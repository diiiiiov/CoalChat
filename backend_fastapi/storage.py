from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from typing import Any

try:
    from redis.asyncio import Redis
except ImportError:  # pragma: no cover - local fallback remains available
    Redis = None  # type: ignore[assignment]


class StateStore:
    def __init__(
        self,
        redis_url: str = "",
        evidence_ttl: int = 3600,
        cache_ttl: int = 300,
        max_memory_items: int = 500,
    ):
        self.evidence_ttl = evidence_ttl
        self.cache_ttl = cache_ttl
        self.max_memory_items = max_memory_items
        self._redis = Redis.from_url(redis_url, decode_responses=True) if redis_url and Redis else None
        self._memory: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    async def _redis_get(self, key: str) -> Any | None:
        if not self._redis:
            return None
        try:
            value = await self._redis.get(key)
            return json.loads(value) if value else None
        except Exception:
            return None

    async def _redis_set(self, key: str, value: Any, ttl: int) -> bool:
        if not self._redis:
            return False
        try:
            await self._redis.set(key, json.dumps(value, ensure_ascii=False), ex=ttl)
            return True
        except Exception:
            return False

    def _memory_set(self, key: str, value: Any, ttl: int) -> None:
        self._cleanup_memory()
        self._memory[key] = (time.time() + ttl, value)
        self._memory.move_to_end(key)
        while len(self._memory) > self.max_memory_items:
            self._memory.popitem(last=False)

    def _memory_get(self, key: str) -> Any | None:
        self._cleanup_memory()
        item = self._memory.get(key)
        if not item:
            return None
        self._memory.move_to_end(key)
        return item[1]

    def _cleanup_memory(self) -> None:
        now = time.time()
        for key in [key for key, (expires_at, _) in self._memory.items() if expires_at <= now]:
            self._memory.pop(key, None)

    async def save_evidence(self, request_id: str, records: dict[int, Any]) -> None:
        key = f"coalchat:evidence:{request_id}"
        payload = {str(citation_id): value for citation_id, value in records.items()}
        if not await self._redis_set(key, payload, self.evidence_ttl):
            self._memory_set(key, payload, self.evidence_ttl)

    async def get_evidence(self, request_id: str, citation_id: int) -> Any | None:
        key = f"coalchat:evidence:{request_id}"
        records = await self._redis_get(key)
        if records is None:
            records = self._memory_get(key)
        return records.get(str(citation_id)) if records else None

    @staticmethod
    def retrieval_cache_key(payload: dict[str, Any]) -> str:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return f"coalchat:retrieval:{hashlib.sha256(encoded).hexdigest()}"

    async def get_retrieval(self, key: str) -> list[dict[str, Any]] | None:
        value = await self._redis_get(key)
        if value is None:
            value = self._memory_get(key)
        return value

    async def save_retrieval(self, key: str, documents: list[dict[str, Any]]) -> None:
        if not await self._redis_set(key, documents, self.cache_ttl):
            self._memory_set(key, documents, self.cache_ttl)

    async def backend(self) -> str:
        if not self._redis:
            return "memory"
        try:
            return "redis" if await self._redis.ping() else "memory"
        except Exception:
            return "memory"

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
