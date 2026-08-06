from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

from backend_fastapi import main as api
from backend_fastapi.storage import StateStore
from evaluation.m3_load_test import percentile


def test_percentile_is_stable_for_small_samples() -> None:
    assert percentile([10, 20, 30, 40], 50) == 20
    assert percentile([10, 20, 30, 40], 95) == 40
    assert percentile([], 95) == 0.0


def test_identical_uncached_requests_are_coalesced() -> None:
    calls = 0

    def fake_hybrid(*args, **kwargs):
        nonlocal calls
        calls += 1
        time.sleep(0.05)
        return [
            {
                "source": "rules.txt",
                "chunk_id": 1,
                "score": 0.9,
                "content": "evidence",
                "metadata": {},
            }
        ]

    async def scenario() -> None:
        nonlocal calls
        original_store = api.state_store
        api.state_store = StateStore(redis_url="", evidence_ttl=60, cache_ttl=60)
        try:
            request = api.ChatRequest(query="同一个性能测试问题", knowledge_base_name="samples")
            with patch.object(api, "index_version", return_value="test-version"), patch.object(
                api, "hybrid_search", side_effect=fake_hybrid
            ):
                results = await asyncio.gather(
                    *(api._retrieve(request, request.query) for _ in range(8))
                )
            assert calls == 1
            assert all(result[0][0]["chunk_id"] == 1 for result in results)
            assert sum(bool(result[4].get("request_coalesced")) for result in results) >= 1
        finally:
            await api.state_store.close()
            api.state_store = original_store

    asyncio.run(scenario())
