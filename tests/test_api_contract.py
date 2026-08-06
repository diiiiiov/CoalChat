from __future__ import annotations

from fastapi.testclient import TestClient

from backend_fastapi import main as api


DOCUMENTS = [
    {
        "source": "煤矿安全规程.txt",
        "chunk_id": 42,
        "score": 0.91,
        "content": "瓦斯浓度超限时应停止作业并撤出人员。",
        "metadata": {"page": 10},
        "retrieval_mode": "exact",
        "reranked": False,
    }
]
SOURCES = [
    {
        "id": 1,
        "label": "[#1]",
        "source": "煤矿安全规程.txt",
        "chunk_id": 42,
        "score": 0.91,
        "preview": "瓦斯浓度超限时应停止作业并撤出人员。",
        "retrieval_mode": "exact",
        "reranked": False,
    }
]


def _retrieval_result(documents=None):
    return documents if documents is not None else DOCUMENTS, "request-test", SOURCES, False, {
        "mode": "exact",
        "cache_hit": False,
    }


def test_openapi_exposes_m1_public_contract() -> None:
    with TestClient(api.app) as client:
        schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert "post" in paths["/api/knowledge/chat"]
    assert "post" in paths["/api/knowledge/chat/stream"]
    assert "post" in paths["/api/knowledge/upload"]
    assert "delete" in paths["/api/knowledge/documents/{filename}"]
    assert "get" in paths["/api/knowledge/evidence/{request_id}/{citation_id}"]


def test_request_validation_and_request_id_header() -> None:
    with TestClient(api.app) as client:
        response = client.post(
            "/api/knowledge/chat",
            json={"query": "", "knowledge_base_name": "../private", "top_k": 0},
            headers={"X-Request-ID": "contract-request"},
        )
    assert response.status_code == 422
    assert response.headers["X-Request-ID"] == "contract-request"


def test_chat_contract_normalizes_citations(monkeypatch) -> None:
    async def fake_retrieve(request, retrieval_query):
        return _retrieval_result()

    async def fake_complete(prompt, model, temperature):
        assert "证据" in prompt
        return "应停止作业[#1]，无效引用应删除[#99]。", {"total_tokens": 20}

    monkeypatch.setattr(api, "_retrieve", fake_retrieve)
    monkeypatch.setattr(api.model_client, "complete_with_usage", fake_complete)
    with TestClient(api.app) as client:
        response = client.post("/api/knowledge/chat", json={"query": "瓦斯超限怎么办？"})

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["answer"] == "应停止作业[#1]，无效引用应删除。"
    assert payload["request_id"] == "request-test"
    assert payload["sources"] == SOURCES
    assert payload["degraded"] is False
    assert payload["trace"]["token_usage"]["total_tokens"] == 20


def test_chat_returns_grounded_refusal_when_retrieval_is_empty(monkeypatch) -> None:
    async def fake_retrieve(request, retrieval_query):
        return [], "request-empty", [], False, {"mode": "semantic"}

    monkeypatch.setattr(api, "_retrieve", fake_retrieve)
    with TestClient(api.app) as client:
        response = client.post("/api/knowledge/chat", json={"query": "知识库外问题"})

    payload = response.json()["data"]
    assert payload["answer"] == "根据现有证据无法回答该问题"
    assert payload["sources"] == []
    assert payload["degraded"] is False


def test_stream_contract_emits_sources_tokens_and_done(monkeypatch) -> None:
    async def fake_retrieve(request, retrieval_query):
        return _retrieval_result()

    async def fake_stream(prompt, model, temperature):
        for token in ("停止作业", "[#1]"):
            yield token

    monkeypatch.setattr(api, "_retrieve", fake_retrieve)
    monkeypatch.setattr(api.model_client, "stream", fake_stream)
    with TestClient(api.app) as client:
        response = client.post("/api/knowledge/chat/stream", json={"query": "瓦斯超限怎么办？"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text.index("event: sources") < response.text.index("event: token")
    assert response.text.index("event: token") < response.text.index("event: done")
    assert '"answer": "停止作业[#1]"' in response.text


def test_evidence_contract_supports_hit_and_expiry() -> None:
    request_id = "api-contract-evidence"
    import asyncio

    asyncio.run(api.state_store.save_evidence(request_id, {1: {"content": "证据正文", "source": "规程"}}))
    with TestClient(api.app) as client:
        found = client.get(f"/api/knowledge/evidence/{request_id}/1")
        missing = client.get(f"/api/knowledge/evidence/{request_id}/2")

    assert found.status_code == 200
    assert found.json()["content"] == "证据正文"
    assert missing.status_code == 404
