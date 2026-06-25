#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "docs/templates/agent-development-context.template.md"
AGENTS_DIR = ROOT / "docs/agents"
EXPECTED_TEMPLATE_SHA256 = "830c7d9fab94f5af06d4709a9b0ccadf7c77fc34635c852d504ca04b70511db8"

REQUIRED_FRONTMATTER_FIELDS = [
    "module",
    "title",
    "language",
    "agent_type",
    "last_updated",
]

REQUIRED_SECTIONS = [
    "## 1. Agent 定位与能力边界",
    "## 2. Harness 架构与代码边界",
    "## 3. 可调用工具与工具契约",
    "## 4. 上下文来源与记忆边界",
    "## 5. 核心业务流",
    "## 6. 数据模型",
    "## 7. 失败模式与降级策略",
    "## 8. 测试要求",
    "## 9. 变更记录",
]

REQUIRED_KEY_AREAS = [
    "### 3.1 工具列表",
    "### 3.2 工具契约",
    "## 6. 数据模型",
    "## 7. 失败模式与降级策略",
    "## 8. 测试要求",
    "## 9. 变更记录",
]

REQUIRED_TEMPLATE_PLACEHOLDERS = [
    "{{module_name}}",
    "{{agent_chinese_name}}",
    "{{YYYY-MM-DD}}",
]

AGENT_DOC_RECOMMENDED_MAX_LINES = 1000


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def template_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract_frontmatter(content: str) -> tuple[dict[str, str], list[str]]:
    errors: list[str] = []
    if not content.startswith("---\n"):
        return {}, ["missing YAML frontmatter"]

    end = content.find("\n---\n", 4)
    if end == -1:
        return {}, ["YAML frontmatter is not closed"]

    fields: dict[str, str] = {}
    for line in content[4:end].splitlines():
        if not line.strip():
            continue
        if ":" not in line:
            errors.append(f"invalid frontmatter line: {line}")
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip().strip('"')
    return fields, errors


def check_frontmatter(content: str, validate_values: bool) -> list[str]:
    fields, errors = extract_frontmatter(content)
    for field in REQUIRED_FRONTMATTER_FIELDS:
        if field not in fields:
            errors.append(f"missing frontmatter field: {field}")

    if validate_values:
        last_updated = fields.get("last_updated", "")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", last_updated):
            errors.append("frontmatter field last_updated must match YYYY-MM-DD")

        for field in REQUIRED_FRONTMATTER_FIELDS:
            value = fields.get(field, "")
            if not value:
                errors.append(f"frontmatter field {field} must not be empty")
    return errors


def check_common_structure(content: str) -> list[str]:
    errors: list[str] = []
    for marker in ["文档定位", "AI 阅读契约"]:
        if marker not in content:
            errors.append(f"missing required marker: {marker}")

    for section in REQUIRED_SECTIONS:
        if section not in content:
            errors.append(f"missing required section: {section}")

    for area in REQUIRED_KEY_AREAS:
        if area not in content:
            errors.append(f"missing required key area: {area}")
    return errors


def check_template_doc(path: Path) -> list[str]:
    content = read_text(path)
    errors = check_frontmatter(content, validate_values=False)
    errors.extend(check_common_structure(content))

    for placeholder in REQUIRED_TEMPLATE_PLACEHOLDERS:
        if placeholder not in content:
            errors.append(f"missing required template placeholder: {placeholder}")

    actual_hash = template_hash(path)
    if actual_hash != EXPECTED_TEMPLATE_SHA256:
        errors.append(
            "template sha256 mismatch: "
            f"expected {EXPECTED_TEMPLATE_SHA256}, got {actual_hash}"
        )
    return errors


def check_agent_doc(path: Path) -> list[str]:
    content = read_text(path)
    errors = check_frontmatter(content, validate_values=True)
    errors.extend(check_common_structure(content))

    if not re.search(r"^# .+ Agent 开发上下文$", content, re.MULTILINE):
        errors.append("missing H1 title matching '# ... Agent 开发上下文'")

    if re.search(r"\{\{[^}]+\}\}", content):
        errors.append("template placeholders must be filled before committing")
    return errors


def check_agent_doc_length(path: Path, content: str) -> list[str]:
    line_count = len(content.splitlines())
    if line_count <= AGENT_DOC_RECOMMENDED_MAX_LINES:
        return []
    display_path = rel(path).replace("\\", "/")
    return [
        f"{display_path} has {line_count} lines, exceeds recommended limit "
        f"{AGENT_DOC_RECOMMENDED_MAX_LINES}; please consolidate content within "
        "the existing agent document template"
    ]


def resolve_target(target: str) -> tuple[list[Path], list[str]]:
    path = (ROOT / target).resolve() if not Path(target).is_absolute() else Path(target)
    errors: list[str] = []

    if path == TEMPLATE_PATH:
        return [TEMPLATE_PATH], errors

    if path == AGENTS_DIR:
        if not AGENTS_DIR.exists():
            print(f"[info] {rel(AGENTS_DIR)} does not exist; no agent docs found")
            return [], errors
        files = sorted(AGENTS_DIR.glob("*.md"))
        if not files:
            print(f"[info] no agent docs found in {rel(AGENTS_DIR)}")
        return files, errors

    if path.is_dir():
        files = sorted(path.glob("*.md"))
        if not files:
            print(f"[info] no markdown files found in {rel(path)}")
        return files, errors

    if path.is_file() and path.suffix == ".md":
        return [path], errors

    errors.append(f"target is not a markdown file or directory: {target}")
    return [], errors


def default_targets() -> list[str]:
    return [str(TEMPLATE_PATH), str(AGENTS_DIR)]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check Agent development context template and docs format."
    )
    parser.add_argument(
        "targets",
        nargs="*",
        help="Files or directories to check. Defaults to template and docs/agents/*.md.",
    )
    args = parser.parse_args()

    targets = args.targets or default_targets()
    files: list[Path] = []
    errors: list[str] = []

    for target in targets:
        target_files, target_errors = resolve_target(target)
        files.extend(target_files)
        errors.extend(target_errors)

    unique_files = sorted(set(files))
    checked = 0
    warnings: list[str] = []

    for path in unique_files:
        checked += 1
        path_errors = (
            check_template_doc(path) if path == TEMPLATE_PATH else check_agent_doc(path)
        )
        if path != TEMPLATE_PATH:
            warnings.extend(check_agent_doc_length(path, read_text(path)))
        if path_errors:
            errors.extend(f"{rel(path)}: {error}" for error in path_errors)
            print(f"[fail] {rel(path)}")
        else:
            print(f"[pass] {rel(path)}")

    if warnings:
        print("\nWarnings:")
        for warning in warnings:
            print(f"- {warning}")

    if errors:
        print("\nErrors:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"\nChecked {checked} file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
