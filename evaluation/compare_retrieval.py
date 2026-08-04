from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env" if (PROJECT_ROOT / ".env").exists() else PROJECT_ROOT / "backen" / ".env")

from backend_fastapi.retrieval import _tokens, load_index, load_reranker  # noqa: E402


def rrf_fuse(dense: list[int], sparse: list[int], limit: int, rrf_k: int = 60) -> list[int]:
    scores: dict[int, float] = defaultdict(float)
    for rank, document_id in enumerate(dense, 1):
        scores[document_id] += 1.0 / (rrf_k + rank)
    for rank, document_id in enumerate(sparse, 1):
        scores[document_id] += 1.0 / (rrf_k + rank)
    return [document_id for document_id, _ in sorted(scores.items(), key=lambda item: item[1], reverse=True)[:limit]]


def first_rank(ranking: list[int], relevant: set[int]) -> int | None:
    return next((rank for rank, document_id in enumerate(ranking, 1) if document_id in relevant), None)


def ndcg_at(ranking: list[int], relevant: set[int], k: int) -> float:
    dcg = sum(1.0 / math.log2(rank + 1) for rank, item in enumerate(ranking[:k], 1) if item in relevant)
    ideal_count = min(k, len(relevant))
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_count + 1))
    return dcg / ideal if ideal else 0.0


def source_of(metadata: dict[str, Any]) -> str:
    return metadata.get("file") or metadata.get("source") or "未知来源"


def summarize(
    rankings: list[list[int]],
    samples: list[dict[str, Any]],
    metadatas: list[dict[str, Any]],
    latency_ms: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    count = len(samples)
    hit_totals = {1: 0, 3: 0, 5: 0}
    source_hit_totals = {1: 0, 3: 0, 5: 0}
    reciprocal_ranks = []
    source_reciprocal_ranks = []
    ndcgs = []
    exact_hits = 0
    details = []
    for sample, ranking in zip(samples, rankings):
        relevant = set(sample["relevant_chunk_ids"])
        relevant_sources = set(sample["relevant_sources"])
        rank = first_rank(ranking, relevant)
        source_ranking = [source_of(metadatas[document_id]) for document_id in ranking]
        source_rank = next(
            (position for position, source in enumerate(source_ranking, 1) if source in relevant_sources),
            None,
        )
        exact_rank = next(
            (position for position, document_id in enumerate(ranking, 1) if document_id == sample["target_chunk_id"]),
            None,
        )
        for k in hit_totals:
            hit_totals[k] += int(rank is not None and rank <= k)
            source_hit_totals[k] += int(source_rank is not None and source_rank <= k)
        reciprocal_ranks.append(1.0 / rank if rank else 0.0)
        source_reciprocal_ranks.append(1.0 / source_rank if source_rank else 0.0)
        ndcgs.append(ndcg_at(ranking, relevant, 5))
        exact_hits += int(exact_rank is not None and exact_rank <= 5)
        details.append(
            {
                "id": sample["id"],
                "question": sample["question"],
                "target_chunk_id": sample["target_chunk_id"],
                "rank": rank,
                "exact_target_rank": exact_rank,
                "source_rank": source_rank,
                "top5_chunk_ids": ranking[:5],
            }
        )
    divisor = max(count, 1)
    metrics = {
        "samples": count,
        "recall@1": round(hit_totals[1] / divisor, 4),
        "recall@3": round(hit_totals[3] / divisor, 4),
        "recall@5": round(hit_totals[5] / divisor, 4),
        "mrr@20": round(sum(reciprocal_ranks) / divisor, 4),
        "ndcg@5": round(sum(ndcgs) / divisor, 4),
        "exact_target_recall@5": round(exact_hits / divisor, 4),
        "source_recall@1": round(source_hit_totals[1] / divisor, 4),
        "source_recall@5": round(source_hit_totals[5] / divisor, 4),
        "source_mrr@20": round(sum(source_reciprocal_ranks) / divisor, 4),
        "batch_amortized_latency_ms_per_query": round(latency_ms, 2),
    }
    return metrics, details


def evaluate(
    dataset: Path,
    knowledge_base: str,
    candidate_k: int,
    reranker_candidate_k: int,
    reranker_max_length: int | None,
) -> dict[str, Any]:
    samples = [json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not samples:
        raise RuntimeError("评测集为空")
    store = load_index(knowledge_base)
    if any(sample["target_chunk_id"] >= len(store.metadatas) for sample in samples):
        raise RuntimeError("评测集与当前索引不匹配")
    candidate_k = min(candidate_k, len(store.metadatas))
    reranker_candidate_k = min(reranker_candidate_k, candidate_k)
    questions = [sample["question"] for sample in samples]

    started = time.perf_counter()
    vectors = store.embedder.encode(
        questions,
        batch_size=32,
        normalize_embeddings=True,
        show_progress_bar=True,
    ).astype("float32")
    _, dense_indices = store.index.search(vectors, candidate_k)
    dense_rankings = [[int(item) for item in row if item >= 0] for row in dense_indices]
    dense_elapsed = time.perf_counter() - started

    started = time.perf_counter()
    sparse_rankings = []
    for question in questions:
        scores = np.asarray(store.bm25.get_scores(_tokens(question)))
        sparse_rankings.append(np.argsort(scores)[::-1][:candidate_k].astype(int).tolist())
    sparse_elapsed = time.perf_counter() - started

    started = time.perf_counter()
    hybrid_rankings = [
        rrf_fuse(dense, sparse, candidate_k)
        for dense, sparse in zip(dense_rankings, sparse_rankings)
    ]
    fusion_elapsed = time.perf_counter() - started

    reranker_load_started = time.perf_counter()
    reranker = load_reranker()
    reranker_load_elapsed = time.perf_counter() - reranker_load_started
    if reranker is None:
        raise RuntimeError("BGE Reranker 模型不可用")
    if reranker_max_length is not None:
        reranker.max_length = reranker_max_length
    pairs = [
        (question, store.metadatas[document_id]["content"])
        for question, ranking in zip(questions, hybrid_rankings)
        for document_id in ranking[:reranker_candidate_k]
    ]
    started = time.perf_counter()
    scores = np.asarray(
        reranker.predict(pairs, batch_size=32, show_progress_bar=True)
    ).reshape(len(samples), reranker_candidate_k)
    rerank_elapsed = time.perf_counter() - started
    reranked_rankings = [
        [
            document_id
            for document_id, _ in sorted(
                zip(ranking[:reranker_candidate_k], row),
                key=lambda item: float(item[1]),
                reverse=True,
            )
        ]
        for ranking, row in zip(hybrid_rankings, scores)
    ]

    count = len(samples)
    latencies = {
        "dense": dense_elapsed * 1000 / count,
        "bm25": sparse_elapsed * 1000 / count,
        "hybrid_rrf": (dense_elapsed + sparse_elapsed + fusion_elapsed) * 1000 / count,
        "hybrid_rrf_reranker": (dense_elapsed + sparse_elapsed + fusion_elapsed + rerank_elapsed) * 1000 / count,
    }
    methods: dict[str, Any] = {}
    for name, rankings in {
        "dense_bge_faiss": dense_rankings,
        "sparse_bm25": sparse_rankings,
        "hybrid_rrf": hybrid_rankings,
        "hybrid_rrf_bge_reranker": reranked_rankings,
    }.items():
        latency_key = {
            "dense_bge_faiss": "dense",
            "sparse_bm25": "bm25",
            "hybrid_rrf": "hybrid_rrf",
            "hybrid_rrf_bge_reranker": "hybrid_rrf_reranker",
        }[name]
        metrics, details = summarize(rankings, samples, store.metadatas, latencies[latency_key])
        methods[name] = {"metrics": metrics, "details": details}

    return {
        "dataset": str(dataset),
        "benchmark_type": "synthetic_query_from_corpus",
        "knowledge_base": knowledge_base,
        "index_chunks": len(store.metadatas),
        "candidate_k": candidate_k,
        "reranker_candidate_k": reranker_candidate_k,
        "reranker_max_length": reranker.max_length,
        "relevance_definition": "target chunk plus adjacent chunks from the same source",
        "latency_note": "batch throughput amortized per query; excludes model/index loading and is not online P95",
        "reranker_load_seconds": round(reranker_load_elapsed, 3),
        "methods": methods,
    }


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# 检索对比实验",
        "",
        f"- 数据集：{report['dataset']}",
        f"- 样本数：{next(iter(report['methods'].values()))['metrics']['samples']}",
        f"- 索引片段：{report['index_chunks']}",
        f"- 候选数：{report['candidate_k']}",
        f"- Reranker 输入候选数：{report['reranker_candidate_k']}",
        f"- Reranker 最大序列长度：{report['reranker_max_length'] or '模型默认值'}",
        "- 说明：问题由语料片段合成，指标用于工程回归，不等同于真实用户盲测。",
        "",
        "| 方法 | Recall@1 | Recall@3 | Recall@5 | MRR@20 | nDCG@5 | 精确目标R@5 | 平均延迟(ms) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, value in report["methods"].items():
        metric = value["metrics"]
        lines.append(
            f"| {name} | {metric['recall@1']:.4f} | {metric['recall@3']:.4f} | "
            f"{metric['recall@5']:.4f} | {metric['mrr@20']:.4f} | {metric['ndcg@5']:.4f} | "
            f"{metric['exact_target_recall@5']:.4f} | {metric['batch_amortized_latency_ms_per_query']:.2f} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=PROJECT_ROOT / "evaluation" / "coal_mine_qa_300.jsonl")
    parser.add_argument("--knowledge-base", default="samples")
    parser.add_argument("--candidate-k", type=int, default=20)
    parser.add_argument("--reranker-candidate-k", type=int, default=10)
    parser.add_argument("--reranker-max-length", type=int)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "evaluation" / "retrieval_comparison_report.json")
    args = parser.parse_args()
    report = evaluate(
        args.dataset,
        args.knowledge_base,
        args.candidate_k,
        args.reranker_candidate_k,
        args.reranker_max_length,
    )
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path = args.output.with_suffix(".md")
    markdown_path.write_text(markdown_report(report), encoding="utf-8")
    print(markdown_report(report))
    print(f"JSON: {args.output}")
    print(f"Markdown: {markdown_path}")


if __name__ == "__main__":
    main()
