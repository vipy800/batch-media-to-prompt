"""日志初始化：滚动日志 + 屏蔽断连异常刷屏"""
import logging
import os
from logging.handlers import RotatingFileHandler

_configured = False


class _AsyncioNoiseFilter(logging.Filter):
    _NOISE = ("ConnectionResetError", "ConnectionAbortedError", "_read_from_self", "远程主机强迫关闭")

    def filter(self, record):
        if record.name == "asyncio":
            msg = str(record.getMessage())
            if any(k in msg for k in self._NOISE):
                return False
        return True


def setup_logging(base_dir: str) -> logging.Logger:
    global _configured
    logger = logging.getLogger("media")
    if _configured:
        return logger

    handler = RotatingFileHandler(
        os.path.join(base_dir, "app.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
        delay=True,
    )
    stream = logging.StreamHandler()
    fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in (handler, stream):
        h.setFormatter(fmt)
        root.addHandler(h)

    logging.getLogger("asyncio").addFilter(_AsyncioNoiseFilter())
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    _configured = True
    return logger


def asyncio_exception_handler(loop, context):
    exc = context.get("exception")
    if isinstance(exc, (ConnectionResetError, ConnectionAbortedError)):
        logging.getLogger("media").debug("客户端连接已断开")
        return
    loop.default_exception_handler(context)
