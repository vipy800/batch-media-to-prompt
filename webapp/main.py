"""全能媒体反推 · 商用版 API"""
import asyncio
import csv
import io
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from urllib.parse import quote
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import requests

from . import jobs, media, store
from .client import VisionClient, is_local_url
from .config import (
    BASE_DIR, CONFIG_PATH, DEFAULTS, DB_PATH, IMAGE_EXTENSIONS, MAX_UPLOAD_SIZE,
    MODEL_SUGGESTIONS, OUTPUT_DIR, STATIC_DIR, TEMPLATE_DIR, THUMB_DIR, UPLOAD_DIR,
    UPLOAD_EXPIRY_HOURS, VIDEO_EXTENSIONS, all_presets, ensure_dirs, get_preset,
    load_config, output_root, save_config,
)
from .logsetup import asyncio_exception_handler, setup_logging

logger = setup_logging(BASE_DIR)
VERSION = "4.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio

    try:
        asyncio.get_running_loop().set_exception_handler(asyncio_exception_handler)
    except RuntimeError:
        pass
    ensure_dirs()
    store.init(DB_PATH)
    recovered = store.recover_interrupted()
    if recovered:
        logger.info("检测到 %d 个上次未完成的项目，已标记为中断", recovered)
    logger.info("=" * 56)
    logger.info("全能媒体反推 v%s 启动 · %s", VERSION, "打包版" if getattr(sys, "frozen", False) else "源码版")
    logger.info("数据目录: %s", BASE_DIR)
    logger.info("=" * 56)
    cleanup_uploads()
    yield
    logger.info("应用已关闭")


app = FastAPI(title="全能媒体反推", version=VERSION, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def cleanup_uploads():
    try:
        now = datetime.now()
        for name in os.listdir(UPLOAD_DIR):
            path = os.path.join(UPLOAD_DIR, name)
            if os.path.isdir(path) and name != "thumbs":
                oldest = min(
                    (os.path.getmtime(os.path.join(path, f)) for f in os.listdir(path)),
                    default=0,
                )
                if oldest and now - datetime.fromtimestamp(oldest) > timedelta(hours=UPLOAD_EXPIRY_HOURS):
                    shutil.rmtree(path, ignore_errors=True)
    except Exception as e:
        logger.warning("清理上传目录失败: %s", e)


def _json_obj(body) -> dict:
    if not isinstance(body, dict):
        raise HTTPException(400, "请求内容格式不正确")
    return body


def public_cfg(cfg: dict) -> dict:
    """返回给前端的配置：只给界面真正需要的字段，密钥/系统提示词等不外发"""
    visible = (
        "base_url", "model", "video_model", "temperature", "max_tokens", "timeout",
        "max_retries", "concurrency", "image_max_side", "jpeg_quality", "video_frames",
        "video_max_side", "video_grid", "output_folder", "save_next_to_source",
        "skip_existing", "active_preset_image", "active_preset_video", "theme",
    )
    out = {k: cfg.get(k) for k in visible}
    key = (cfg.get("api_key") or "").strip()
    out["api_key_masked"] = (key[:6] + "…" + key[-4:]) if len(key) > 12 else ("已配置" if key else "")
    out["has_key"] = bool(key)
    return out


def safe_rel_thumb(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    try:
        rel = os.path.relpath(path, THUMB_DIR)
    except Exception:
        return None
    if rel.startswith("..") or not os.path.isfile(path):
        return None
    return "/thumbs/" + rel.replace("\\", "/")


def decorate(items: List[dict]) -> List[dict]:
    for it in items:
        it["thumb_url"] = safe_rel_thumb(it.get("thumb"))
        it["preview"] = (it.get("text") or "")[:200]
        # 轮询列表只带预览，避免几百条全文每 2 秒回传一次；全文由详情接口给
        for key in ("src_path", "text", "out_path", "thumb"):
            it.pop(key, None)
    return items


# ------------------------------------------------------------------ 页面
@app.get("/")
def index():
    return FileResponse(
        os.path.join(TEMPLATE_DIR, "index.html"),
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/healthz")
def healthz():
    return {"ok": True, "version": VERSION, "time": int(time.time())}


@app.get("/thumbs/{path:path}")
def thumb(path: str):
    try:
        root = os.path.realpath(THUMB_DIR)
        full = os.path.realpath(os.path.join(THUMB_DIR, path))
        if os.path.commonpath([root, full]) != root or not os.path.isfile(full):
            raise HTTPException(404)
    except (ValueError, OSError):
        raise HTTPException(404)
    if os.path.splitext(full)[1].lower() not in (".jpg", ".jpeg", ".png", ".webp"):
        raise HTTPException(404)
    return FileResponse(full)


# ------------------------------------------------------------------ 配置
@app.get("/api/bootstrap")
def bootstrap():
    cfg = load_config()
    return {
        "version": VERSION,
        "config": public_cfg(cfg),
        "presets": all_presets(),
        "models": MODEL_SUGGESTIONS,
        "model_cache": (cfg.get("model_cache") or {}).get(cfg.get("base_url", "").rstrip("/"), {}).get("models", []),
        "stats": store.stats(),
        "env": {
            "python": platform.python_version(),
            "platform": platform.system() + " " + platform.release(),
            "frozen": bool(getattr(sys, "frozen", False)),
            "base_dir": BASE_DIR,
            "output_dir": output_root(),
            "db": DB_PATH,
            "first_run": (not os.path.exists(os.path.join(BASE_DIR, ".setup_done")) and not cfg.get("api_key")),
        },
    }


def _int_field(patch: dict, key: str, lo: int, hi: int, label: str):
    if key not in patch:
        return
    try:
        value = int(float(patch[key]))
    except (TypeError, ValueError):
        raise HTTPException(400, f"{label} 必须是 {lo}–{hi} 之间的数字")
    if value < lo or value > hi:
        raise HTTPException(400, f"{label} 必须在 {lo}–{hi} 之间")
    patch[key] = value


def _normalise_presets(raw) -> list:
    if not isinstance(raw, list):
        raise HTTPException(400, "预设数据格式不正确")
    if len(raw) > 200:
        raise HTTPException(400, "自定义预设最多 200 条")
    out = []
    for p in raw:
        if not isinstance(p, dict):
            continue
        pid = str(p.get("id") or uuid.uuid4().hex[:8])
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", pid):
            pid = uuid.uuid4().hex[:8]
        name = str(p.get("name") or "自定义预设").strip()[:40] or "自定义预设"
        kind = "video" if p.get("kind") == "video" else "image"
        group = str(p.get("group") or "我的预设").strip()[:20] or "我的预设"
        text = str(p.get("text") or "")[:20000]
        out.append({"id": pid, "name": name, "kind": kind, "group": group,
                    "text": text, "builtin": False})
    return out


@app.post("/api/config")
async def save_settings(request: Request):
    try:
        patch = await request.json()
    except Exception:
        raise HTTPException(400, "请求内容不是合法 JSON")
    if not isinstance(patch, dict):
        raise HTTPException(400, "请求内容格式不正确")
    allowed = set(DEFAULTS.keys()) | {"custom_presets"}
    patch = {k: v for k, v in patch.items() if k in allowed}

    if "api_key" in patch:
        key = str(patch.get("api_key") or "").strip()
        if key:
            patch["api_key"] = key[:500]
        else:
            # 前端密钥框通常留空表示“沿用已保存的 Key”，不能误清空
            patch.pop("api_key", None)
    for key, limit in (("base_url", 500), ("model", 200), ("video_model", 200),
                       ("active_preset_image", 80), ("active_preset_video", 80)):
        if key in patch:
            patch[key] = str(patch.get(key) or "").strip()[:limit]
    if patch.get("base_url"):
        if not re.match(r"^https?://", patch["base_url"], re.I):
            raise HTTPException(400, "接口地址必须以 http:// 或 https:// 开头")
        patch["base_url"] = patch["base_url"].rstrip("/")
    if "output_folder" in patch:
        folder = str(patch.get("output_folder") or "").strip()
        if folder:
            folder = os.path.abspath(os.path.expanduser(folder))
            try:
                os.makedirs(folder, exist_ok=True)
            except Exception as e:
                raise HTTPException(400, f"输出目录无法创建：{e}")
        patch["output_folder"] = folder
    if "theme" in patch:
        patch["theme"] = "light" if str(patch["theme"]) == "light" else "dark"
    if "video_grid" in patch:
        patch["video_grid"] = str(patch["video_grid"]).lower() in ("1", "true", "on", "yes")
    if "system_prompt" in patch:
        patch["system_prompt"] = str(patch["system_prompt"] or "")[:8000]
    _int_field(patch, "concurrency", 1, 8, "并发数")
    _int_field(patch, "timeout", 10, 7200, "超时时间")
    _int_field(patch, "max_retries", 1, 8, "重试次数")
    _int_field(patch, "image_max_side", 512, 4096, "图片最长边")
    _int_field(patch, "jpeg_quality", 50, 95, "JPEG 质量")
    _int_field(patch, "video_frames", 3, 24, "视频抽帧数")
    _int_field(patch, "video_max_side", 512, 2048, "视频帧最长边")
    _int_field(patch, "max_tokens", 64, 16384, "最大输出长度")
    if "temperature" in patch:
        try:
            temp = float(patch["temperature"])
        except (TypeError, ValueError):
            raise HTTPException(400, "温度必须是 0–2 之间的数字")
        if temp < 0 or temp > 2:
            raise HTTPException(400, "温度必须在 0–2 之间")
        patch["temperature"] = round(temp, 2)
    if "custom_presets" in patch:
        patch["custom_presets"] = _normalise_presets(patch["custom_presets"])

    cfg = save_config(patch)
    try:
        if cfg.get("api_key"):
            with open(os.path.join(BASE_DIR, ".setup_done"), "w", encoding="utf-8") as f:
                f.write("1")
    except Exception:
        pass
    return {"ok": True, "config": public_cfg(cfg)}


@app.post("/api/config/clear-key")
def clear_api_key():
    """显式清除已保存的 Key（前端不会把完整 Key 回显，因此需要单独入口）"""
    cfg = save_config({"api_key": ""})
    return {"ok": True, "config": public_cfg(cfg)}


@app.post("/api/config/test")
async def test_connection(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    body = _json_obj(body)
    cfg = load_config()
    for key in ("base_url", "model", "api_key"):
        if key in body and str(body.get(key) or "").strip():
            cfg[key] = str(body[key]).strip()
    if not cfg.get("api_key") and not is_local_url(cfg.get("base_url") or ""):
        return {"ok": False, "error": "还没有可用的 API Key，请先填写并保存", "ms": 0}
    client = VisionClient(cfg)
    model = body.get("model") or cfg.get("model")
    if not model:
        return {"ok": False, "error": "还没有填写模型名", "ms": 0}
    return client.test(str(model).strip())


VISION_HINTS = (
    "vl", "vision", "visual", "multimodal", "multi-modal", "omni", "llava",
    "internvl", "minicpm-v", "pixtral", "idefics", "cogvlm", "molmo",
    "glm-4v", "glm-5", "gpt-4o", "gpt-4.1", "gpt-5", "claude", "gemini",
    "qwen-vl", "caption", "phi-4-mm", "step-1v", "yi-vl", "avila", "deepseek-vl",
)

NON_CHAT_HINTS = (
    "embedding", "embed", "rerank", "tts", "speech", "audio", "asr", "whisper",
    "flux", "diffusion", "sdxl", "kolors", "seedream", "seededit", "image-edit",
    "image-gen", "upscal", "moderation", "guard",
)


def _model_rank(model_id: str) -> float:
    """给模型打分：偏好通用视觉对话模型，压低 OCR / 描述器 / 生成类"""
    low = (model_id or "").lower()
    s = 0.0
    if "vl" in low:
        s += 6
    if "instruct" in low:
        s += 4
    if "qwen3-vl" in low or "qwen2.5-vl" in low or "qwen2-vl" in low:
        s += 5
    if "glm-5" in low or "glm-4.6v" in low or "gpt-4o" in low:
        s += 3
    if "thinking" in low or "reasoner" in low:
        s -= 3
    if any(k in low for k in ("ocr", "caption", "omni", "base")):
        s -= 6
    import re as _re
    m = _re.search(r"(\d+(?:\.\d+)?)\s*b", low)
    if m:
        s += min(6.0, float(m.group(1)) / 8.0)   # 大模型优先
    return s


def _is_chat_model(model_id: str) -> bool:
    """排除向量/语音/生图类，只留能对话（含视觉理解）的模型"""
    low = (model_id or "").lower()
    if any(h in low for h in NON_CHAT_HINTS):
        return False
    if "image" in low and not any(h in low for h in ("vl", "vision", "omni", "caption", "ocr")):
        return False
    return True


def _is_vision_model(model_id: str) -> bool:
    low = (model_id or "").lower()
    return any(h in low for h in VISION_HINTS)


@app.post("/api/models")
async def list_models(request: Request):
    """拉取该接口下所有可用模型，并标注哪些支持视觉（多模态）"""
    body = _json_obj(await request.json())
    cfg = load_config()
    base = (body.get("base_url") or cfg.get("base_url") or "").strip().rstrip("/")
    for suffix in ("/chat/completions", "/completions"):
        if base.lower().endswith(suffix):
            base = base[: -len(suffix)].rstrip("/")
    key = body.get("api_key")
    if key is None or not str(key).strip():
        # 前端密钥框留空代表沿用已保存的 Key
        key = cfg.get("api_key") or ""
    key = str(key).strip()
    if not base:
        return {"ok": False, "error": "还没有填接口地址", "models": [], "suggestions": MODEL_SUGGESTIONS}
    if not re.match(r"^https?://", base, re.I):
        return {"ok": False, "error": "接口地址必须以 http:// 或 https:// 开头", "models": [], "suggestions": MODEL_SUGGESTIONS}

    url = base + "/models"
    headers = {"Accept": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    try:
        r = requests.get(url, headers=headers, timeout=12)
    except requests.exceptions.SSLError as e:
        return {"ok": False, "error": "SSL 证书校验失败：" + str(e)[:80], "models": [], "suggestions": MODEL_SUGGESTIONS}
    except requests.exceptions.ConnectionError:
        return {"ok": False, "error": "连不上这个地址，检查接口地址 / 本机服务是否已启动", "models": [], "suggestions": MODEL_SUGGESTIONS}
    except requests.exceptions.Timeout:
        return {"ok": False, "error": "拉取模型超时（12s），接口可能较慢或地址不对", "models": [], "suggestions": MODEL_SUGGESTIONS}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120], "models": [], "suggestions": MODEL_SUGGESTIONS}

    if r.status_code in (401, 403):
        return {"ok": False, "error": f"鉴权失败（HTTP {r.status_code}），Key 不对或没有该模型的权限", "models": [], "suggestions": MODEL_SUGGESTIONS}
    if r.status_code == 404:
        return {"ok": False, "error": "该服务商未开放 /models 列表，请手动填模型名（下方有推荐）", "models": [], "suggestions": MODEL_SUGGESTIONS}
    if r.status_code != 200:
        return {"ok": False, "error": f"HTTP {r.status_code}：{r.text[:120]}", "models": [], "suggestions": MODEL_SUGGESTIONS}

    try:
        data = r.json()
    except Exception:
        return {"ok": False, "error": "返回内容不是 JSON，地址可能填错了", "models": [], "suggestions": MODEL_SUGGESTIONS}

    raw = data.get("data") or data.get("models") or data.get("result") or []
    if isinstance(raw, dict):
        raw = raw.get("data") or []
    ids = []
    caps = {}
    for m in raw:
        if isinstance(m, str):
            mid = m
        elif isinstance(m, dict):
            mid = m.get("id") or m.get("model") or m.get("name")
            cap = json.dumps(m.get("capabilities") or m.get("capability") or "", ensure_ascii=False).lower()
            if "vision" in cap or "image" in cap or "multimodal" in cap:
                caps[mid] = True
        else:
            continue
        if mid and mid not in ids:
            ids.append(str(mid))

    models = []
    skipped = 0
    for mid in ids:
        if not _is_chat_model(mid):
            skipped += 1
            continue
        vis = bool(caps.get(mid)) or _is_vision_model(mid)
        models.append({"id": mid, "vision": vis, "rank": round(_model_rank(mid), 2)})
    models.sort(key=lambda x: (not x["vision"], -x["rank"], x["id"].lower()))
    # 前 3 个视觉模型标「推荐」
    shown = 0
    for m in models:
        if m["vision"]:
            if shown < 3:
                m["rec"] = True
            shown += 1

    # 缓存起来，下次打开/主界面输入框直接能用
    try:
        cache = cfg.get("model_cache") or {}
        cache[base] = {"models": models, "ts": int(time.time())}
        if len(cache) > 12:
            cache = dict(list(cache.items())[-12:])
        save_config({"model_cache": cache})
    except Exception:
        pass

    return {
        "ok": True,
        "base": base,
        "count": len(models),
        "vision_count": sum(1 for m in models if m["vision"]),
        "skipped": skipped,
        "models": models,
    }


LOCAL_PORTS = [    (11434, "Ollama"),
    (1234, "LM Studio"),
    (8080, "llama.cpp"),
    (8000, "vLLM / 其他"),
    (6006, "自定义服务"),
]


def _probe_one(port: int, name: str) -> dict:
    url = f"http://127.0.0.1:{port}/v1"
    out = {"port": port, "name": name, "url": url, "ok": False, "models": [], "detail": ""}
    try:
        r = requests.get(f"{url}/models", timeout=2)
        if r.status_code == 200:
            data = r.json()
            raw = data.get("data") or data.get("models") or []
            ids = [m.get("id") for m in raw if isinstance(m, dict) and m.get("id")]
            out["ok"] = True
            out["models"] = ids[:12]
            out["detail"] = "OpenAI 兼容 /v1 可用"
        else:
            out["detail"] = f"HTTP {r.status_code}"
    except Exception as e:
        out["detail"] = str(e)[:80]
    return out


@app.get("/api/local/scan")
def scan_local():
    """探测本机常见 AI 服务端口，帮用户一键找到可用地址"""
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=len(LOCAL_PORTS)) as ex:
        results = list(ex.map(lambda p: _probe_one(*p), LOCAL_PORTS))
    return {"found": [r for r in results if r["ok"]], "all": results}


@app.post("/api/selfcheck")
async def selfcheck(request: Request):
    """一键自检：把「配好了能不能跑」的每一步都验一遍，给出结论和修法"""
    try:
        body = await request.json()
    except Exception:
        body = {}
    body = _json_obj(body)
    deep = bool(body.get("deep", True))
    cfg = load_config()
    base = (cfg.get("base_url") or "").rstrip("/")
    model = (cfg.get("model") or "").strip()
    key = (cfg.get("api_key") or "").strip()
    from .client import is_local_url

    checks = []

    def add(name, ok, detail, fix="", level="error"):
        checks.append({"name": name, "ok": bool(ok), "detail": detail, "fix": fix, "level": level})

    add("配置文件", True, f"{CONFIG_PATH}（密钥长度 {len(key)}）")

    if not base:
        add("接口地址", False, "没有填接口地址", "设置 → 接口 → 点服务商卡片或填 https://…/v1")
    else:
        add("接口地址", True, base)

    local = is_local_url(base) if base else False
    if local:
        add("API Key", True, "本地 / 内网地址，免 Key", level="info")
    elif key:
        add("API Key", True, f"已填（{len(key)} 位）")
    else:
        add("API Key", False, "没有填 Key，云端接口必须有", "设置 → 接口 → 填服务商给的 Key")

    if not model:
        add("模型", False, "没有选模型", "设置 → 接口 → 点「拉取可用模型」选一个带「视觉」的")

    # 拉模型列表
    listed = []
    vision = []
    if base:
        try:
            h = {"Accept": "application/json"}
            if key:
                h["Authorization"] = "Bearer " + key
            r = requests.get(base + "/models", headers=h, timeout=10)
            if r.status_code == 200:
                data = r.json()
                raw = data.get("data") or data.get("models") or []
                listed = [m.get("id") for m in raw if isinstance(m, dict) and m.get("id")]
                vision = [i for i in listed if _is_vision_model(i)]
                add("模型列表", True, f"共 {len(listed)} 个，其中 {len(vision)} 个视觉模型")
            elif r.status_code == 404:
                add("模型列表", True, "该服务商未开放 /models（不影响使用）", level="warn")
            elif r.status_code in (401, 403):
                add("模型列表", False,
                    "未填 Key，无法查询（填完 Key 会自动列出来）" if not key else f"HTTP {r.status_code}，Key 无效或无权限",
                    "设置 → 接口 → 填 Key 后保存" if not key else "重新复制 Key，注意别带空格")
            else:
                add("模型列表", False, f"HTTP {r.status_code}：{r.text[:80]}", "检查接口地址是否以 /v1 结尾")
        except requests.exceptions.SSLError:
            add("网络连通", False, "SSL 证书校验失败", "检查系统时间 / 代理设置")
        except requests.exceptions.ConnectionError:
            add("网络连通", False, "连不上接口地址", "本机服务是否启动？云端地址是否写错？")
        except requests.exceptions.Timeout:
            add("网络连通", False, "连接超时（10s）", "换网络或稍后再试")
        except Exception as e:
            add("网络连通", False, str(e)[:100])

    if listed and model and model not in listed:
        add("模型可用性", False, f"「{model}」不在该接口列表里",
            "设置 → 拉取模型后重选；本地模型确认已 ollama pull")
    elif model and not local and not key:
        add("模型可用性", True, f"{model}（填 Key 后再验证）", level="warn")
    elif model:
        add("模型可用性", True, f"{model}" + ("（视觉）" if _is_vision_model(model) else "（未识别为视觉，可能无法读图）"))

    out_dir = output_root()
    try:
        os.makedirs(out_dir, exist_ok=True)
        probe = os.path.join(out_dir, ".write_test")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        add("输出目录", True, out_dir)
    except Exception as e:
        add("输出目录", False, f"无法写入：{e}", "把输出目录改成有权限的路径")

    try:
        free = shutil.disk_usage(out_dir).free / (1024 ** 3)
        add("磁盘空间", free > 0.5, f"剩余 {free:.1f} GB", "清理 C 盘或改输出目录" if free <= 0.5 else "", level="info")
    except Exception:
        pass

    # 真调一次文字接口（最便宜）
    if deep and base and model and (key or local):
        client = VisionClient(cfg)
        res = client.test(model)
        if res.get("ok"):
            add("接口实测（文字）", True, f"{res['ms']}ms，返回：{(res.get('reply') or '')[:30]}")
        else:
            add("接口实测（文字）", False, str(res.get("error"))[:160],
                "Key/模型/地址三者必须是同一家；看错误码：401=Key，404=模型或地址")
        # 再验一次视觉（1 张小图，几乎不耗额度）
        if res.get("ok"):
            try:
                from io import BytesIO
                from PIL import Image
                buf = BytesIO()
                Image.new("RGB", (64, 64), (0, 128, 255)).save(buf, format="JPEG", quality=80)
                buf.seek(0)
                import base64
                url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
                ans = client.analyze("这张图是什么颜色？只回答颜色。", [url], model, max_retries=1)
                add("接口实测（看图）", True, f"模型能读图：{ans[:30]}")
            except Exception as e:
                add("接口实测（看图）", False, str(e)[:160],
                    "换带「视觉」标记的模型；本地模型确认是 VL 版本")

    failed = [c for c in checks if not c["ok"] and c.get("level") == "error"]
    return {"ok": not failed, "checks": checks, "failed": len(failed)}


@app.post("/api/presets")
async def manage_presets(request: Request):
    body = _json_obj(await request.json())
    action = body.get("action")
    cfg = load_config()
    custom = cfg.get("custom_presets") or []
    if action == "save":
        pid = str(body.get("id") or "")
        if pid and not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", pid):
            raise HTTPException(400, "预设 ID 不合法")
        pid = pid or uuid.uuid4().hex[:8]
        text = str(body.get("text") or "")[:20000]
        if not text.strip():
            raise HTTPException(400, "提示词内容不能为空")
        entry = {
            "id": pid,
            "name": str(body.get("name") or "自定义预设").strip()[:40] or "自定义预设",
            "kind": "video" if body.get("kind") == "video" else "image",
            "group": str(body.get("group") or "我的预设").strip()[:20] or "我的预设",
            "text": text,
            "builtin": False,
        }
        custom = [c for c in custom if c.get("id") != pid] + [entry]
        if len(custom) > 200:
            raise HTTPException(400, "自定义预设最多 200 条")
        save_config({"custom_presets": _normalise_presets(custom)})
        return {"ok": True, "presets": all_presets()}
    if action == "delete":
        pid = body.get("id")
        save_config({"custom_presets": [c for c in custom if c.get("id") != pid]})
        return {"ok": True, "presets": all_presets()}
    raise HTTPException(400, "未知操作")


# ------------------------------------------------------------------ 任务创建
def _preflight(cfg: dict, media_type: str = "auto"):
    """开跑前体检：Key / 模型是否填对，避免几百个文件全失败才发现"""
    base = (cfg.get("base_url") or "").rstrip("/")
    need_video = media_type in ("auto", "video")
    models = []
    if media_type != "video":
        models.append(str(cfg.get("model") or "").strip())
    if need_video:
        models.append(str(cfg.get("video_model") or cfg.get("model") or "").strip())
    models = [m for m in models if m]
    if not base:
        raise HTTPException(400, "还没配置接口地址：点右上角「设置」→ 选服务商或填地址")
    if not models:
        raise HTTPException(400, "还没配置模型：点右上角「设置」→ 拉取可用模型后选一个")
    if not (cfg.get("api_key") or "").strip():
        if not is_local_url(base):
            raise HTTPException(400, "还没填 API Key：点右上角「设置」→ 填 Key → 保存")
    cache = (cfg.get("model_cache") or {}).get(base) or {}
    ids = [m.get("id") for m in (cache.get("models") or []) if m.get("id")]
    if ids:
        for model in set(models):
            if model not in ids:
                vis = [m.get("id") for m in cache["models"] if m.get("vision")][:3]
                hint = ("，推荐：" + "、".join(vis)) if vis else ""
                raise HTTPException(400, f"模型「{model}」不在该接口的可用列表里{hint}。请在设置里重新拉取模型后重选")


def _safe_workers(value, default: int = 3) -> int:
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        n = default
    return max(1, min(8, n))


def _collect_params(form: dict, media_type: str) -> dict:
    cfg = load_config()
    if media_type not in ("auto", "image", "video"):
        raise HTTPException(400, "处理模式只能是 auto / image / video")
    preset_id = str(form.get("preset_id") or cfg.get("active_preset_image", "standard"))[:80]
    preset = get_preset(preset_id, "image")
    prompt = str(form.get("prompt") or preset["text"])[:20000]
    model = str(form.get("model") or cfg.get("model") or "")[:200]

    video_preset_id = str(form.get("video_preset_id") or cfg.get("active_preset_video", "video"))[:80]
    video_preset = get_preset(video_preset_id, "video")
    video_prompt = str(form.get("video_prompt") or video_preset["text"])[:20000]
    video_model = str(form.get("video_model") or cfg.get("video_model") or "")[:200]
    preset_label = video_preset["name"] if media_type == "video" else preset["name"]
    if form.get("prompt"):
        preset_label = "自定义提示词 · " + preset["name"]

    return {
        "name": str(form.get("name") or "批量任务").strip()[:60] or "批量任务",
        "source": form.get("source") or "upload",
        "media_type": media_type,
        "preset_id": preset_id,
        "preset_name": preset_label[:120],
        "prompt_image": prompt,
        "prompt_video": video_prompt,
        "model_image": model,
        "model_video": video_model,
        "concurrency": _safe_workers(form.get("concurrency") or cfg.get("concurrency", 3)),
        "save_next_to_source": str(form.get("save_next_to_source")).lower() in ("1", "true", "on"),
        "skip_existing": str(form.get("skip_existing")).lower() in ("1", "true", "on"),
    }


@app.post("/api/jobs/upload")
async def create_upload_job(
    files: List[UploadFile] = File(...),
    preset_id: str = Form(""),
    model: str = Form(""),
    prompt: str = Form(""),
    video_preset_id: str = Form(""),
    video_prompt: str = Form(""),
    video_model: str = Form(""),
    name: str = Form(""),
    mode: str = Form("auto"),
    concurrency: str = Form(""),
    save_next_to_source: str = Form("0"),
    skip_existing: str = Form("0"),
):
    if not files:
        raise HTTPException(400, "没有收到文件")
    params = _collect_params(
        {
            "preset_id": preset_id, "model": model, "name": name, "source": "upload",
            "prompt": prompt, "video_preset_id": video_preset_id,
            "video_prompt": video_prompt, "video_model": video_model,
            "concurrency": concurrency, "save_next_to_source": save_next_to_source,
            "skip_existing": skip_existing,
        },
        mode,
    )
    pre_cfg = load_config()
    pre_cfg["model"] = params.get("model_image") or ""
    pre_cfg["video_model"] = params.get("model_video") or ""
    _preflight(pre_cfg, mode)

    box = os.path.join(UPLOAD_DIR, datetime.now().strftime("job_%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:4])
    os.makedirs(box, exist_ok=True)

    items = []
    try:
        for f in files:
            fname = media.safe_filename(f.filename)
            kind = media.classify(fname)
            if kind is None:
                continue
            if mode == "image" and kind != "image":
                continue
            if mode == "video" and kind != "video":
                continue
            dest = media.unique_path(os.path.join(box, fname))
            size = 0
            with open(dest, "wb") as out:
                while chunk := await f.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_UPLOAD_SIZE:
                        out.close()
                        os.remove(dest)
                        raise HTTPException(413, f"{fname} 超过单文件大小限制")
                    out.write(chunk)
            items.append({"filename": fname, "src_path": dest, "media_type": kind})
    except Exception:
        shutil.rmtree(box, ignore_errors=True)
        raise

    if not items:
        shutil.rmtree(box, ignore_errors=True)
        raise HTTPException(400, "没有可处理的图片或视频文件")

    if not params["name"] or params["name"] == "批量任务":
        short = items[0]["filename"][:60]
        params["name"] = f"{len(items)} 个文件" if len(items) > 1 else short
    job_id = jobs.start_job(items, params)
    return {"ok": True, "job_id": job_id, "total": len(items)}


@app.post("/api/jobs/scan")
async def create_scan_job(request: Request):
    body = _json_obj(await request.json())
    folder = str(body.get("folder") or "").strip().strip('"')
    if not folder or not os.path.isdir(folder):
        raise HTTPException(400, "文件夹不存在或无法访问")
    recursive = bool(body.get("recursive", False))
    mode = str(body.get("mode") or "auto")

    params = _collect_params(body, mode)
    params["source"] = "folder"
    pre_cfg = load_config()
    pre_cfg["model"] = params.get("model_image") or ""
    pre_cfg["video_model"] = params.get("model_video") or ""
    _preflight(pre_cfg, mode)

    exts = IMAGE_EXTENSIONS + VIDEO_EXTENSIONS
    found = []
    if recursive:
        for root, _dirs, files in os.walk(folder):
            for f in files:
                if f.lower().endswith(exts):
                    found.append(os.path.join(root, f))
    else:
        for f in os.listdir(folder):
            p = os.path.join(folder, f)
            if os.path.isfile(p) and f.lower().endswith(exts):
                found.append(p)

    items = []
    for p in sorted(found):
        kind = media.classify(p)
        if kind is None:
            continue
        if mode == "image" and kind != "image":
            continue
        if mode == "video" and kind != "video":
            continue
        items.append({"filename": os.path.basename(p), "src_path": p, "media_type": kind})

    if not items:
        raise HTTPException(400, "该文件夹内没有找到可处理的媒体文件")

    if not params["name"] or params["name"] == "批量任务":
        params["name"] = (os.path.basename(folder.rstrip("\\/")) or folder)[:60]
    job_id = jobs.start_job(items, params)
    return {"ok": True, "job_id": job_id, "total": len(items)}


@app.post("/api/jobs/preview")
async def preview_scan(request: Request):
    """扫描文件夹但不启动任务，返回文件数量与样例"""
    body = _json_obj(await request.json())
    folder = str(body.get("folder") or "").strip().strip('"')
    if not os.path.isdir(folder):
        raise HTTPException(400, "文件夹不存在或无法访问")
    exts = IMAGE_EXTENSIONS + VIDEO_EXTENSIONS
    hits = []
    for root, _d, files in os.walk(folder) if body.get("recursive") else [(folder, [], os.listdir(folder))]:
        for f in files:
            if f.lower().endswith(exts):
                hits.append(os.path.join(root, f))
    imgs = sum(1 for h in hits if media.classify(h) == "image")
    vids = len(hits) - imgs
    return {"total": len(hits), "images": imgs, "videos": vids, "samples": [os.path.basename(h) for h in hits[:8]]}


# ------------------------------------------------------------------ 任务查询与控制
@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    data = jobs.status(job_id)
    if not data:
        raise HTTPException(404, "任务不存在")
    data["items"] = decorate(data["items"])
    return data


@app.post("/api/jobs/{job_id}/{action}")
def job_action(job_id: str, action: str):
    if action == "pause":
        return {"ok": jobs.pause(job_id)}
    if action == "resume":
        return {"ok": jobs.resume(job_id)}
    if action == "cancel":
        return {"ok": jobs.cancel(job_id)}
    if action == "retry":
        return {"ok": True, "count": jobs.retry_failed(job_id)}
    raise HTTPException(400, "未知操作")


def _csv_cell(value):
    """防 Excel 公式注入：以 = + - @ 开头的单元格前置单引号"""
    s = "" if value is None else str(value)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


@app.get("/api/jobs/{job_id}/export")
def export_job(job_id: str, fmt: str = "zip"):
    data = jobs.status(job_id)
    if not data:
        raise HTTPException(404, "任务不存在")
    job = data["job"]
    items = data["items"]
    stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(job["created_at"]))
    base = f"反推结果_{stamp}_{job_id[:6]}"

    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["序号", "文件名", "状态", "字符数", "耗时(秒)", "输出路径", "错误", "内容"])
        for it in items:
            w.writerow([it["idx"] + 1, _csv_cell(it["filename"]), it["status"], it["chars"] or 0,
                        it["duration"] or 0, _csv_cell(it["out_path"] or ""),
                        _csv_cell(it["error"] or ""),
                        _csv_cell((it["text"] or "").replace("\n", " "))])
        return StreamingResponse(
            iter(["\ufeff" + buf.getvalue()]),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": _cd(f"{base}.csv")},
        )

    if fmt in ("txt", "text"):
        lines = []
        for it in items:
            if it["status"] not in ("done", "skipped") or not it["text"]:
                continue
            lines.append(" ".join((it["text"] or "").split()))
        payload = "\r\n".join(lines) + ("\r\n" if lines else "")
        return StreamingResponse(
            iter([payload.encode("utf-8")]),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": _cd(f"{base}.txt")},
        )

    if fmt == "json":
        payload = json.dumps({"job": job, "counts": data["counts"], "items": [
            {k: it[k] for k in ("idx", "filename", "status", "chars", "duration", "text", "error", "out_path")}
            for it in items
        ]}, ensure_ascii=False, indent=2)
        return StreamingResponse(
            iter([payload]),
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": _cd(f"{base}.json")},
        )

    if fmt == "md":
        created = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(job["created_at"]))
        lines = [f"# {job['name']}", "", f"- 模型：{job['model']}", f"- 生成时间：{created}", ""]
        for it in items:
            lines.append(f"## {it['idx'] + 1}. {it['filename']}")
            lines.append(f"- 状态：{it['status']}　字符数：{it['chars'] or 0}")
            if it["error"]:
                lines.append(f"- 错误：{it['error']}")
            lines += ["", it["text"] or "_（无内容）_", ""]
        return StreamingResponse(
            iter(["\n".join(lines)]),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": _cd(f"{base}.md")},
        )

    # 默认：打包 txt
    mem = io.BytesIO()
    used = {"结果清单.csv"}
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as zf:
        for it in items:
            if it["status"] not in ("done", "skipped"):
                continue
            stem = os.path.splitext(media.safe_filename(it["filename"]))[0] or "结果"
            name = stem + ".txt"
            if name.lower() in used:
                name = f"{stem}_{it['idx'] + 1}.txt"
            used.add(name.lower())
            zf.writestr(name, it["text"] or "")
        zf.writestr("结果清单.csv", "\ufeff" + _items_csv(items))
    mem.seek(0)
    return StreamingResponse(
        mem, media_type="application/zip",
        headers={"Content-Disposition": _cd(f"{base}.zip")},
    )


def _cd(filename: str) -> str:
    """RFC 5987 编码的下载文件名"""
    return "attachment; filename*=UTF-8''" + quote(filename)


def _items_csv(items) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["序号", "文件名", "状态", "字符数", "耗时(秒)", "错误"])
    for it in items:
        w.writerow([it["idx"] + 1, _csv_cell(it["filename"]), it["status"],
                    it["chars"] or 0, it["duration"] or 0, _csv_cell(it["error"] or "")])
    return buf.getvalue()


@app.get("/api/items/{item_id}")
def item_detail(item_id: int):
    it = store.get_item(item_id)
    if not it:
        raise HTTPException(404)
    it["thumb_url"] = safe_rel_thumb(it.get("thumb"))
    return it


@app.post("/api/items/{item_id}/text")
async def save_item_text(item_id: int, request: Request):
    body = _json_obj(await request.json())
    text = str(body.get("text") or "")[:200000]
    it = store.get_item(item_id)
    if not it:
        raise HTTPException(404)
    store.update_item(item_id, text=text, chars=len(text))
    out = it.get("out_path")
    if out and os.path.exists(out) and os.path.isfile(out):
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
    return {"ok": True}


@app.post("/api/items/{item_id}/rerun")
def rerun_item(item_id: int):
    if not jobs.rerun_item(item_id):
        raise HTTPException(404, "项目不存在")
    return {"ok": True}


# ------------------------------------------------------------------ 历史
@app.get("/api/history")
def history(q: str = "", status: str = "", limit: int = 50, offset: int = 0):
    limit = max(1, min(200, int(limit)))
    offset = max(0, int(offset))
    rows = store.list_jobs(limit=limit, offset=offset, q=q[:80], status=status[:20])
    return {"jobs": rows, "stats": store.stats()}


@app.post("/api/history/clear")
def clear_history():
    if jobs.has_active():
        raise HTTPException(409, "还有任务正在运行，请先取消当前任务再清空历史")
    n = store.clear_history()
    shutil.rmtree(THUMB_DIR, ignore_errors=True)
    os.makedirs(THUMB_DIR, exist_ok=True)
    return {"ok": True, "deleted": n}


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str):
    if jobs.has_active(job_id):
        raise HTTPException(409, "该任务正在运行，请先取消再删除")
    store.delete_job(job_id)
    shutil.rmtree(os.path.join(THUMB_DIR, job_id), ignore_errors=True)
    return {"ok": True}


def _is_within(path: str, root: str) -> bool:
    try:
        path = os.path.normcase(os.path.realpath(path))
        root = os.path.normcase(os.path.realpath(root))
        return os.path.commonpath([path, root]) == root
    except (ValueError, OSError):
        return False


@app.post("/api/open-output")
async def open_output(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    body = _json_obj(body)
    target = str(body.get("path") or output_root()).strip() or output_root()
    target = os.path.realpath(os.path.expanduser(target))
    roots = [os.path.realpath(output_root()), os.path.realpath(OUTPUT_DIR)]
    if not any(_is_within(target, r) for r in roots):
        raise HTTPException(400, "只能打开输出目录内的文件夹")
    if not os.path.isdir(target):
        raise HTTPException(400, "目录不存在")
    try:
        if platform.system() == "Windows":
            os.startfile(target)  # noqa: S606
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", target])
        else:
            subprocess.Popen(["xdg-open", target])
    except Exception as e:
        raise HTTPException(500, str(e))
    return {"ok": True}


# ------------------------------------------------------------------ 运维
@app.get("/api/logs", response_class=PlainTextResponse)
def logs(lines: int = 300):
    lines = max(1, min(2000, int(lines)))
    path = os.path.join(BASE_DIR, "app.log")
    if not os.path.exists(path):
        return "暂无日志"
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(max(0, size - lines * 200))
        data = f.read().decode("utf-8", "ignore").splitlines()
    return "\n".join(data[-lines:])


@app.post("/api/maintenance/clean-uploads")
def clean_uploads():
    cleanup_uploads()
    size = 0
    for root, _d, files in os.walk(UPLOAD_DIR):
        if "thumbs" in root:
            continue
        for f in files:
            size += os.path.getsize(os.path.join(root, f))
    return {"ok": True, "size": media.human_size(size)}


@app.get("/api/version")
def version():
    return {"version": VERSION}


# ------------------------------------------------------------------ 本地目录选择器
_pick_lock = __import__("threading").Lock()


@app.post("/api/pick-folder")
async def pick_folder(request: Request):
    body = _json_obj(await request.json())
    kind = body.get("kind", "folder")
    if not _pick_lock.acquire(blocking=False):
        raise HTTPException(429, "已有一个选择窗口打开，请先完成它")

    def _dialog():
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            if kind == "file":
                path = filedialog.askopenfilename(title="选择媒体文件")
            else:
                path = filedialog.askdirectory(title="选择文件夹")
            root.destroy()
            return path or ""
        finally:
            _pick_lock.release()

    try:
        path = await asyncio.get_running_loop().run_in_executor(None, _dialog)
    except Exception as e:
        raise HTTPException(500, f"无法打开系统选择窗口：{e}")
    return {"path": path}
