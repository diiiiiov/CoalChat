from __future__ import annotations

from backend_fastapi import document_registry as registry


def test_document_registry_tracks_versions_and_status(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(registry, "KNOWLEDGE_ROOT", tmp_path)

    first, changed = registry.register_upload("test-kb", "rules.md", "a" * 64, 10, 300, 50)
    assert changed is True
    assert first["version"] == 1

    unchanged, changed = registry.register_upload("test-kb", "rules.md", "a" * 64, 10, 300, 50)
    assert changed is False
    assert unchanged["version"] == 1

    second, changed = registry.register_upload("test-kb", "rules.md", "b" * 64, 12, 400, 80)
    assert changed is True
    assert second["version"] == 2
    assert second["document_id"] == ("b" * 24)

    registry.update_status(
        "test-kb",
        ["rules.md"],
        "indexed",
        index_version="v2",
        chunk_counts={"rules.md": 7},
        block_summaries={"rules.md": {"text": 3, "table": 1}},
    )
    listed = registry.list_documents("test-kb")
    assert listed[0]["status"] == "indexed"
    assert listed[0]["chunk_count"] == 7
    assert listed[0]["block_summary"] == {"text": 3, "table": 1}

    removed = registry.remove_document("test-kb", "rules.md")
    assert removed and removed["version"] == 2
    assert registry.list_documents("test-kb") == []
