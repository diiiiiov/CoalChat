from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path
from typing import Any

import httpx


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((percentile_value / 100) * len(ordered))) - 1))
    return ordered[index]


async def run_load(
    url: str, payload: dict[str, Any], requests: int, concurrency: int, timeout: float
) -> dict[str, Any]:
    semaphore = asyncio.Semaphore(max(1, concurrency))
    latencies: list[float] = []
    statuses: list[int] = []

    async with httpx.AsyncClient(timeout=timeout) as client:
        async def one_request() -> None:
            async with semaphore:
                started = time.perf_counter()
                try:
                    response = await client.post(url, json=payload)
                    statuses.append(response.status_code)
                except Exception:
                    statuses.append(0)
                finally:
                    latencies.append((time.perf_counter() - started) * 1000)

        started = time.perf_counter()
        await asyncio.gather(*(one_request() for _ in range(requests)))
        elapsed = time.perf_counter() - started

    successes = sum(status == 200 for status in statuses)
    return {
        "requests": requests,
        "concurrency": concurrency,
        "successes": successes,
        "errors": requests - successes,
        "error_rate": round((requests - successes) / max(requests, 1), 4),
        "throughput_rps": round(requests / max(elapsed, 0.001), 3),
        "latency_ms": {
            "p50": round(percentile(latencies, 50), 2),
            "p95": round(percentile(latencies, 95), 2),
            "p99": round(percentile(latencies, 99), 2),
            "max": round(max(latencies) if latencies else 0.0, 2),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a bounded CoalChat HTTP load test")
    parser.add_argument("--url", default="http://127.0.0.1:8000/api/knowledge/chat")
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--query", default="瓦斯浓度超限时应当如何处置？")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = {
        "query": args.query,
        "knowledge_base_name": "samples",
        "top_k": 5,
        "score_threshold": 0.0,
        "temperature": 0.2,
    }
    result = asyncio.run(run_load(args.url, payload, args.requests, args.concurrency, args.timeout))
    serialized = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
