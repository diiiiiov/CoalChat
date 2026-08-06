from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend_fastapi.document_blocks import parse_document, persist_blocks


FIXTURES = Path(__file__).parent / "fixtures"


def _stable_block(block) -> dict:
    value = block.to_dict()
    return {
        "block_type": value["block_type"],
        "content": value["content"],
        "page": value["page"],
        "section_title": value["section_title"],
        "metadata": value["metadata"],
    }


@pytest.mark.parametrize("filename", ["safety.md", "limits.csv"])
def test_document_parser_matches_golden_snapshot(filename: str) -> None:
    expected = json.loads(
        (FIXTURES / "golden" / "document_blocks.json").read_text(encoding="utf-8")
    )
    document_hash, blocks = parse_document(FIXTURES / "documents" / filename)

    assert len(document_hash) == 64
    assert [_stable_block(block) for block in blocks] == expected[filename]
    assert all(block.document_id == document_hash[:24] for block in blocks)
    assert len({block.block_id for block in blocks}) == len(blocks)


def test_persist_blocks_writes_valid_jsonl_atomically(tmp_path: Path) -> None:
    document_hash, blocks = parse_document(FIXTURES / "documents" / "safety.md")
    target = persist_blocks(tmp_path, document_hash[:24], blocks)

    rows = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 4
    assert rows[0]["block_type"] == "title"
    assert not list(tmp_path.glob("*.tmp"))


def test_parser_rejects_unsupported_extension(tmp_path: Path) -> None:
    source = tmp_path / "unsafe.exe"
    source.write_bytes(b"not a document")
    with pytest.raises(ValueError, match="不支持的文档类型"):
        parse_document(source)
