#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "docs/templates/codebase-map.template.md"
MAP_PATH = ROOT / "docs/architecture/codebase-map.md"
EXPECTED_TEMPLATE_SHA256 = "8d0994e007732781906296f8beddded1bac7aa085f36cc3739abb6e13500000a"

REQUIRED_FRONTMATTER_FIELDS = [
    "title",
    "last_updated",
]

REQUIRED_SECTIONS = [
    "## 目录说明",
    "## 文件说明",
]

REQUIRED_TEMPLATE_PLACEHOLDERS = [
    "{{project_name}}",
    "{{YYYY-MM-DD}}",
    "{{dir_path}}",
    "{{module_name}}",
    "{{module_dir}}",
    "{{file_path}}",
]

DIRECTORY_TABLE_HEADER = "| 目录 | 作用 |"
FILE_TABLE_HEADER = "| 文件 | 作用 |"


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
    if not re.search(r"^# .+ 代码地图$", content, re.MULTILINE):
        errors.append("missing H1 title matching '# ... 代码地图'")

    for section in REQUIRED_SECTIONS:
        if section not in content:
            errors.append(f"missing required section: {section}")

    if DIRECTORY_TABLE_HEADER not in content:
        errors.append(f"missing directory table header: {DIRECTORY_TABLE_HEADER}")
    if FILE_TABLE_HEADER not in content:
        errors.append(f"missing file table header: {FILE_TABLE_HEADER}")
    return errors


def check_module_sections(content: str) -> list[str]:
    errors: list[str] = []
    file_section_index = content.find("## 文件说明")
    if file_section_index == -1:
        return ["missing file description section"]

    file_section = content[file_section_index:]
    module_matches = list(re.finditer(r"^### .+$", file_section, re.MULTILINE))
    if not module_matches:
        return ["file descriptions must be grouped by module with '### ...' headings"]

    for index, match in enumerate(module_matches):
        start = match.end()
        end = module_matches[index + 1].start() if index + 1 < len(module_matches) else len(file_section)
        module_block = file_section[start:end]
        module_title = match.group(0)
        if "模块目录：" not in module_block:
            errors.append(f"{module_title}: missing 模块目录")
        if "模块作用：" not in module_block:
            errors.append(f"{module_title}: missing 模块作用")
        if FILE_TABLE_HEADER not in module_block:
            errors.append(f"{module_title}: missing file table header")
    return errors


def check_template_doc(path: Path) -> list[str]:
    content = read_text(path)
    errors = check_frontmatter(content, validate_values=False)
    errors.extend(check_common_structure(content))
    errors.extend(check_module_sections(content))

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


def check_codebase_map_doc(path: Path) -> list[str]:
    content = read_text(path)
    errors = check_frontmatter(content, validate_values=True)
    errors.extend(check_common_structure(content))
    errors.extend(check_module_sections(content))

    if re.search(r"\{\{[^}]+\}\}", content):
        errors.append("template placeholders must be filled before committing")
    return errors


def resolve_target(target: str) -> tuple[list[Path], list[str]]:
    path = (ROOT / target).resolve() if not Path(target).is_absolute() else Path(target)
    errors: list[str] = []

    if path in {TEMPLATE_PATH, MAP_PATH}:
        return [path], errors

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
    return [str(TEMPLATE_PATH), str(MAP_PATH)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Check codebase map template and docs format.")
    parser.add_argument(
        "targets",
        nargs="*",
        help="Files or directories to check. Defaults to template and docs/architecture/codebase-map.md.",
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

    for path in unique_files:
        checked += 1
        path_errors = check_template_doc(path) if path == TEMPLATE_PATH else check_codebase_map_doc(path)
        if path_errors:
            errors.extend(f"{rel(path)}: {error}" for error in path_errors)
            print(f"[fail] {rel(path)}")
        else:
            print(f"[pass] {rel(path)}")

    if errors:
        print("\nErrors:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"\nChecked {checked} file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
