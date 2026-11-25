"""一键打包免安装版（onedir）。由 build.bat 调用，避免 bat 里的中文编码问题。"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
NAME = "全能媒体反推"


def run(cmd):
    print(">", " ".join(cmd))
    return subprocess.call(cmd, cwd=ROOT)


def main():
    print("=" * 56)
    print("  Build portable package")
    print("=" * 56)
    if run([sys.executable, "-m", "PyInstaller", "--version"]) != 0:
        print("Installing PyInstaller ...")
        if run([sys.executable, "-m", "pip", "install", "pyinstaller", "--disable-pip-version-check"]) != 0:
            print("[ERROR] PyInstaller install failed. Check network.")
            return 1

    for folder in ("build", "dist"):
        target = os.path.join(ROOT, folder)
        if os.path.isdir(target):
            shutil.rmtree(target, ignore_errors=True)

    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onedir", "--console",
        "--name", NAME,
        "--icon", "app.ico",
        "--add-data", "webapp/templates;webapp/templates",
        "--add-data", "webapp/static;webapp/static",
        "--collect-submodules", "webapp",
        "--exclude-module", "matplotlib",
        "--exclude-module", "pandas",
        "--exclude-module", "scipy",
        "--exclude-module", "IPython",
        "--hidden-import", "uvicorn.logging",
        "--hidden-import", "uvicorn.loops.auto",
        "--hidden-import", "uvicorn.protocols.http.auto",
        "--hidden-import", "uvicorn.protocols.http.h11_impl",
        "--hidden-import", "uvicorn.protocols.websockets.auto",
        "--hidden-import", "uvicorn.lifespan.on",
        "run.py",
    ]
    if run(args) != 0:
        print("[ERROR] Build failed.")
        return 1

    out = os.path.join(ROOT, "dist", NAME)
    for src, dst in (
        ("使用说明-v4.0.txt", "使用说明.txt"),
        ("自检.bat", "自检.bat"),
        ("客户速查卡-A4.pdf", "客户速查卡-A4.pdf"),
    ):
        s = os.path.join(ROOT, src)
        if os.path.exists(s):
            shutil.copy2(s, os.path.join(out, dst))
    print("")
    print("[OK] Done:", out)
    print("     Run %s.exe" % NAME)
    return 0


if __name__ == "__main__":
    sys.exit(main())
