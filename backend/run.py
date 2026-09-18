"""一键启动：建库 -> 空库灌种子 -> 起服务 -> 自动开浏览器。.bat 启动器调的就是它。"""
import os
import socket
import sys
import threading
import time
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import PORT  # noqa: E402
from app.database import init_db  # noqa: E402
from app.seed import seed_if_empty  # noqa: E402


def _lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "本机IP"


def _open_browser():
    time.sleep(2)
    webbrowser.open(f"http://127.0.0.1:{PORT}")


def main():
    init_db()
    if seed_if_empty():
        print("[初始化] 空库 detected，已灌入演示数据（15 药品 / 30 批次 / 8 门店 / 近三月流水）", flush=True)
    print("=" * 60, flush=True)
    print(f"  总仓本机访问：  http://127.0.0.1:{PORT}", flush=True)
    print(f"  门店电脑访问：  http://{_lan_ip()}:{PORT}   （同一局域网内浏览器直接打开）", flush=True)
    print("=" * 60, flush=True)
    threading.Thread(target=_open_browser, daemon=True).start()

    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=PORT, reload=False)


if __name__ == "__main__":
    main()
