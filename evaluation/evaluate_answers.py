from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CITATION_RE = re.compile(r"\[#(\d+)\]")
_REFUSAL_RE = re.compile(r"根据现有证据无法回答|没有找到.*依据|证据不足|无法确认")
_SENTENCE_RE = re.compile(r"[^。！？!?\n]+[。！？!?]?")


def evaluate_answer_record(record: dict[str, Any]) -> dict[str, Any]:
    answer = str(record.get("answer") or "").strip()
    sources = record.get("sources") or []
    source_count = len(sources) if isinstance(sources, list) else int(record.get("source_count") or 0)
    citation_ids = [int(value) for value in _CITATION_RE.findall(answer)]
    valid_ids = [value for value in citation_ids if 1 <= value <= source_count]
    sentences = [item.strip() for item in _SENTENCE_RE.findall(answer) if item.strip()]
    substantive = [item for item in sentences if len(_CITATION_RE.sub("", item).strip()) >= 6]
    cited_substantive = [item for item in substantive if _CITATION_RE.search(item)]
    refused = bool(_REFUSAL_RE.search(answer))
    expected_refusal = record.get("should_refuse")
    return {
        "id": record.get("id"),
        "citation_count": len(citation_ids),
        "valid_citation_count": len(valid_ids),
        "invalid_citation_count": len(citation_ids) - len(valid_ids),
        "citation_precision": round(len(valid_ids) / len(citation_ids), 4) if citation_ids else 1.0,
        "citation_coverage": round(len(cited_substantive) / len(substantive), 4) if substantive else 0.0,
        "refused": refused,
        "should_refuse": expected_refusal if isinstance(expected_refusal, bool) else None,
        "refusal_correct": refused == expected_refusal if isinstance(expected_refusal, bool) else None,
        "citation_required_violation": bool(answer and not refused and not citation_ids),
        "answer_empty": not bool(answer),
    }


def summarize_answer_records(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    evaluated = [evaluate_answer_record(record) for record in records]
    count = len(evaluated)
    divisor = max(count, 1)
    total_citations = sum(item["citation_count"] for item in evaluated)
    total_valid_citations = sum(item["valid_citation_count"] for item in evaluated)
    refusal_labeled = [item for item in evaluated if item["refusal_correct"] is not None]
    return {
        "samples": count,
        "empty_answer_rate": round(sum(item["answer_empty"] for item in evaluated) / divisor, 4),
        "refusal_rate": round(sum(item["refused"] for item in evaluated) / divisor, 4),
        "citation_precision": round(total_valid_citations / max(total_citations, 1), 4),
        "citation_coverage": round(sum(item["citation_coverage"] for item in evaluated) / divisor, 4),
        "citation_required_violation_rate": round(
            sum(item["citation_required_violation"] for item in evaluated) / divisor, 4
        ),
        "invalid_citation_rate": round(
            sum(item["invalid_citation_count"] for item in evaluated)
            / max(sum(item["citation_count"] for item in evaluated), 1),
            4,
        ),
        "refusal_labeled_samples": len(refusal_labeled),
        "refusal_accuracy": round(
            sum(item["refusal_correct"] for item in refusal_labeled) / len(refusal_labeled), 4
        ) if refusal_labeled else None,
        "details": evaluated,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate citation and refusal quality from answer JSONL")
    parser.add_argument("answers", type=Path, help="JSONL with id, answer, and sources")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    records = [
        json.loads(line)
        for line in args.answers.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    result = summarize_answer_records(records)
    serialized = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
