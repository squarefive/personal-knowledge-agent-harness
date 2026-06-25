from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_check_agents_md_format_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "check-agents-md-format.py"
    spec = importlib.util.spec_from_file_location("check_agents_md_format", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def valid_content() -> str:
    return "\n".join(
        [
            "# AI Coding 工作入口",
            "",
            "本文档是本仓库面向 AI Coding 工具的工作入口，也是本地文档和协作规约的一级目录。",
            "",
            "它不承载具体 Agent 的完整设计边界、代码实现方案、单次任务计划、临时决策或工作进度。",
            "",
            "正文目录层级最多到二级标题（`##`）。",
            "",
            "超过 500 行时，检查脚本应给出告警。",
            "",
            "## 协作规约",
            "",
            "说明协作规约的作用、读取时机、不需要读取的场景，以及不能替代哪些其他文档。",
        ]
    )


def test_valid_agents_md_passes_without_warnings():
    module = load_check_agents_md_format_module()

    errors, warnings = module.check_agents_md_content(valid_content())

    assert errors == []
    assert warnings == []


def test_third_level_heading_fails():
    module = load_check_agents_md_format_module()

    errors, _ = module.check_agents_md_content(valid_content() + "\n\n### 细节")

    assert "AGENTS.md must not use headings deeper than ##: ### 细节" in errors


def test_multiple_h1_headings_fail():
    module = load_check_agents_md_format_module()

    errors, _ = module.check_agents_md_content(valid_content() + "\n\n# Another")

    assert "AGENTS.md must contain exactly one H1 heading" in errors


def test_missing_required_marker_fails():
    module = load_check_agents_md_format_module()

    errors, _ = module.check_agents_md_content(valid_content().replace("代码实现方案、", ""))

    assert "missing required marker: 代码实现方案" in errors


def test_over_500_lines_warns_without_error():
    module = load_check_agents_md_format_module()
    content = valid_content() + "\n" + "\n".join(
        ["filler"] * (module.AGENTS_MD_RECOMMENDED_MAX_LINES + 1)
    )

    errors, warnings = module.check_agents_md_content(content)

    assert errors == []
    assert warnings == [
        "AGENTS.md has 514 lines, exceeds recommended limit 500; "
        "please consolidate entry rules"
    ]
