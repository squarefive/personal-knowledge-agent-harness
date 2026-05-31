import pytest

from personal_knowledge_agent.agent_memory import MemoryIndexStore


def test_load_memory_index_returns_empty_when_missing(tmp_path):
    store = MemoryIndexStore(tmp_path)

    index = store.load()

    assert index.entries == []


def test_load_memory_index_reads_markdown_table(tmp_path):
    memory_dir = tmp_path / ".memory"
    memory_dir.mkdir()
    (memory_dir / "MEMORY.md").write_text(
        "\n".join(
            [
                "# Memory Index",
                "",
                "| name | type | description | path |",
                "|---|---|---|---|",
                "| project-boundary | project | Project boundary memory | .memory/project-boundary.md |",
            ]
        ),
        encoding="utf-8",
    )

    index = MemoryIndexStore(tmp_path).load()

    assert len(index.entries) == 1
    assert index.entries[0].name == "project-boundary"
    assert index.entries[0].type == "project"
    assert index.entries[0].description == "Project boundary memory"
    assert index.entries[0].path == ".memory/project-boundary.md"


def test_load_memory_index_rejects_missing_required_columns(tmp_path):
    memory_dir = tmp_path / ".memory"
    memory_dir.mkdir()
    (memory_dir / "MEMORY.md").write_text(
        "\n".join(
            [
                "# Memory Index",
                "",
                "| name | type | path |",
                "|---|---|---|",
                "| project-boundary | project | .memory/project-boundary.md |",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing required columns"):
        MemoryIndexStore(tmp_path).load()


def test_load_memory_index_rejects_invalid_type(tmp_path):
    memory_dir = tmp_path / ".memory"
    memory_dir.mkdir()
    (memory_dir / "MEMORY.md").write_text(
        "\n".join(
            [
                "# Memory Index",
                "",
                "| name | type | description | path |",
                "|---|---|---|---|",
                "| project-boundary | temporary | Project boundary memory | .memory/project-boundary.md |",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="memory type"):
        MemoryIndexStore(tmp_path).load()
