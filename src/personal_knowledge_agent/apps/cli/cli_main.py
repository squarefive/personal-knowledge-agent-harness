from __future__ import annotations

import sys

from .constants import CliConstants as cli_constants


def run_cli() -> int:
    print("本地 CLI Agent runtime 已移除；请使用 `pka web` 或 `./run-web` 启动 cloud-only Web runtime。")
    return 1


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == [cli_constants.WEB_COMMAND]:
        from ..web.web_main import main as web_main

        return web_main(args[1:])
    return run_cli()


if __name__ == "__main__":
    raise SystemExit(main())
