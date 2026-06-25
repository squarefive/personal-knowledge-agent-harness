#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENTS_PATH = ROOT / "AGENTS.md"
REQUIRED_H1 = "# AI Coding 工作入口"
AGENTS_MD_RECOMMENDED_MAX_LINES = 500

REQUIRED_MARKERS = [
    "本地文档和协作规约的一级目录",
    "不承载具体 Agent 的完整设计边界",
    "代码实现方案",
    "单次任务计划",
    "正文目录层级最多到二级标题",
    "超过 500 行时",
]


@dataclass(frozen=True)
class Heading:
    level: int
    text: str
    raw: str


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def collect_headings(content: str) -> list[Heading]:
    headings: list[Heading] = []
    for line in content.splitlines():
        match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if not match:
            continue
        headings.append(
            Heading(level=len(match.group(1)), text=match.group(2).strip(), raw=line)
        )
    return headings


def check_agents_md_content(content: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    headings = collect_headings(content)

    h1_headings = [heading for heading in headings if heading.level == 1]
    if len(h1_headings) != 1:
        errors.append("AGENTS.md must contain exactly one H1 heading")
    elif h1_headings[0].raw != REQUIRED_H1:
        errors.append("AGENTS.md H1 must be '# AI Coding 工作入口'")

    for heading in headings:
        if heading.level >= 3:
            errors.append(f"AGENTS.md must not use headings deeper than ##: {heading.raw}")

    for marker in REQUIRED_MARKERS:
        if marker not in content:
            errors.append(f"missing required marker: {marker}")

    line_count = len(content.splitlines())
    if line_count > AGENTS_MD_RECOMMENDED_MAX_LINES:
        warnings.append(
            f"AGENTS.md has {line_count} lines, exceeds recommended limit "
            f"{AGENTS_MD_RECOMMENDED_MAX_LINES}; please consolidate entry rules"
        )

    return errors, warnings


def check_agents_md(path: Path) -> tuple[list[str], list[str]]:
    if not path.exists():
        return [f"{rel(path)} does not exist"], []
    return check_agents_md_content(read_text(path))


def main() -> int:
    parser = argparse.ArgumentParser(description="Check AGENTS.md entry document format.")
    parser.add_argument(
        "target",
        nargs="?",
        default=str(AGENTS_PATH),
        help="AGENTS.md file to check. Defaults to repository AGENTS.md.",
    )
    args = parser.parse_args()

    target = Path(args.target)
    if not target.is_absolute():
        target = ROOT / target

    errors, warnings = check_agents_md(target)
    if errors:
        print(f"[fail] {rel(target)}")
    else:
        print(f"[pass] {rel(target)}")

    if warnings:
        print("\nWarnings:")
        for warning in warnings:
            print(f"- {warning}")

    if errors:
        print("\nErrors:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("\nChecked 1 file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
