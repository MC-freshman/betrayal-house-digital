"""联机主机（房主电脑 / 云服务器）启动入口。

用法：
    python -m game.net.host_app --port 8765
"""
from __future__ import annotations

import argparse

try:
    from game.net.server import GameHost
except ImportError:  # pragma: no cover - direct script execution
    from net.server import GameHost  # type: ignore


def main() -> None:
    parser = argparse.ArgumentParser(description="《山中小屋》联机主机")
    parser.add_argument("--port", type=int, default=8765, help="监听端口（默认 8765）")
    parser.add_argument("--password", default="", help="可选房间口令（留空则无需口令）")
    args = parser.parse_args()

    host = GameHost(port=args.port, password=args.password)
    host.start()
    try:
        host.run_loop()
    except KeyboardInterrupt:
        print("\n[主机] 正在关闭…")
    finally:
        host.stop()


if __name__ == "__main__":
    main()
