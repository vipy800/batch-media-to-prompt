"""启动入口：源码运行与打包版共用"""
import os
import socket
import sys
import threading
import time
import webbrowser

PORT = int(os.getenv("MEDIA_PORT", "8888"))
HOST = "127.0.0.1"


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex((HOST, port)) == 0


def free_port(start: int) -> int:
    p = start
    while p < start + 40 and port_in_use(p):
        p += 1
    return p


SELFCHECK = "--selfcheck" in sys.argv


def open_browser_later(port: int, delay: float = 1.8, suffix: str = ""):
    def _open():
        time.sleep(delay)
        try:
            webbrowser.open(f"http://{HOST}:{port}/{suffix}")
        except Exception:
            pass

    threading.Thread(target=_open, daemon=True).start()


def main():
    import uvicorn

    from webapp.main import app

    port = free_port(PORT)
    print("=" * 56)
    print("  全能媒体反推 · 商用版")
    print(f"  服务地址: http://{HOST}:{port}/")
    print("  关闭窗口或按 Ctrl+C 结束程序")
    print("=" * 56)
    if SELFCHECK:
        print("  自检模式：浏览器会自动打开「设置 → 自检」并跑一遍")
    if os.getenv("MEDIA_NO_BROWSER") != "1":
        open_browser_later(port, suffix="?selfcheck=1" if SELFCHECK else "")
    uvicorn.run(app, host=HOST, port=port, log_level="info", access_log=False)


if __name__ == "__main__":
    main()
