from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT_ENV = PROJECT_ROOT / ".env"
LEGACY_ENV = PROJECT_ROOT / "backen" / ".env"
load_dotenv(dotenv_path=ROOT_ENV if ROOT_ENV.exists() else LEGACY_ENV)

from .model_client import ModelClient, ModelClientConfig, ModelServiceError  # noqa: E402
from .retrieval import hybrid_search, index_version  # noqa: E402
from .storage import StateStore  # noqa: E402
from .text_utils import normalize_citations  # noqa: E402


logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("coalchat")

def _valid_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _resolve_llm_config() -> tuple[str, str, str, str, bool]:
    raw_url = os.getenv("LLM_API_URL", "").strip()
    api_key = os.getenv("LLM_API_KEY", "").strip()
    api_style = os.getenv("LLM_API_STYLE", "auto").lower()
    model = os.getenv("LLM_MODEL_NAME", "qwen_coalchat")
    legacy_layout = (
        not _valid_http_url(raw_url)
        and not api_key
        and bool(re.fullmatch(r"(?:sk-)?[A-Za-z0-9_-]{24,}", raw_url))
    )
    if legacy_layout:
        # Backward compatibility for the original local .env layout. The key is
        # never logged; users should still migrate to the documented variables.
        return (
            "https://api.deepseek.com/chat/completions",
            raw_url,
            "chat",
            "deepseek-v4-pro",
            True,
        )
    return raw_url, api_key, api_style, model, False


LLM_API_URL, LLM_API_KEY, LLM_API_STYLE, DEFAULT_MODEL, LEGACY_ENV_LAYOUT = (
    _resolve_llm_config()
)

model_client = ModelClient(
    ModelClientConfig(
        api_url=LLM_API_URL,
        api_key=LLM_API_KEY,
        api_style=LLM_API_STYLE,
        default_model=DEFAULT_MODEL,
        timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "60")),
        connect_timeout_seconds=float(os.getenv("LLM_CONNECT_TIMEOUT_SECONDS", "10")),
        max_retries=int(os.getenv("LLM_MAX_RETRIES", "2")),
    )
)
state_store = StateStore(
    redis_url=os.getenv("REDIS_URL", ""),
    evidence_ttl=int(os.getenv("EVIDENCE_TTL_SECONDS", "3600")),
    cache_ttl=int(os.getenv("RETRIEVAL_CACHE_TTL_SECONDS", "300")),
    max_memory_items=int(os.getenv("MAX_EVIDENCE_REQUESTS", "500")),
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await state_store.close()


app = FastAPI(title="CoalChat Knowledge API", version="2.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("request_failed request_id=%s path=%s", request_id, request.url.path)
        raise
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_completed request_id=%s method=%s path=%s status=%s elapsed_ms=%.1f",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        (time.perf_counter() - started) * 1000,
    )
    return response


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    knowledge_base_name: str = Field(default="samples", pattern=r"^[\w-]+$")
    top_k: int = Field(default=5, ge=1, le=20)
    score_threshold: float = Field(default=0.0, ge=0.0, le=1.0)
    model_name: str | None = None
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    history: list[dict[str, Any]] = Field(default_factory=list)


SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "你是煤矿安全领域问答助手。只能根据给定证据回答，不得补充证据之外的事实。\n"
    "每个事实性结论后必须使用 [#n] 标注对应证据，可同时引用多个证据。\n"
    "引用编号必须来自给定证据；证据不足时直接回答'根据现有证据无法回答该问题'。",
)


def _prompt(query: str, documents: list[dict[str, Any]]) -> str:
    context = "\n\n".join(
        f"[#{index}] 来源：{document['source']}\n{document['content']}"
        for index, document in enumerate(documents, 1)
    )
    return f"{SYSTEM_PROMPT}\n\n证据：\n{context}\n\n问题：{query}\n回答："


async def _register_evidence(
    documents: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    request_id = uuid.uuid4().hex
    sources = []
    records: dict[int, dict[str, Any]] = {}
    for citation_id, document in enumerate(documents, 1):
        source = {
            "id": citation_id,
            "label": f"[#{citation_id}]",
            "source": document["source"],
            "chunk_id": document["chunk_id"],
            "score": round(float(document["score"]), 4),
            "preview": document["content"][:180],
        }
        sources.append(source)
        records[citation_id] = {
            **source,
            "content": document["content"],
            "metadata": document["metadata"],
        }
    await state_store.save_evidence(request_id, records)
    return request_id, sources


async def _retrieve(
    request: ChatRequest,
) -> tuple[list[dict[str, Any]], str, list[dict[str, Any]], bool]:
    cache_payload = {
        "query": request.query,
        "knowledge_base": request.knowledge_base_name,
        "top_k": request.top_k,
        "score_threshold": request.score_threshold,
        "index_version": index_version(request.knowledge_base_name),
    }
    cache_key = state_store.retrieval_cache_key(cache_payload)
    documents = await state_store.get_retrieval(cache_key)
    cache_hit = documents is not None
    if documents is None:
        documents = await asyncio.to_thread(
            hybrid_search,
            request.query,
            request.knowledge_base_name,
            request.top_k,
            request.score_threshold,
        )
        await state_store.save_retrieval(cache_key, documents)
    request_id, sources = await _register_evidence(documents)
    return documents, request_id, sources, cache_hit


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _degraded_answer() -> str:
    return "模型服务暂时不可用，已为你保留检索到的相关证据，请稍后重试。"


async def _stream_answer(
    chat_request: ChatRequest, http_request: Request
) -> AsyncIterator[str]:
    try:
        documents, request_id, sources, cache_hit = await _retrieve(chat_request)
    except Exception as exc:
        logger.exception("retrieval_failed")
        yield _sse("error", {"message": f"检索失败：{type(exc).__name__}"})
        return

    if await http_request.is_disconnected():
        return
    yield _sse(
        "sources",
        {"request_id": request_id, "sources": sources, "cache_hit": cache_hit},
    )
    if not documents:
        answer = "根据现有证据无法回答该问题"
        yield _sse("token", {"text": answer})
        yield _sse("done", {"answer": answer, "request_id": request_id, "degraded": False})
        return

    answer_parts: list[str] = []
    try:
        async for token in model_client.stream(
            _prompt(chat_request.query, documents),
            chat_request.model_name,
            chat_request.temperature,
        ):
            if await http_request.is_disconnected():
                logger.info("stream_cancelled evidence_request_id=%s", request_id)
                return
            answer_parts.append(token)
            yield _sse("token", {"text": token})
    except ModelServiceError:
        logger.warning("model_stream_failed evidence_request_id=%s", request_id)
        answer = normalize_citations("".join(answer_parts), len(sources)) or _degraded_answer()
        if not answer_parts:
            yield _sse("token", {"text": answer})
        yield _sse(
            "done",
            {"answer": answer, "request_id": request_id, "degraded": True},
        )
        return

    answer = normalize_citations("".join(answer_parts), len(sources))
    yield _sse(
        "done",
        {"answer": answer, "request_id": request_id, "degraded": False},
    )


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "coalchat-knowledge-fastapi",
        "llm_configured": _valid_http_url(LLM_API_URL),
        "llm_api_style": LLM_API_STYLE,
        "llm_model": DEFAULT_MODEL,
        "legacy_env_layout": LEGACY_ENV_LAYOUT,
        "state_backend": await state_store.backend(),
    }


@app.post("/api/knowledge/chat")
async def chat(request: ChatRequest) -> dict[str, Any]:
    try:
        documents, request_id, sources, cache_hit = await _retrieve(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"检索失败：{type(exc).__name__}") from exc
    if not documents:
        return {
            "code": 0,
            "data": {
                "answer": "根据现有证据无法回答该问题",
                "request_id": request_id,
                "sources": sources,
                "cache_hit": cache_hit,
                "degraded": False,
            },
        }

    try:
        answer = await model_client.complete(
            _prompt(request.query, documents), request.model_name, request.temperature
        )
        degraded = False
    except ModelServiceError:
        logger.warning("model_call_failed evidence_request_id=%s", request_id)
        answer = _degraded_answer()
        degraded = True

    return {
        "code": 0,
        "data": {
            "answer": normalize_citations(answer, len(sources)),
            "request_id": request_id,
            "sources": sources,
            "cache_hit": cache_hit,
            "degraded": degraded,
        },
    }


@app.post("/api/knowledge/chat/stream")
async def chat_stream(request: ChatRequest, http_request: Request) -> StreamingResponse:
    return StreamingResponse(
        _stream_answer(request, http_request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/knowledge/evidence/{request_id}/{citation_id}")
async def evidence(request_id: str, citation_id: int) -> dict[str, Any]:
    record = await state_store.get_evidence(request_id, citation_id)
    if not record:
        raise HTTPException(status_code=404, detail="引用证据不存在或已过期")
    return record
