from pathlib import Path

import pytest

from evaluation.validate_dataset import DatasetValidationError, validate_dataset


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_frozen_retrieval_dataset_matches_manifest() -> None:
    result = validate_dataset(PROJECT_ROOT / "evaluation" / "dataset_manifest.json")
    assert result["status"] == "ok"
    assert result["samples"] == 300
    assert result["unique_sources"] >= 8


def test_dataset_hash_detects_unreviewed_changes(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text('{"id":"q1"}\n', encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        '{"dataset":"dataset.jsonl","samples":1,"sha256":"wrong","required_fields":[]}',
        encoding="utf-8",
    )
    with pytest.raises(DatasetValidationError, match="SHA256 不匹配"):
        validate_dataset(manifest)
