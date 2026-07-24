from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env" if (PROJECT_ROOT / ".env").exists() else PROJECT_ROOT / "backen" / ".env")

from backend_fastapi.retrieval import hybrid_search  # noqa: E402


def evaluate(dataset_path: Path, knowledge_base: str, top_k: int) -> dict:
    samples = [
        json.loads(line)
        for line in dataset_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    hits = 0
    reciprocal_ranks = []
    latencies = []
    details = []
    for sample in samples:
        started = time.perf_counter()
        documents = hybrid_search(sample["question"], knowledge_base, top_k, 0.0)
        latencies.append(time.perf_counter() - started)
        sources = [document["source"] for document in documents]
        relevant = set(sample["relevant_sources"])
        first_rank = next(
            (rank for rank, source in enumerate(sources, 1) if source in relevant),
            None,
        )
        hits += int(first_rank is not None)
        reciprocal_ranks.append(1 / first_rank if first_rank else 0.0)
        details.append(
            {
                "question": sample["question"],
                "hit": first_rank is not None,
                "rank": first_rank,
                "returned_sources": sources,
            }
        )

    count = len(samples) or 1
    return {
        "samples": len(samples),
        f"recall@{top_k}": round(hits / count, 4),
        "mrr": round(sum(reciprocal_ranks) / count, 4),
        "average_latency_s": round(sum(latencies) / count, 3),
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        type=Path,
        default=PROJECT_ROOT / "evaluation" / "retrieval_eval.jsonl",
    )
    parser.add_argument("--knowledge-base", default="samples")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    print(
        json.dumps(
            evaluate(args.dataset, args.knowledge_base, args.top_k),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
