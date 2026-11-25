"""批处理任务管理：并发队列、暂停/继续/取消、失败重试"""
import json
import os
import threading
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from . import media, store
from .client import VisionClient, ApiError
from .config import load_config, get_preset, output_root, THUMB_DIR, ensure_dirs

_runtimes = {}
_lock = threading.Lock()


class JobRuntime:
    def __init__(self, job_id: str, params: dict, total: int):
        self.id = job_id
        self.params = params
        self.total = total
        self.pause = threading.Event()
        self.cancel = threading.Event()
        self.counts = Counter({"done": 0, "failed": 0, "skipped": 0})
        self.lock = threading.Lock()
        self.started_at = time.time()
        self.finished = False
        self.executor = None
        self.standalone = False


def _safe_workers(value, default: int = 3) -> int:
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        n = default
    return max(1, min(8, n))


def _job_folder(rt: JobRuntime) -> str:
    name = rt.params.get("name") or "任务"
    safe = "".join(ch for ch in name if ch not in '<>:"/\\|?*')[:32].strip(" .") or "任务"
    # 秒级时间 + 任务 id 尾号，避免同一秒同名任务互相覆盖
    suffix = (rt.id or uuid.uuid4().hex)[:6]
    folder = os.path.join(
        output_root(),
        f"{time.strftime('%Y%m%d_%H%M%S', time.localtime(rt.started_at))}_{safe}_{suffix}",
    )
    os.makedirs(folder, exist_ok=True)
    return folder


def start_job(items: list, params: dict) -> str:
    """items: [{filename, src_path, media_type}]"""
    ensure_dirs()
    job_id = uuid.uuid4().hex[:12]
    rt = JobRuntime(job_id, params, len(items))
    rt.output_dir = _job_folder(rt)

    params = dict(params)
    params["output_dir"] = rt.output_dir
    rt.params = params

    store.create_job(
        {
            "id": job_id,
            "name": params.get("name") or "批量任务",
            "source": params.get("source", "upload"),
            "media_type": params.get("media_type", "image"),
            "model": params.get("model_image", ""),
            "preset_id": params.get("preset_id", ""),
            "preset_name": params.get("preset_name", ""),
            "status": "running",
            "total": len(items),
            "params": params,
        }
    )
    store.add_items(job_id, items)

    with _lock:
        _runtimes[job_id] = rt

    workers = _safe_workers(params.get("concurrency", 3))
    rt.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix=f"job-{job_id[:6]}-")
    for item in store.job_items(job_id):
        rt.executor.submit(_run_item, rt, item)

    if not items:
        _finish(rt, "done")
    return job_id


def _run_item(rt: JobRuntime, item: dict) -> None:
    if rt.cancel.is_set():
        store.update_item(item["id"], status="cancelled", finished_at=time.time())
        _maybe_finish(rt)
        return

    while rt.pause.is_set() and not rt.cancel.is_set():
        time.sleep(0.25)
    if rt.cancel.is_set():
        store.update_item(item["id"], status="cancelled", finished_at=time.time())
        _maybe_finish(rt)
        return

    cfg = load_config()
    t0 = time.time()
    store.update_item(item["id"], status="running", started_at=t0)

    # 缩略图先行，界面能马上看到预览
    thumb = os.path.join(THUMB_DIR, rt.id, f"{item['idx']}.jpg")
    if not media.make_thumb(item["src_path"], thumb):
        thumb = None
    store.update_item(item["id"], thumb=thumb)

    if rt.params.get("skip_existing") and rt.params.get("save_next_to_source"):
        out_guess = os.path.splitext(item["src_path"])[0] + ".txt"
        if os.path.exists(out_guess):
            store.update_item(
                item["id"], status="skipped", out_path=out_guess, finished_at=time.time()
            )
            _bump(rt, "skipped")
            return

    try:
        client = VisionClient(cfg)
        if item["media_type"] == "video":
            frames, _vmeta = media.extract_video_frames(
                item["src_path"],
                count=int(cfg.get("video_frames", 9)),
                max_side=int(cfg.get("video_max_side", 1024)),
                quality=int(cfg.get("jpeg_quality", 88)),
                grid=bool(cfg.get("video_grid", True)),
            )
            images = frames
            model = rt.params.get("model_video") or rt.params.get("model") or cfg.get("video_model")
            prompt = rt.params.get("prompt_video") or rt.params.get("prompt") or ""
        else:
            data, _meta = media.prepare_image(
                item["src_path"],
                max_side=int(cfg.get("image_max_side", 1600)),
                quality=int(cfg.get("jpeg_quality", 88)),
            )
            images = [data]
            model = rt.params.get("model_image") or rt.params.get("model") or cfg.get("model")
            prompt = rt.params.get("prompt_image") or rt.params.get("prompt") or ""

        text = client.analyze(prompt, images, model)

        if rt.params.get("save_next_to_source"):
            src_dir = os.path.dirname(item["src_path"])
            out_path = os.path.splitext(item["src_path"])[0] + ".txt"
        else:
            stem = os.path.splitext(media.safe_filename(item["filename"]))[0]
            out_path = os.path.join(rt.output_dir, stem + ".txt")

        # 重跑时沿用原输出文件并覆盖，避免同一项目生成 _1/_2 副本
        prev_out = item.get("out_path")
        if prev_out and os.path.isfile(prev_out):
            out_path = prev_out
        else:
            out_path = media.write_text(out_path, text)
        if out_path == prev_out:
            os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(text)

        dur = round(time.time() - t0, 1)
        store.update_item(
            item["id"], status="done", text=text, out_path=out_path,
            chars=len(text), duration=dur, finished_at=time.time(),
        )
        _bump(rt, "done")
    except ApiError as e:
        store.update_item(
            item["id"], status="failed", error=e.message, duration=round(time.time() - t0, 1),
            finished_at=time.time(),
        )
        _bump(rt, "failed")
        if not e.retryable and e.status in (401, 403):
            # 密钥失效：整体暂停，避免继续烧请求
            rt.pause.set()
            store.update_job(rt.id, status="paused")
    except Exception as e:
        store.update_item(
            item["id"], status="failed", error=f"处理失败：{e}", duration=round(time.time() - t0, 1),
            finished_at=time.time(),
        )
        _bump(rt, "failed")
    finally:
        _maybe_finish(rt)


def _bump(rt: JobRuntime, key: str, delta: int = 1) -> None:
    with rt.lock:
        rt.counts[key] += delta


def _maybe_finish(rt: JobRuntime) -> None:
    if rt.standalone:
        return
    items = store.job_items(rt.id)
    if any(i["status"] in ("pending", "running") for i in items):
        return
    counts = Counter(i["status"] for i in items)
    status = "done"
    if rt.cancel.is_set():
        status = "cancelled"
    elif counts["failed"] and not counts["done"] and not counts["skipped"]:
        status = "error"
    _finish(rt, status)


def _finish(rt: JobRuntime, status: str) -> None:
    with rt.lock:
        if rt.finished:
            return
        rt.finished = True
    items = store.job_items(rt.id)
    counts = Counter(i["status"] for i in items)
    store.update_job(
        rt.id,
        status=status,
        finished_at=time.time(),
        done=counts["done"],
        failed=counts["failed"],
        skipped=counts["skipped"],
    )
    if rt.executor:
        rt.executor.shutdown(wait=False)
    _dump_results(rt)


def _csv_cell(value):
    """防 Excel 公式注入：以 = + - @ 开头的单元格前置单引号"""
    s = "" if value is None else str(value)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def _dump_results(rt: JobRuntime) -> None:
    """任务结束自动把清单落盘，方便直接交给客户/同事"""
    try:
        import csv
        items = store.job_items(rt.id)
        if not items:
            return
        os.makedirs(rt.output_dir, exist_ok=True)
        csv_path = os.path.join(rt.output_dir, "results.csv")
        # utf-8-sig：Excel 双击打开不乱码
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["序号", "文件", "状态", "字数", "耗时(秒)", "输出文件", "结果"])
            for it in items:
                w.writerow([
                    it["idx"] + 1, _csv_cell(it["filename"]), it["status"], it.get("chars") or 0,
                    it.get("duration") or 0, _csv_cell(it.get("out_path") or ""),
                    _csv_cell((it.get("text") or "").replace("\n", " ")),
                ])
        json_path = os.path.join(rt.output_dir, "results.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def run_single(item: dict, params: dict) -> None:
    """任务结束后单独重跑某一项（后台线程里执行，不阻塞接口）"""
    rt = JobRuntime(item.get("job_id", ""), params, 1)
    rt.standalone = True
    rt.output_dir = params.get("output_dir") or os.path.join(output_root(), "单项重跑")
    os.makedirs(rt.output_dir, exist_ok=True)
    rt.executor = None
    _run_item(rt, item)
    # 单项重跑不触发整任务收尾，但要把任务汇总和落盘清单刷新
    try:
        items = store.job_items(rt.id)
        counts = Counter(i["status"] for i in items)
        status = "running" if (counts["pending"] or counts["running"]) else (
            "error" if counts["failed"] and not counts["done"] else "done"
        )
        store.update_job(
            rt.id, status=status, done=counts["done"], failed=counts["failed"],
            skipped=counts["skipped"], finished_at=time.time() if status != "running" else None,
        )
        _dump_results(rt)
    except Exception:
        pass


def rerun_item(item_id: int) -> bool:
    """单项重跑：运行中的任务进线程池，已结束任务起后台线程，避免阻塞请求"""
    item = store.get_item(item_id)
    if not item:
        return False
    job = store.get_job(item["job_id"])
    if not job:
        return False
    try:
        params = json.loads(job.get("params") or "{}")
    except Exception:
        params = {}
    proc = {
        "filename": item["filename"], "src_path": item["src_path"],
        "media_type": item["media_type"], "id": item_id, "idx": item["idx"],
        "job_id": item["job_id"], "out_path": item.get("out_path"),
    }
    store.update_item(item_id, status="pending", error=None)
    rt = _runtimes.get(item["job_id"])
    if rt and rt.executor and not rt.finished:
        rt.executor.submit(_run_item, rt, proc)
        store.update_job(item["job_id"], status="running")
        return True
    threading.Thread(
        target=run_single, args=(proc, params),
        name=f"single-{item_id}", daemon=True,
    ).start()
    return True


# ---------------------------------------------------------------- 控制
def pause(job_id: str) -> bool:
    rt = _runtimes.get(job_id)
    if not rt or rt.finished:
        return False
    rt.pause.set()
    store.update_job(job_id, status="paused")
    return True


def resume(job_id: str) -> bool:
    rt = _runtimes.get(job_id)
    if not rt or rt.finished:
        return False
    rt.pause.clear()
    store.update_job(job_id, status="running")
    return True


def cancel(job_id: str) -> bool:
    rt = _runtimes.get(job_id)
    if not rt:
        return False
    rt.cancel.set()
    rt.pause.clear()
    store.cancel_pending(job_id)
    if rt.executor is not None:
        try:
            rt.executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
    # 未开始就被取消的 future 不会再执行，必须再落一次库，避免残留 pending
    store.cancel_pending(job_id)
    store.update_job(job_id, status="cancelled")
    # 若已没有在跑的线程，这里直接收尾并落盘清单
    _maybe_finish(rt)
    return True


def has_active(job_id: str = "") -> bool:
    """是否存在仍在运行的任务（用于删除/清空历史时保护）"""
    with _lock:
        if job_id:
            rt = _runtimes.get(job_id)
            return bool(rt and not rt.finished)
        return any(rt and not rt.finished for rt in _runtimes.values())


def retry_failed(job_id: str) -> int:
    rt = _runtimes.get(job_id)
    if not rt:
        # 程序重启后，历史任务没有内存态：按数据库参数重建
        job = store.get_job(job_id)
        if not job:
            return 0
        try:
            params = json.loads(job.get("params") or "{}")
        except Exception:
            params = {}
        rt = JobRuntime(job_id, params, job.get("total") or 0)
        rt.output_dir = params.get("output_dir") or os.path.join(output_root(), f"重试结果_{job_id[:6]}")
        rt.finished = False
        with _lock:
            _runtimes[job_id] = rt
        os.makedirs(rt.output_dir, exist_ok=True)

    rows = store.reset_failed_items(job_id)
    if not rows:
        return 0
    # 按数据库重建计数（尤其是程序重启后，内存计数已丢失）
    all_items = store.job_items(job_id)
    rebuilt = Counter({k: 0 for k in ("done", "failed", "skipped")})
    for it in all_items:
        st = it.get("status")
        if st in rebuilt:
            rebuilt[st] += 1
    with rt.lock:
        rt.counts = rebuilt
        rt.total = len(all_items)
        rt.finished = False
        rt.standalone = False
    rt.cancel.clear()
    rt.pause.clear()
    store.update_job(job_id, status="running")
    if rt.executor is not None:
        try:
            rt.executor.shutdown(wait=False)
        except Exception:
            pass
    rt.executor = ThreadPoolExecutor(
        max_workers=_safe_workers(rt.params.get("concurrency", 3)),
        thread_name_prefix=f"retry-{job_id[:6]}-",
    )
    for row in rows:
        rt.executor.submit(_run_item, rt, row)
    return len(rows)


def status(job_id: str):
    job = store.get_job(job_id)
    if not job:
        return None
    try:
        job["params"] = json.loads(job.get("params") or "{}")
    except Exception:
        job["params"] = {}
    items = store.job_items(job_id)
    counts = Counter(i["status"] for i in items)
    total = len(items)
    finished = counts["done"] + counts["failed"] + counts["skipped"] + counts["cancelled"]
    durations = [i["duration"] for i in items if i.get("duration")]
    avg = sum(durations) / len(durations) if durations else 0
    remaining = counts["pending"] + counts["running"]
    rt = _runtimes.get(job_id)
    conc = _safe_workers(job["params"].get("concurrency", 3)) if job.get("params") else 3

    eta = int(remaining * avg / max(1, conc)) if avg and remaining else 0
    return {
        "job": job,
        "items": items,
        "counts": {k: counts.get(k, 0) for k in ("pending", "running", "done", "failed", "skipped", "cancelled")},
        "progress": round(finished / total * 100, 1) if total else 0,
        "eta": eta,
        "elapsed": int(time.time() - job["created_at"]) if job["status"] in ("running", "paused") else int((job["finished_at"] or job["created_at"]) - job["created_at"]),
        "paused": bool(rt and rt.pause.is_set() and not rt.finished),
    }
