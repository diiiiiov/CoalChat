from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT_ENV = PROJECT_ROOT / ".env"
LEGACY_ENV = PROJECT_ROOT / "backen" / ".env"
load_dotenv(dotenv_path=ROOT_ENV if ROOT_ENV.exists() else LEGACY_ENV)

from .model_client import ModelClient, ModelClientConfig, ModelServiceError  # noqa: E402
from .retrieval import (  # noqa: E402
    RETRIEVAL_PIPELINE_VERSION,
    clear_index_cache,
    hybrid_search,
    index_version,
    preload_retrieval_models,
)
from .storage import StateStore  # noqa: E402
from .text_utils import citation_metrics, estimate_tokens, normalize_citations  # noqa: E402
from .query_context import (
    clean_rewritten_query,
    compact_history,
    rewrite_prompt,
    should_rewrite,
)  # noqa: E402
from .document_registry import (  # noqa: E402
    chunk_counts_from_metadata,
    document_block_summaries,
    file_sha256,
    load_document_blocks,
    list_documents,
    register_upload,
    remove_document,
    update_status,
)
from .document_blocks import parser_capabilities  # noqa: E402


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
_rebuild_processes: dict[str, asyncio.subprocess.Process] = {}
_retrieval_tasks: dict[str, asyncio.Task[dict[str, Any]]] = {}
_retrieval_tasks_guard = asyncio.Lock()
_KB_NAME_RE = re.compile(r"^[\w-]+$")
_ALLOWED_UPLOAD_EXTENSIONS = {".txt", ".md", ".docx", ".pdf", ".pptx", ".csv"}
_MAX_UPLOAD_BYTES = 200 * 1024 * 1024


@asynccontextmanager
async def lifespan(_: FastAPI):
    if os.getenv("PRELOAD_RETRIEVAL_MODELS", "false").lower() in {"1", "true", "yes", "on"}:
        knowledge_base = os.getenv("PRELOAD_KNOWLEDGE_BASE", "samples")
        preload_result = await asyncio.to_thread(preload_retrieval_models, knowledge_base)
        logger.info("retrieval_preloaded %s", json.dumps(preload_result, ensure_ascii=False))
    yield
    await state_store.close()


def _knowledge_paths(knowledge_base: str) -> tuple[Path, Path]:
    if not _KB_NAME_RE.fullmatch(knowledge_base):
        raise HTTPException(status_code=400, detail="非法知识库名称")
    root = PROJECT_ROOT / "knowledge_base" / knowledge_base
    return root / "context", root / "vector_store" / "bge-large-zh"


def _safe_filename(filename: str | None) -> str:
    name = Path(filename or "").name
    if not name or name in {".", ".."} or Path(name).suffix.lower() not in _ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail="不支持的文件类型")
    return name


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


class RebuildRequest(BaseModel):
    knowledge_base: str = Field(pattern=r"^[\w-]+$")
    chunk_size: int = Field(default=300, ge=50, le=2000)
    chunk_overlap: int = Field(default=50, ge=0, le=500)


@app.post("/api/knowledge/upload")
async def upload_knowledge_files(
    knowledge_base: str = Form(...),
    chunk_size: int = Form(300),
    chunk_overlap: int = Form(50),
    files: list[UploadFile] = File(..., alias="file"),
) -> dict[str, Any]:
    context_dir, _ = _knowledge_paths(knowledge_base)
    if not 50 <= chunk_size <= 2000 or not 0 <= chunk_overlap < chunk_size:
        raise HTTPException(status_code=400, detail="分段参数无效")
    context_dir.mkdir(parents=True, exist_ok=True)
    uploaded: list[dict[str, Any]] = []
    for upload in files:
        filename = _safe_filename(upload.filename)
        target = context_dir / filename
        temp = context_dir / f".{filename}.{uuid.uuid4().hex}.upload"
        size = 0
        try:
            with temp.open("wb") as output:
                while chunk := await upload.read(1024 * 1024):
                    size += len(chunk)
                    if size > _MAX_UPLOAD_BYTES:
                        raise HTTPException(status_code=413, detail="单个文件超过 200MB")
                    output.write(chunk)
            content_hash = file_sha256(temp)
            existing = next(
                (
                    item
                    for item in list_documents(knowledge_base)
                    if item.get("filename") == filename
                ),
                None,
            )
            unchanged = bool(
                target.exists()
                and existing
                and existing.get("content_hash") == content_hash
            )
            if not unchanged:
                os.replace(temp, target)
                record, _ = register_upload(
                    knowledge_base,
                    filename,
                    content_hash,
                    size,
                    chunk_size,
                    chunk_overlap,
                )
            else:
                record = existing
            uploaded.append(
                {
                    "filename": filename,
                    "path": str(target),
                    "document_id": str(record.get("document_id", "")),
                    "version": int(record.get("version", 1)),
                    "status": "unchanged" if unchanged else "uploaded",
                }
            )
        finally:
            await upload.close()
            temp.unlink(missing_ok=True)
    return {"code": 0, "success": True, "msg": "上传成功", "files": uploaded}


@app.post("/api/knowledge/rebuild_vector")
async def rebuild_vector_store(
    request: RebuildRequest,
) -> dict[str, Any]:
    knowledge_base = request.knowledge_base
    chunk_size = request.chunk_size
    chunk_overlap = request.chunk_overlap
    context_dir, vector_dir = _knowledge_paths(knowledge_base)
    if not 50 <= chunk_size <= 2000 or not 0 <= chunk_overlap < chunk_size:
        raise HTTPException(status_code=400, detail="分段参数无效")
    if knowledge_base in _rebuild_processes:
        raise HTTPException(status_code=409, detail="该知识库正在重建")
    context_dir.mkdir(parents=True, exist_ok=True)
    vector_dir.mkdir(parents=True, exist_ok=True)
    source_files = [
        path
        for path in context_dir.iterdir()
        if path.is_file() and path.suffix.lower() in _ALLOWED_UPLOAD_EXTENSIONS
    ]
    known = {item.get("filename") for item in list_documents(knowledge_base)}
    for source in source_files:
        if source.name not in known:
            register_upload(
                knowledge_base,
                source.name,
                file_sha256(source),
                source.stat().st_size,
                chunk_size,
                chunk_overlap,
            )
    filenames = [path.name for path in source_files]
    update_status(knowledge_base, filenames, "indexing")
    # A retrieval request may have a large embedding/reranker model cached in
    # this API process. Release it before the isolated build worker loads its
    # own model, which is especially important for Windows commit-space limits.
    clear_index_cache()
    script = PROJECT_ROOT / "backen" / "knowledge" / "scripts" / "build_faiss.py"
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            str(script),
            "--input_dir",
            str(context_dir),
            "--output_dir",
            str(vector_dir),
            "--chunk_size",
            str(chunk_size),
            "--overlap",
            str(chunk_overlap),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        update_status(knowledge_base, filenames, "failed", error=str(exc))
        raise HTTPException(status_code=500, detail="无法启动索引进程") from exc
    _rebuild_processes[knowledge_base] = process
    try:
        stdout, stderr = await process.communicate()
    finally:
        _rebuild_processes.pop(knowledge_base, None)
    if process.returncode != 0:
        error_text = stderr.decode("utf-8", errors="ignore")[-2000:]
        if "os error 1455" in error_text.lower() or "paging" in error_text.lower():
            error_text = (
                "Windows 虚拟内存不足：请先关闭重复的 FastAPI/ Python 服务，"
                "再重启单个知识服务后重建。原始错误：" + error_text
            )
        update_status(knowledge_base, filenames, "failed", error=error_text)
        raise HTTPException(
            status_code=500,
            detail=f"向量库重建失败：{error_text}",
        )
    active_version = index_version(knowledge_base)
    chunk_counts = chunk_counts_from_metadata(vector_dir / "index.pkl")
    block_summaries = document_block_summaries(knowledge_base)
    update_status(
        knowledge_base,
        filenames,
        "completed",
        index_version=active_version,
        chunk_counts=chunk_counts,
        block_summaries=block_summaries,
    )
    return {
        "code": 0,
        "msg": "向量库重建成功",
        "output": stdout.decode("utf-8", errors="ignore")[-2000:],
        "index_version": active_version,
        "documents": list_documents(knowledge_base),
    }


@app.post("/api/knowledge/cancel_upload")
async def cancel_knowledge_operation(payload: dict[str, Any]) -> dict[str, Any]:
    knowledge_base = str(payload.get("knowledge_base") or "")
    context_dir, vector_dir = _knowledge_paths(knowledge_base)
    process = _rebuild_processes.pop(knowledge_base, None)
    if process and process.returncode is None:
        process.kill()
        await process.communicate()
    filename = payload.get("filename")
    if filename:
        safe_name = _safe_filename(str(filename))
        (context_dir / safe_name).unlink(missing_ok=True)
        update_status(knowledge_base, [safe_name], "cancelled")
    elif process:
        update_status(
            knowledge_base,
            [item.get("filename", "") for item in list_documents(knowledge_base)],
            "cancelled",
        )
    for temp in vector_dir.glob("*.tmp"):
        temp.unlink(missing_ok=True)
    return {"code": 0, "msg": "操作已取消"}


@app.get("/api/knowledge/documents")
async def knowledge_documents(knowledge_base: str = "samples") -> dict[str, Any]:
    _knowledge_paths(knowledge_base)
    return {"code": 0, "documents": list_documents(knowledge_base)}


@app.get("/api/knowledge/parser-capabilities")
async def knowledge_parser_capabilities() -> dict[str, Any]:
    return {"code": 0, "capabilities": parser_capabilities()}


@app.get("/api/knowledge/documents/{filename}/blocks")
async def knowledge_document_blocks(
    filename: str,
    knowledge_base: str = "samples",
    page: int | None = None,
    block_type: str | None = None,
) -> dict[str, Any]:
    _knowledge_paths(knowledge_base)
    safe_name = _safe_filename(filename)
    document = next(
        (item for item in list_documents(knowledge_base) if item.get("filename") == safe_name),
        None,
    )
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")
    blocks = load_document_blocks(knowledge_base, str(document.get("document_id", "")))
    if page is not None:
        blocks = [item for item in blocks if item.get("page") == page]
    if block_type:
        blocks = [item for item in blocks if item.get("block_type") == block_type]
    document_id = str(document.get("document_id", ""))
    for block in blocks:
        asset_name = (block.get("metadata") or {}).get("asset_name")
        if asset_name:
            block["asset_url"] = (
                f"/api/knowledge/assets/{knowledge_base}/{document_id}/{asset_name}"
            )
    return {"code": 0, "document": document, "blocks": blocks}


@app.get("/api/knowledge/assets/{knowledge_base}/{document_id}/{asset_name}")
async def knowledge_document_asset(
    knowledge_base: str, document_id: str, asset_name: str
) -> FileResponse:
    _knowledge_paths(knowledge_base)
    if not re.fullmatch(r"[a-f0-9]{24}", document_id):
        raise HTTPException(status_code=400, detail="非法文档标识")
    safe_asset = Path(asset_name).name
    if safe_asset != asset_name or Path(safe_asset).suffix.lower() not in {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".gif",
        ".bmp",
        ".tif",
        ".tiff",
    }:
        raise HTTPException(status_code=400, detail="非法资产名称")
    asset = (
        PROJECT_ROOT
        / "knowledge_base"
        / knowledge_base
        / "parsed"
        / "assets"
        / document_id
        / safe_asset
    )
    if not asset.exists():
        raise HTTPException(status_code=404, detail="视觉资产不存在")
    return FileResponse(asset)


@app.delete("/api/knowledge/documents/{filename}")
async def delete_knowledge_document(
    filename: str,
    knowledge_base: str = "samples",
    chunk_size: int = 300,
    chunk_overlap: int = 50,
) -> dict[str, Any]:
    context_dir, _ = _knowledge_paths(knowledge_base)
    safe_name = _safe_filename(filename)
    target = context_dir / safe_name
    if not target.exists():
        raise HTTPException(status_code=404, detail="文档不存在")
    remaining = [
        path
        for path in context_dir.iterdir()
        if path.is_file()
        and path != target
        and path.suffix.lower() in _ALLOWED_UPLOAD_EXTENSIONS
    ]
    if not remaining:
        raise HTTPException(status_code=409, detail="暂不支持删除知识库中的最后一个文档")
    trash_dir = context_dir / ".trash"
    trash_dir.mkdir(exist_ok=True)
    recoverable = trash_dir / f"{uuid.uuid4().hex}-{safe_name}"
    os.replace(target, recoverable)
    try:
        rebuild_result = await rebuild_vector_store(
            RebuildRequest(
                knowledge_base=knowledge_base,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
        )
    except Exception:
        os.replace(recoverable, target)
        raise
    remove_document(knowledge_base, safe_name)
    recoverable.unlink(missing_ok=True)
    return {
        "code": 0,
        "msg": "文档及其索引已删除",
        "filename": safe_name,
        "index_version": rebuild_result["index_version"],
    }


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


async def _standalone_query(request: ChatRequest) -> str:
    history = compact_history(request.history, request.query)
    if not should_rewrite(request.query, history):
        return request.query
    if os.getenv("QUERY_REWRITE_ENABLED", "true").lower() not in {"1", "true", "yes", "on"}:
        return request.query
    try:
        rewritten = await model_client.complete(
            rewrite_prompt(request.query, history), request.model_name, 0.0
        )
        return clean_rewritten_query(rewritten, request.query)
    except ModelServiceError:
        logger.warning("query_rewrite_failed; using original query")
        return request.query


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
            "retrieval_mode": document.get("retrieval_mode", "hybrid"),
            "reranked": bool(document.get("reranked", False)),
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
    retrieval_query: str,
) -> tuple[list[dict[str, Any]], str, list[dict[str, Any]], bool, dict[str, Any]]:
    retrieve_started = time.perf_counter()
    cache_payload = {
        "query": retrieval_query,
        "knowledge_base": request.knowledge_base_name,
        "top_k": request.top_k,
        "score_threshold": request.score_threshold,
        "index_version": index_version(request.knowledge_base_name),
        "pipeline_version": RETRIEVAL_PIPELINE_VERSION,
    }
    cache_key = state_store.retrieval_cache_key(cache_payload)
    cached = await state_store.get_retrieval(cache_key)
    cache_hit = cached is not None
    diagnostics: dict[str, Any] = {}
    if isinstance(cached, dict) and "documents" in cached:
        documents = cached.get("documents") or []
        diagnostics = dict(cached.get("diagnostics") or {})
    elif isinstance(cached, list):
        documents = cached
        diagnostics = {"cache_format": "legacy"}
    else:
        documents = None
    coalesced = False
    if documents is None:
        async def run_retrieval() -> dict[str, Any]:
            local_diagnostics: dict[str, Any] = {}
            local_documents = await asyncio.to_thread(
                hybrid_search,
                retrieval_query,
                request.knowledge_base_name,
                request.top_k,
                request.score_threshold,
                local_diagnostics,
            )
            payload = {"documents": local_documents, "diagnostics": local_diagnostics}
            await state_store.save_retrieval(cache_key, payload)
            return payload

        async with _retrieval_tasks_guard:
            task = _retrieval_tasks.get(cache_key)
            if task is None:
                task = asyncio.create_task(run_retrieval())
                _retrieval_tasks[cache_key] = task
            else:
                coalesced = True
        try:
            payload = await asyncio.shield(task)
            documents = payload["documents"]
            diagnostics = dict(payload["diagnostics"])
        finally:
            if task.done():
                async with _retrieval_tasks_guard:
                    if _retrieval_tasks.get(cache_key) is task:
                        _retrieval_tasks.pop(cache_key, None)
    diagnostics = {
        **diagnostics,
        "cache_hit": cache_hit,
        "request_coalesced": coalesced,
        "request_retrieval_ms": round(
            (time.perf_counter() - retrieve_started) * 1000, 2
        ),
    }
    request_id, sources = await _register_evidence(documents)
    return documents, request_id, sources, cache_hit, diagnostics


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _degraded_answer() -> str:
    return "模型服务暂时不可用，已为你保留检索到的相关证据，请稍后重试。"


async def _stream_answer(
    chat_request: ChatRequest, http_request: Request
) -> AsyncIterator[str]:
    request_started = time.perf_counter()
    rewrite_started = time.perf_counter()
    try:
        rewritten_query = await _standalone_query(chat_request)
        rewrite_ms = round((time.perf_counter() - rewrite_started) * 1000, 2)
        documents, request_id, sources, cache_hit, retrieval_trace = await _retrieve(
            chat_request, rewritten_query
        )
    except Exception as exc:
        logger.exception("retrieval_failed")
        yield _sse("error", {"message": f"检索失败：{type(exc).__name__}"})
        return

    if await http_request.is_disconnected():
        return
    trace: dict[str, Any] = {
        "query_rewrite_ms": rewrite_ms,
        "query_rewritten": rewritten_query != chat_request.query,
        "retrieval": retrieval_trace,
    }
    yield _sse(
        "sources",
        {
            "request_id": request_id,
            "sources": sources,
            "cache_hit": cache_hit,
            "rewritten_query": rewritten_query,
            "trace": trace,
        },
    )
    if not documents:
        answer = "根据现有证据无法回答该问题"
        yield _sse("token", {"text": answer})
        trace["total_ms"] = round((time.perf_counter() - request_started) * 1000, 2)
        trace["citations"] = citation_metrics(answer, len(sources))
        logger.info("rag_trace %s", json.dumps({"request_id": request_id, **trace}, ensure_ascii=False))
        yield _sse(
            "done",
            {"answer": answer, "request_id": request_id, "degraded": False, "trace": trace},
        )
        return

    answer_parts: list[str] = []
    prompt = _prompt(
        f"{chat_request.query}\n独立检索问题：{rewritten_query}", documents
    )
    generation_started = time.perf_counter()
    first_token_ms: float | None = None
    try:
        async for token in model_client.stream(
            prompt,
            chat_request.model_name,
            chat_request.temperature,
        ):
            if await http_request.is_disconnected():
                logger.info("stream_cancelled evidence_request_id=%s", request_id)
                return
            if first_token_ms is None:
                first_token_ms = round((time.perf_counter() - generation_started) * 1000, 2)
            answer_parts.append(token)
            yield _sse("token", {"text": token})
    except ModelServiceError:
        logger.warning("model_stream_failed evidence_request_id=%s", request_id)
        answer = normalize_citations("".join(answer_parts), len(sources)) or _degraded_answer()
        trace.update(
            {
                "first_token_ms": first_token_ms,
                "generation_ms": round((time.perf_counter() - generation_started) * 1000, 2),
                "total_ms": round((time.perf_counter() - request_started) * 1000, 2),
                "token_usage": {
                    "estimated_prompt_tokens": estimate_tokens(prompt),
                    "estimated_completion_tokens": estimate_tokens(answer),
                },
                "citations": citation_metrics(answer, len(sources)),
            }
        )
        if not answer_parts:
            yield _sse("token", {"text": answer})
        logger.info("rag_trace %s", json.dumps({"request_id": request_id, **trace}, ensure_ascii=False))
        yield _sse(
            "done",
            {"answer": answer, "request_id": request_id, "degraded": True, "trace": trace},
        )
        return

    answer = normalize_citations("".join(answer_parts), len(sources))
    trace.update(
        {
            "first_token_ms": first_token_ms,
            "generation_ms": round((time.perf_counter() - generation_started) * 1000, 2),
            "total_ms": round((time.perf_counter() - request_started) * 1000, 2),
            "token_usage": {
                "estimated_prompt_tokens": estimate_tokens(prompt),
                "estimated_completion_tokens": estimate_tokens(answer),
            },
            "citations": citation_metrics(answer, len(sources)),
        }
    )
    logger.info("rag_trace %s", json.dumps({"request_id": request_id, **trace}, ensure_ascii=False))
    yield _sse(
        "done",
        {"answer": answer, "request_id": request_id, "degraded": False, "trace": trace},
    )


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "coalchat-knowledge-fastapi",
        "llm_configured": _valid_http_url(LLM_API_URL),
        "llm_api_style": LLM_API_STYLE,
        "llm_model": DEFAULT_MODEL,
        "retrieval_pipeline": RETRIEVAL_PIPELINE_VERSION,
        "legacy_env_layout": LEGACY_ENV_LAYOUT,
        "state_backend": await state_store.backend(),
        "performance": {
            "retrieval_max_concurrency": int(os.getenv("RETRIEVAL_MAX_CONCURRENCY", "2")),
            "reranker_max_concurrency": int(os.getenv("RERANKER_MAX_CONCURRENCY", "1")),
            "reranker_cpu_threads": int(
                os.getenv("RERANKER_CPU_THREADS", str(min(os.cpu_count() or 1, 12)))
            ),
            "preload_retrieval_models": os.getenv(
                "PRELOAD_RETRIEVAL_MODELS", "false"
            ).lower() in {"1", "true", "yes", "on"},
        },
    }


@app.post("/api/knowledge/chat")
async def chat(request: ChatRequest) -> dict[str, Any]:
    request_started = time.perf_counter()
    rewrite_started = time.perf_counter()
    try:
        rewritten_query = await _standalone_query(request)
        rewrite_ms = round((time.perf_counter() - rewrite_started) * 1000, 2)
        documents, request_id, sources, cache_hit, retrieval_trace = await _retrieve(
            request, rewritten_query
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"检索失败：{type(exc).__name__}") from exc
    if not documents:
        answer = "根据现有证据无法回答该问题"
        trace = {
            "query_rewrite_ms": rewrite_ms,
            "query_rewritten": rewritten_query != request.query,
            "retrieval": retrieval_trace,
            "total_ms": round((time.perf_counter() - request_started) * 1000, 2),
            "citations": citation_metrics(answer, len(sources)),
        }
        logger.info("rag_trace %s", json.dumps({"request_id": request_id, **trace}, ensure_ascii=False))
        return {
            "code": 0,
            "data": {
                "answer": answer,
                "request_id": request_id,
                "sources": sources,
                "cache_hit": cache_hit,
                "rewritten_query": rewritten_query,
                "trace": trace,
                "degraded": False,
            },
        }

    prompt = _prompt(
        f"{request.query}\n独立检索问题：{rewritten_query}", documents
    )
    generation_started = time.perf_counter()
    provider_usage: dict[str, Any] = {}
    try:
        answer, provider_usage = await model_client.complete_with_usage(
            prompt,
            request.model_name,
            request.temperature,
        )
        degraded = False
    except ModelServiceError:
        logger.warning("model_call_failed evidence_request_id=%s", request_id)
        answer = _degraded_answer()
        degraded = True

    normalized_answer = normalize_citations(answer, len(sources))
    trace = {
        "query_rewrite_ms": rewrite_ms,
        "query_rewritten": rewritten_query != request.query,
        "retrieval": retrieval_trace,
        "generation_ms": round((time.perf_counter() - generation_started) * 1000, 2),
        "total_ms": round((time.perf_counter() - request_started) * 1000, 2),
        "token_usage": provider_usage
        or {
            "estimated_prompt_tokens": estimate_tokens(prompt),
            "estimated_completion_tokens": estimate_tokens(normalized_answer),
        },
        "citations": citation_metrics(normalized_answer, len(sources)),
    }
    logger.info("rag_trace %s", json.dumps({"request_id": request_id, **trace}, ensure_ascii=False))

    return {
        "code": 0,
        "data": {
            "answer": normalized_answer,
            "request_id": request_id,
            "sources": sources,
            "cache_hit": cache_hit,
            "rewritten_query": rewritten_query,
            "trace": trace,
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
