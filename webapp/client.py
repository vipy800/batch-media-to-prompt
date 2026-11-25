"""OpenAI 兼容的多模态接口客户端：重试、退避、错误归类"""
import json
import time
from urllib.parse import urlparse

import requests


def _num(value, default, lo, hi, as_float: bool = False):
    """配置里的数字可能是字符串/空值，统一兜底并夹紧范围"""
    try:
        n = float(value)
    except (TypeError, ValueError):
        n = float(default)
    n = max(lo, min(hi, n))
    return n if as_float else int(n)


class ApiError(Exception):
    def __init__(self, message: str, retryable: bool = False, status: int = 0):
        super().__init__(message)
        self.message = message
        self.retryable = retryable
        self.status = status


def is_local_url(base_url: str) -> bool:
    """本机 / 内网地址：通常不需要 API Key。

    注意：不能把所有明文 http 都当成本地地址，否则远端 http 接口也会被
    误判为免 Key，既跑不通也绕过了开跑前体检。
    """
    try:
        u = urlparse((base_url or "").strip())
    except Exception:
        return False
    host = (u.hostname or "").lower().strip("[]")
    if host in ("127.0.0.1", "localhost", "::1", "0.0.0.0"):
        return True
    if host.startswith("192.168.") or host.startswith("10."):
        return True
    if host.startswith("172."):
        try:
            second = int(host.split(".")[1])
        except (IndexError, ValueError):
            return False
        return 16 <= second <= 31
    return False


class VisionClient:
    def __init__(self, cfg: dict):
        self.api_key = (cfg.get("api_key") or "").strip()
        base = (cfg.get("base_url") or "https://api.siliconflow.cn/v1").strip().rstrip("/")
        # 用户可能直接粘贴完整 chat/completions 地址，避免拼出重复路径
        for suffix in ("/chat/completions", "/completions"):
            if base.lower().endswith(suffix):
                base = base[: -len(suffix)].rstrip("/")
        self.base_url = base
        self.timeout = _num(cfg.get("timeout", 600), 600, 10, 7200)
        self.max_retries = _num(cfg.get("max_retries", 3), 3, 1, 8)
        self.temperature = _num(cfg.get("temperature", 0.3), 0.3, 0, 2, as_float=True)
        self.max_tokens = _num(cfg.get("max_tokens", 4096), 4096, 64, 16384)
        self.system_prompt = cfg.get("system_prompt") or "你是专业的多模态分析助手。"

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/chat/completions"

    @property
    def is_local(self) -> bool:
        return is_local_url(self.base_url)

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _payload(self, prompt: str, images: list, model: str):
        content = [{"type": "text", "text": prompt}] if prompt else []
        for url in images:
            content.append({"type": "image_url", "image_url": {"url": url}})
        return {
            "model": model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": content},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }

    def analyze(self, prompt: str, images: list, model: str, max_retries: int = None) -> str:
        if not self.api_key and not self.is_local:
            raise ApiError("未配置 API Key，请先在设置中填写", retryable=False, status=401)
        if not images:
            raise ApiError("没有可用的图像数据", retryable=False)
        retries = self.max_retries if max_retries is None else max_retries
        payload = self._payload(prompt, images, model)
        headers = self._headers()

        last_err = None
        for attempt in range(retries):
            t0 = time.time()
            try:
                resp = requests.post(
                    self.endpoint, headers=headers, data=json.dumps(payload),
                    timeout=(15, self.timeout),
                )
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices") or []
                    if choices and choices[0].get("message"):
                        text = choices[0]["message"].get("content") or ""
                        if text.strip():
                            return text.strip()
                        raise ApiError("接口返回内容为空", retryable=True)
                    raise ApiError("接口返回格式异常", retryable=True)

                body = resp.text[:400]
                if resp.status_code in (401, 403):
                    raise ApiError("API Key 无效或无权限，请检查密钥", retryable=False, status=resp.status_code)
                if resp.status_code == 404:
                    raise ApiError(f"接口地址或模型不存在：{body}", retryable=False, status=404)
                if resp.status_code == 429:
                    try:
                        wait = float(resp.headers.get("Retry-After") or 5)
                    except (TypeError, ValueError):
                        wait = 5.0
                    last_err = ApiError("触发限流（429），稍后重试", retryable=True, status=429)
                    time.sleep(min(30, max(2, wait)))
                    continue
                if resp.status_code >= 500:
                    last_err = ApiError(f"服务端错误 {resp.status_code}", retryable=True, status=resp.status_code)
                elif 400 <= resp.status_code < 500:
                    raise ApiError(f"请求被拒绝（{resp.status_code}）：{body}", retryable=False, status=resp.status_code)
                else:
                    last_err = ApiError(f"未知响应 {resp.status_code}", retryable=True)

            except ApiError:
                raise
            except requests.exceptions.Timeout:
                last_err = ApiError(f"请求超时（{self.timeout}s）", retryable=True)
            except requests.exceptions.ConnectionError as e:
                last_err = ApiError(f"网络连接失败：{e}", retryable=True)
            except Exception as e:
                last_err = ApiError(f"调用异常：{e}", retryable=True)

            if attempt < retries - 1 and isinstance(last_err, ApiError) and last_err.retryable:
                time.sleep(min(20, 2 ** attempt))
                continue
            break

        raise last_err or ApiError("调用失败", retryable=True)

    def test(self, model: str) -> dict:
        """连通性测试"""
        t0 = time.time()
        try:
            resp = requests.post(
                self.endpoint,
                headers=self._headers(),
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "回复：连接成功"}],
                    "max_tokens": 16,
                    "temperature": 0,
                },
                timeout=(10, 60),
            )
            if resp.status_code == 200:
                data = resp.json()
                reply = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
                return {"ok": True, "reply": (reply or "").strip(), "ms": int((time.time() - t0) * 1000)}
            return {"ok": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}", "ms": int((time.time() - t0) * 1000)}
        except Exception as e:
            return {"ok": False, "error": str(e), "ms": int((time.time() - t0) * 1000)}
