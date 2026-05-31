import pytest

from personal_knowledge_agent.agent_memory import MemoryStore
from personal_knowledge_agent.schemas import MemoryIndexEntry


def test_read_memory_document_with_frontmatter(tmp_path):
    memory_dir = tmp_path / ".memory"
    memory_dir.mkdir()
    (memory_dir / "project-boundary.md").write_text(
        "\n".join(
            [
                "---",
                'name: "project-boundary"',
                'type: "project"',
                'description: "Project boundary memory"',
                'updated_at: "2026-05-31"',
                'source_type: "user_decision"',
                'source_ref: "conversation:2026-05-31"',
                "---",
                "",
                "Q&A 知识库和 Agent memory 必须分开。",
            ]
        ),
        encoding="utf-8",
    )

    memory = MemoryStore(tmp_path).read_path(".memory/project-boundary.md")

    assert memory.name == "project-boundary"
    assert memory.type == "project"
    assert memory.description == "Project boundary memory"
    assert memory.path == ".memory/project-boundary.md"
    assert memory.updated_at == "2026-05-31"
    assert memory.source_type == "user_decision"
    assert memory.source_ref == "conversation:2026-05-31"
    assert memory.content == "Q&A 知识库和 Agent memory 必须分开。"


def test_read_memory_document_by_index_entry(tmp_path):
    memory_dir = tmp_path / ".memory"
    memory_dir.mkdir()
    (memory_dir / "reference-doc.md").write_text(
        "\n".join(
            [
                "---",
                'name: "reference-doc"',
                'type: "reference"',
                'description: "Agent doc path"',
                'updated_at: "2026-05-31"',
                'source_type: "reference"',
                "---",
                "",
                "Agent 设计文档位于 docs/agents/local-qa-knowledge-agent.md。",
            ]
        ),
        encoding="utf-8",
    )
    entry = MemoryIndexEntry(
        name="reference-doc",
        type="reference",
        description="Agent doc path",
        path=".memory/reference-doc.md",
    )

    memory = MemoryStore(tmp_path).read_by_entry(entry)

    assert memory.name == "reference-doc"
    assert memory.source_ref is None


def test_read_memory_document_rejects_missing_frontmatter(tmp_path):
    memory_dir = tmp_path / ".memory"
    memory_dir.mkdir()
    (memory_dir / "broken.md").write_text("missing frontmatter", encoding="utf-8")

    with pytest.raises(ValueError, match="frontmatter"):
        MemoryStore(tmp_path).read_path(".memory/broken.md")


def test_read_memory_document_rejects_invalid_type(tmp_path):
    memory_dir = tmp_path / ".memory"
    memory_dir.mkdir()
    (memory_dir / "broken.md").write_text(
        "\n".join(
            [
                "---",
                'name: "broken"',
                'type: "session"',
                'description: "Invalid type"',
                'updated_at: "2026-05-31"',
                'source_type: "user_decision"',
                "---",
                "",
                "content",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="memory type"):
        MemoryStore(tmp_path).read_path(".memory/broken.md")


def test_read_memory_document_rejects_missing_required_field(tmp_path):
    memory_dir = tmp_path / ".memory"
    memory_dir.mkdir()
    (memory_dir / "broken.md").write_text(
        "\n".join(
            [
                "---",
                'name: "broken"',
                'type: "project"',
                'updated_at: "2026-05-31"',
                'source_type: "user_decision"',
                "---",
                "",
                "content",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="description"):
        MemoryStore(tmp_path).read_path(".memory/broken.md")


def test_read_memory_document_rejects_absolute_path(tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_text("outside", encoding="utf-8")

    with pytest.raises(ValueError, match="relative"):
        MemoryStore(tmp_path).read_path(outside)


def test_read_memory_document_rejects_path_traversal(tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_text("outside", encoding="utf-8")

    with pytest.raises(ValueError, match="under .memory"):
        MemoryStore(tmp_path).read_path(".memory/../outside.md")
