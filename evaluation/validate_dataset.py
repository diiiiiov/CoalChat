from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT_ROOT / "evaluation" / "dataset_manifest.json"


class DatasetValidationError(ValueError):
    """Raised when the frozen retrieval dataset no longer matches its contract."""


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetValidationError(f"无法读取 JSON：{path}: {exc}") from exc


def validate_dataset(manifest_path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    manifest = _load_json(manifest_path)
    if not isinstance(manifest, dict):
        raise DatasetValidationError("评测集清单必须是 JSON 对象")

    dataset_name = manifest.get("dataset")
    if not isinstance(dataset_name, str) or Path(dataset_name).name != dataset_name:
        raise DatasetValidationError("清单中的 dataset 必须是同目录文件名")
    dataset_path = manifest_path.parent / dataset_name
    try:
        raw = dataset_path.read_bytes()
    except OSError as exc:
        raise DatasetValidationError(f"无法读取评测集：{dataset_path}: {exc}") from exc

    actual_sha256 = hashlib.sha256(raw).hexdigest()
    expected_sha256 = str(manifest.get("sha256", ""))
    if actual_sha256 != expected_sha256:
        raise DatasetValidationError(
            f"评测集 SHA256 不匹配：expected={expected_sha256}, actual={actual_sha256}"
        )

    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(raw.decode("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DatasetValidationError(f"第 {line_number} 行不是合法 JSON") from exc
        if not isinstance(row, dict):
            raise DatasetValidationError(f"第 {line_number} 行必须是 JSON 对象")
        rows.append(row)

    expected_samples = int(manifest.get("samples", -1))
    if len(rows) != expected_samples:
        raise DatasetValidationError(
            f"评测集数量不匹配：expected={expected_samples}, actual={len(rows)}"
        )

    required_fields = set(manifest.get("required_fields") or [])
    ids: list[str] = []
    questions: list[str] = []
    sources: Counter[str] = Counter()
    for index, row in enumerate(rows, 1):
        missing = sorted(field for field in required_fields if field not in row)
        if missing:
            raise DatasetValidationError(f"第 {index} 条缺少字段：{', '.join(missing)}")
        sample_id = str(row["id"]).strip()
        question = str(row["question"]).strip()
        if not sample_id or not question:
            raise DatasetValidationError(f"第 {index} 条 id/question 不能为空")
        relevant_ids = row.get("relevant_chunk_ids")
        relevant_sources = row.get("relevant_sources")
        if not isinstance(relevant_ids, list) or row["target_chunk_id"] not in relevant_ids:
            raise DatasetValidationError(f"第 {index} 条目标片段未包含在相关片段中")
        if not isinstance(relevant_sources, list) or row["source"] not in relevant_sources:
            raise DatasetValidationError(f"第 {index} 条来源未包含在相关来源中")
        snippet_hash = str(row["snippet_sha256"])
        if len(snippet_hash) != 16 or any(ch not in "0123456789abcdef" for ch in snippet_hash):
            raise DatasetValidationError(f"第 {index} 条 snippet_sha256 格式错误")
        ids.append(sample_id)
        questions.append(question)
        sources[str(row["source"])] += 1

    if len(set(ids)) != len(ids):
        raise DatasetValidationError("评测集存在重复 id")
    if len(set(questions)) != len(questions):
        raise DatasetValidationError("评测集存在重复问题")

    return {
        "status": "ok",
        "dataset": dataset_name,
        "samples": len(rows),
        "sha256": actual_sha256,
        "unique_sources": len(sources),
        "source_distribution": dict(sorted(sources.items())),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the frozen retrieval dataset")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    print(json.dumps(validate_dataset(args.manifest), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
