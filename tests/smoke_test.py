import json
import sys
import time

import httpx


BASE_URL = "http://127.0.0.1:18000"
PAYLOAD = {
    "query": "煤矿发生透水事故后应当如何处置？",
    "knowledge_base_name": "samples",
    "top_k": 3,
    "score_threshold": 0.0,
    "model_name": "mock-model",
    "temperature": 0.2,
}


def main() -> None:
    health = httpx.get(f"{BASE_URL}/health", timeout=10)
    health.raise_for_status()
    health_data = health.json()
    assert health_data["state_backend"] in {"memory", "redis"}

    events = []
    first_event_at = None
    started = time.perf_counter()
    with httpx.stream(
        "POST", f"{BASE_URL}/api/knowledge/chat/stream", json=PAYLOAD, timeout=120
    ) as response:
        response.raise_for_status()
        event_name = "message"
        for line in response.iter_lines():
            if line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                if first_event_at is None:
                    first_event_at = time.perf_counter()
                events.append((event_name, json.loads(line[5:].strip())))

    names = [name for name, _ in events]
    assert names[0] == "sources", names
    assert names.count("token") >= 2, names
    assert names[-1] == "done", names

    source_payload = events[0][1]
    done_payload = events[-1][1]
    assert source_payload["sources"], source_payload
    assert "[#1]" in done_payload["answer"], done_payload
    assert "[#99]" not in done_payload["answer"], done_payload

    request_id = source_payload["request_id"]
    evidence = httpx.get(
        f"{BASE_URL}/api/knowledge/evidence/{request_id}/1", timeout=10
    )
    evidence.raise_for_status()
    evidence_data = evidence.json()
    assert evidence_data["content"]
    assert evidence_data["source"]

    normal = httpx.post(
        f"{BASE_URL}/api/knowledge/chat", json=PAYLOAD, timeout=120
    )
    normal.raise_for_status()
    normal_data = normal.json()["data"]
    assert "[#1]" in normal_data["answer"]
    assert "[#99]" not in normal_data["answer"]
    assert normal_data["cache_hit"] is True

    result = {
        "health": "ok",
        "event_sequence": names,
        "token_events": names.count("token"),
        "time_to_first_event_s": round((first_event_at or started) - started, 3),
        "citations_normalized": True,
        "evidence_lookup": "ok",
        "normal_chat": "ok",
        "retrieval_cache_hit": normal_data["cache_hit"],
        "state_backend": health_data["state_backend"],
        "top_source": evidence_data["source"],
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"SMOKE_TEST_FAILED: {exc}", file=sys.stderr)
        raise
