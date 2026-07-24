from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend_fastapi.storage import StateStore


REDIS_URL = "redis://127.0.0.1:6379/0"
REQUEST_ID = "coalchat-persistence-test"


async def write() -> None:
    store = StateStore(REDIS_URL, evidence_ttl=60, cache_ttl=60)
    await store.save_evidence(
        REQUEST_ID,
        {1: {"content": "跨进程证据", "source": "redis-test"}},
    )
    print(json.dumps({"backend": await store.backend(), "written": True}))
    await store.close()


async def read() -> None:
    store = StateStore(REDIS_URL, evidence_ttl=60, cache_ttl=60)
    value = await store.get_evidence(REQUEST_ID, 1)
    print(
        json.dumps(
            {
                "backend": await store.backend(),
                "persisted": bool(value),
                "content_matches": bool(value)
                and value.get("content") == "跨进程证据",
            }
        )
    )
    await store.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["write", "read"])
    args = parser.parse_args()
    asyncio.run(write() if args.mode == "write" else read())


if __name__ == "__main__":
    main()
