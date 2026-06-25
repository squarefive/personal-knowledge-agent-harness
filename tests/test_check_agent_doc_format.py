from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_check_agent_doc_format_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "check-agent-doc-format.py"
    spec = importlib.util.spec_from_file_location("check_agent_doc_format", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_agent_doc_length_warning_does_not_return_error():
    module = load_check_agent_doc_format_module()
    content = "\n".join(["line"] * (module.AGENT_DOC_RECOMMENDED_MAX_LINES + 1))

    warnings = module.check_agent_doc_length(Path("docs/agents/example.md"), content)

    assert warnings == [
        "docs/agents/example.md has 1001 lines, exceeds recommended limit 1000; "
        "please consolidate content within the existing agent document template"
    ]
