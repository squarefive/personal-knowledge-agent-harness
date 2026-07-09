from __future__ import annotations

from .apps.cli.cli_main import main

__all__ = ["main"]


if __name__ == "__main__":
    raise SystemExit(main())
