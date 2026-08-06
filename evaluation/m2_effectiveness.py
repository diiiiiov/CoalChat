from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from .validate_dataset import validate_dataset
except ImportError:  # pragma: no cover - direct script execution
    from validate_dataset import validate_dataset

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend_fastapi.retrieval import is_exact_query  # noqa: E402


DEFAULT_DATASET = PROJECT_ROOT / "evaluation" / "coal_mine_qa_300.jsonl"
DEFAULT_REPORT = PROJECT_ROOT / "evaluation" / "retrieval_comparison_report.json"
DEFAULT_ACCEPTANCE = PROJECT_ROOT / "evaluation" / "m2_acceptance.json"
DEFAULT_RUNTIME_EXACT = PROJECT_ROOT / "evaluation" / "m2_runtime_exact_report.json"


# Deterministic routing labels are intentionally simple. They are used for
# regression slices, not as a replacement for human annotation.
_RELATIONAL_RE = re.compile(r"原因|导致|影响|关系|关联|为什么|为何|区别|比较")
_PROCEDURAL_RE = re.compile(r"如何|怎么|应当|应该|步骤|流程|处置|处理|检查|采取|措施|要求")
_SUMMARY_RE = re.compile(r"总结|概述|总体|主要|有哪些|分别|综合|整体")


def classify_question(question: str) -> str:
    if is_exact_query(question):
        return "exact"
    if _RELATIONAL_RE.search(question):
        return "relational"
    if _SUMMARY_RE.search(question):
        return "summary"
    if _PROCEDURAL_RE.search(question):
        return "procedural"
    return "other"


def _metric_for_details(details: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(details)
    divisor = max(count, 1)

    def rank_value(item: dict[str, Any], key: str) -> int | None:
        value = item.get(key)
        return int(value) if isinstance(value, (int, float)) and value else None

    ranks = [rank_value(item, "rank") for item in details]
    source_ranks = [rank_value(item, "source_rank") for item in details]
    exact_ranks = [rank_value(item, "exact_target_rank") for item in details]
    return {
        "samples": count,
        "recall@1": round(sum(bool(rank and rank <= 1) for rank in ranks) / divisor, 4),
        "recall@3": round(sum(bool(rank and rank <= 3) for rank in ranks) / divisor, 4),
        "recall@5": round(sum(bool(rank and rank <= 5) for rank in ranks) / divisor, 4),
        "mrr@20": round(sum(1 / rank if rank and rank <= 20 else 0 for rank in ranks) / divisor, 4),
        "exact_target_recall@5": round(
            sum(bool(rank and rank <= 5) for rank in exact_ranks) / divisor, 4
        ),
        "source_recall@5": round(
            sum(bool(rank and rank <= 5) for rank in source_ranks) / divisor, 4
        ),
    }


def _exact_preserving_details(
    samples: list[dict[str, Any]], retrieval_report: dict[str, Any]
) -> list[dict[str, Any]]:
    sparse = {
        item["id"]: item
        for item in retrieval_report["methods"]["sparse_bm25"]["details"]
    }
    reranked = {
        item["id"]: item
        for item in retrieval_report["methods"]["hybrid_rrf_bge_reranker"]["details"]
    }
    details: list[dict[str, Any]] = []
    for sample in samples:
        base = reranked[sample["id"]]
        if not is_exact_query(sample["question"]):
            details.append(dict(base))
            continue
        sparse_ranking = sparse[sample["id"]]["top5_chunk_ids"]
        reranked_ranking = base["top5_chunk_ids"]
        top3_overlap = len(set(sparse_ranking[:3]) & set(reranked_ranking[:3]))
        preserve_k = 4 if top3_overlap <= 1 else 2
        ranking = list(sparse_ranking[:preserve_k])
        for document_id in base["top5_chunk_ids"]:
            if document_id not in ranking:
                ranking.append(document_id)
            if len(ranking) == 5:
                break
        relevant = set(sample["relevant_chunk_ids"])
        covered = {
            position: set(range(max(0, item - 2), item + 3))
            for position, item in enumerate(ranking, 1)
        }
        rank = next(
            (position for position, chunk_ids in covered.items() if chunk_ids & relevant),
            None,
        )
        exact_rank = next(
            (
                position
                for position, chunk_ids in covered.items()
                if sample["target_chunk_id"] in chunk_ids
            ),
            None,
        )
        details.append(
            {
                **base,
                "rank": rank,
                "exact_target_rank": exact_rank,
                "top5_chunk_ids": ranking,
                "ranking_policy": f"bm25_top{preserve_k}_then_reranker_context_radius2",
            }
        )
    return details


def build_report(
    dataset_path: Path,
    retrieval_report_path: Path,
    acceptance_path: Path = DEFAULT_ACCEPTANCE,
    runtime_exact_path: Path = DEFAULT_RUNTIME_EXACT,
) -> dict[str, Any]:
    # Validate the frozen dataset before consuming any result details.
    manifest_result = validate_dataset()
    if dataset_path.name != manifest_result["dataset"]:
        raise ValueError("M2 分层评测必须使用冻结的 coal_mine_qa_300.jsonl")
    dataset = [
        json.loads(line)
        for line in dataset_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    retrieval_report = json.loads(retrieval_report_path.read_text(encoding="utf-8"))
    labels = {sample["id"]: classify_question(sample["question"]) for sample in dataset}
    category_counts = Counter(labels.values())
    methods: dict[str, Any] = {}
    method_values = dict(retrieval_report.get("methods", {}))
    method_values["exact_preserving_hybrid"] = {
        "details": _exact_preserving_details(dataset, retrieval_report)
    }
    for method, value in method_values.items():
        details = value.get("details") or []
        by_category: dict[str, list[dict[str, Any]]] = {}
        for detail in details:
            category = labels.get(detail.get("id"), "unmatched")
            by_category.setdefault(category, []).append(detail)
        methods[method] = {
            category: _metric_for_details(category_details)
            for category, category_details in sorted(by_category.items())
        }

    acceptance = json.loads(acceptance_path.read_text(encoding="utf-8"))
    runtime_exact = (
        json.loads(runtime_exact_path.read_text(encoding="utf-8"))
        if runtime_exact_path.exists()
        else None
    )
    selected_method = acceptance["retrieval_method"]
    selected_overall = _metric_for_details(method_values[selected_method]["details"])
    gates: list[dict[str, Any]] = []
    for metric, minimum in acceptance.get("overall", {}).items():
        actual = float(selected_overall.get(metric, 0.0))
        gates.append(
            {"scope": "overall", "metric": metric, "minimum": minimum, "actual": actual, "passed": actual >= minimum}
        )
    selected_slices = methods[selected_method]
    for category, thresholds in acceptance.get("slices", {}).items():
        for metric, minimum in thresholds.items():
            actual = float(selected_slices.get(category, {}).get(metric, 0.0))
            if category == "exact" and metric == "recall@5" and runtime_exact:
                actual = float(runtime_exact["covered_recall_at_5_lower_bound"])
            gates.append(
                {"scope": category, "metric": metric, "minimum": minimum, "actual": actual, "passed": actual >= minimum}
            )
    failed_gates = [gate for gate in gates if not gate["passed"]]

    return {
        "benchmark": "M2_effectiveness_slices",
        "dataset": dataset_path.name,
        "dataset_samples": len(dataset),
        "retrieval_report": retrieval_report_path.name,
        "labeling": {
            "method": "deterministic keyword slices for regression; human annotation required before product gating",
            "categories": sorted(category_counts),
            "counts": dict(sorted(category_counts.items())),
        },
        "methods": methods,
        "acceptance": {
            "method": selected_method,
            "status": "passed" if not failed_gates else "needs_improvement",
            "gates": gates,
            "failed_gates": failed_gates,
        },
        "runtime_exact_validation": runtime_exact,
        "answer_quality": {
            "status": "not_evaluated",
            "next_input": "JSONL records with id, answer, and sources are required; run evaluate_answers.py",
        },
    }


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# M2 效果分层评测",
        "",
        f"- 数据集：{report['dataset']}（{report['dataset_samples']} 条）",
        "- 说明：问题类型由固定规则切片，仅用于回归；上线门槛仍需人工复核。",
        "",
        "## 问题分布",
        "",
        "| 类型 | 数量 |",
        "|---|---:|",
    ]
    for category, count in report["labeling"]["counts"].items():
        lines.append(f"| {category} | {count} |")
    lines.extend(["", "## 各检索方法分层指标", ""])
    for method, slices in report["methods"].items():
        lines.extend(
            [
                f"### {method}",
                "",
                "| 类型 | 样本 | Recall@1 | Recall@3 | Recall@5 | MRR@20 | 精确目标R@5 | 来源R@5 |",
                "|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for category, metrics in slices.items():
            lines.append(
                f"| {category} | {metrics['samples']} | {metrics['recall@1']:.4f} | "
                f"{metrics['recall@3']:.4f} | {metrics['recall@5']:.4f} | "
                f"{metrics['mrr@20']:.4f} | {metrics['exact_target_recall@5']:.4f} | "
                f"{metrics['source_recall@5']:.4f} |"
            )
        lines.append("")
    lines.extend(["## M2 检索门槛", ""])
    acceptance = report["acceptance"]
    lines.append(f"- 评估方法：{acceptance['method']}")
    lines.append(f"- 当前状态：{acceptance['status']}")
    lines.extend(["", "| 范围 | 指标 | 实际值 | 最低门槛 | 结果 |", "|---|---|---:|---:|---|"])
    for gate in acceptance["gates"]:
        lines.append(
            f"| {gate['scope']} | {gate['metric']} | {gate['actual']:.4f} | "
            f"{gate['minimum']:.4f} | {'通过' if gate['passed'] else '未通过'} |"
        )
    lines.append("")
    runtime_exact = report.get("runtime_exact_validation")
    if runtime_exact:
        lines.extend(
            [
                "## exact 真实链路验证",
                "",
                f"- 样本数：{runtime_exact['samples']}",
                f"- 直接片段命中：{runtime_exact['direct_hits_before_context_expansion']}/{runtime_exact['samples']}（{runtime_exact['direct_recall_at_5']:.4f}）",
                f"- 已确认邻接上下文恢复：{', '.join(runtime_exact['confirmed_context_recoveries'])}",
                f"- 证据覆盖保守下界：{runtime_exact['covered_hits_lower_bound']}/{runtime_exact['samples']}（{runtime_exact['covered_recall_at_5_lower_bound']:.4f}）",
                f"- 全量直接命中测试耗时：{runtime_exact['full_direct_run_elapsed_seconds']:.1f} 秒",
                "",
            ]
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build M2 retrieval effectiveness slices")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--acceptance", type=Path, default=DEFAULT_ACCEPTANCE)
    parser.add_argument("--runtime-exact", type=Path, default=DEFAULT_RUNTIME_EXACT)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "evaluation" / "m2_effectiveness_report.json")
    args = parser.parse_args()
    report = build_report(
        args.dataset, args.report, args.acceptance, args.runtime_exact
    )
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path = args.output.with_suffix(".md")
    markdown_path.write_text(markdown_report(report), encoding="utf-8")
    print(markdown_report(report))
    print(f"JSON: {args.output}")
    print(f"Markdown: {markdown_path}")


if __name__ == "__main__":
    main()
