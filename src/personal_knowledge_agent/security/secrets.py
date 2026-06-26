from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping


def read_secret(
    name: str,
    *,
    required: bool = False,
    environ: Mapping[str, str] | None = None,
) -> str | None:
    env = environ if environ is not None else os.environ
    file_name = f"{name}_FILE"
    secret_file = env.get(file_name)
    if secret_file:
        value = _read_secret_file(name, Path(secret_file))
    else:
        value = env.get(name)

    if value == "":
        raise ValueError(f"{name} is empty")
    if required and value is None:
        raise ValueError(f"{name} is required")
    return value


def _read_secret_file(name: str, path: Path) -> str:
    try:
        value = path.read_text(encoding="utf-8").rstrip("\r\n")
    except FileNotFoundError as exc:
        raise ValueError(f"{name}_FILE does not exist: {path}") from exc

    if value == "":
        raise ValueError(f"{name}_FILE is empty: {path}")
    return value
