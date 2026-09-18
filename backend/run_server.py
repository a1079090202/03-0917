"""生产启动入口（由 start.bat 调用）：

- 首次启动自动建库 + 播种演示数据；
- 打印本机局域网地址，门店浏览器用它访问；
- 起 uvicorn，同源托管前端构建产物与 /api。
"""
import argparse
import socket
import threading
import webbrowser

import uvicorn

from app.config import DB_PATH
from app.seed import build


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--open", action="store_true", help="启动后自动开浏览器")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print("首次启动：建库并写入演示数据……")
        build()

    ip = lan_ip()
    print("=" * 62)
    print(" 批号效期台账已启动")
    print(f"  总仓本机访问：  http://127.0.0.1:{args.port}")
    print(f"  8 家门店访问：  http://{ip}:{args.port}")
    print(" （门店打不开时，请在 Windows 防火墙放行本端口的专用网络）")
    print(" 关闭服务：直接关掉本黑窗口即可")
    print("=" * 62)

    if args.open:
        threading.Timer(1.5, lambda: webbrowser.open(f"http://127.0.0.1:{args.port}")).start()

    uvicorn.run("app.main:app", host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
