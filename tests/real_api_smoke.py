from __future__ import annotations

import json
import re
import time

import httpx


BASE_URL = "http://127.0.0.1:18000"


def main() -> None:
    payload = {
        "query": "煤矿发生透水事故后，现场人员应当如何处置？",
        "knowledge_base_name": "samples",
        "top_k": 3,
        "score_threshold": 0.0,
        "temperature": 0.2,
    }
    started = time.perf_counter()
    first_token_at = None
    sources_payload = {}
    done_payload = {}
    token_count = 0
    with httpx.stream(
        "POST", f"{BASE_URL}/api/knowledge/chat/stream", json=payload, timeout=180
    ) as response:
        response.raise_for_status()
        event_name = "message"
        for line in response.iter_lines():
            if line.startswith("event:"):
                event_name = line[6:].strip()
                continue
            if not line.startswith("data:"):
                continue
            data = json.loads(line[5:].strip())
            if event_name == "sources":
                sources_payload = data
            elif event_name == "token":
                token_count += 1
                first_token_at = first_token_at or time.perf_counter()
            elif event_name == "done":
                done_payload = data
            elif event_name == "error":
                raise RuntimeError(data.get("message", "unknown SSE error"))

    answer = done_payload.get("answer", "")
    citations = sorted({int(value) for value in re.findall(r"\[#(\d+)\]", answer)})
    source_count = len(sources_payload.get("sources", []))
    assert token_count > 0
    assert done_payload and done_payload.get("degraded") is False
    assert citations, "模型回答没有引用"
    assert all(1 <= citation_id <= source_count for citation_id in citations)

    request_id = sources_payload["request_id"]
    for citation_id in citations:
        evidence = httpx.get(
            f"{BASE_URL}/api/knowledge/evidence/{request_id}/{citation_id}",
            timeout=10,
        )
        evidence.raise_for_status()
        assert evidence.json().get("content")

    print(
        json.dumps(
            {
                "status": "passed",
                "token_events": token_count,
                "time_to_first_token_s": round((first_token_at or started) - started, 3),
                "total_time_s": round(time.perf_counter() - started, 3),
                "source_count": source_count,
                "citations": citations,
                "evidence_lookup": "passed",
                "answer": answer,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
