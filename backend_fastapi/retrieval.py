from __future__ import annotations

import math
import os
import pickle
import re
import sys
import time
import gc
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_ROOT = PROJECT_ROOT / "knowledge_base"
DEFAULT_EMBED_MODEL = (
    KNOWLEDGE_ROOT / "samples" / "vector_store" / "bge-large-zh"
)
DEFAULT_RERANKER = PROJECT_ROOT / "backen" / "knowledge" / "bge-reranker-base"
DEFAULT_RERANKER_MAX_LENGTH = 320
RETRIEVAL_PIPELINE_VERSION = "weighted-routing-v2-exact-preserve"
_RETRIEVAL_GATE = threading.BoundedSemaphore(
    max(1, int(os.getenv("RETRIEVAL_MAX_CONCURRENCY", "2")))
)
_RERANKER_GATE = threading.BoundedSemaphore(
    max(1, int(os.getenv("RERANKER_MAX_CONCURRENCY", "1")))
)


@dataclass(frozen=True)
class RetrievalStrategy:
    mode: str
    dense_weight: float
    sparse_weight: float
    rerank: bool


_STRONG_EXACT_RE = re.compile(
    r"(?:第\s*[一二三四五六七八九十百千万\d]+\s*条|"
    r"\d+(?:\.\d+)?\s*(?:%|％|mm|cm|m|km|v|kv|a|ma|mpa|pa|℃|度|米|毫米|厘米|兆帕)|"
    r"[a-zA-Z]{1,8}[-_/]?\d{2,}[a-zA-Z0-9-]*)",
    re.IGNORECASE,
)
_EXACT_LOOKUP_RE = re.compile(
    r"多少|数值|限值|比例|平均厚度|单位涌水量|渗透系数|矿化度|预计费用|生产能力|累计.{0,8}进尺"
)
_RELATIONAL_RE = re.compile(r"原因|导致|影响|关系|关联|为什么|为何|流程|步骤|先后|如何处置|怎么处理")
_SUMMARY_RE = re.compile(r"总结|概述|总体|主要有哪些|全部|综合说明|整体")


def is_exact_query(query: str) -> bool:
    return bool(_STRONG_EXACT_RE.search(query) or _EXACT_LOOKUP_RE.search(query))


def analyze_query(query: str) -> RetrievalStrategy:
    """Choose a low-cost retrieval route from stable, inspectable rules."""
    if is_exact_query(query):
        # BM25 remains dominant, while a small dense pool gives the reranker
        # enough candidates to recover paraphrased exact lookups.
        return RetrievalStrategy("exact", dense_weight=1.0, sparse_weight=1.0, rerank=True)
    if _SUMMARY_RE.search(query):
        return RetrievalStrategy("summary", dense_weight=1.2, sparse_weight=0.8, rerank=True)
    if _RELATIONAL_RE.search(query):
        return RetrievalStrategy("relational", dense_weight=1.1, sparse_weight=0.9, rerank=True)
    # The current coal-mine corpus benchmark favors BM25, so semantic queries
    # still keep a modest sparse bias instead of returning to equal-weight RRF.
    return RetrievalStrategy("semantic", dense_weight=0.7, sparse_weight=1.3, rerank=True)


def should_use_reranker(
    strategy: RetrievalStrategy,
    dense: list[int] | None = None,
    sparse: list[int] | None = None,
) -> bool:
    policy = os.getenv("RERANKER_POLICY", "auto").strip().lower()
    if policy == "always":
        return True
    if policy == "never":
        return False
    if not strategy.rerank:
        return False
    if strategy.mode == "exact":
        return True
    if strategy.mode == "summary" or not dense or not sparse:
        return True
    # When both retrievers already agree on at least two of their top three
    # candidates, the expensive cross-encoder usually has little ordering work
    # left to do. Disagreement is treated as ambiguity and triggers reranking.
    top_overlap = len(set(dense[:3]) & set(sparse[:3]))
    required_overlap = max(1, int(os.getenv("RERANKER_SKIP_TOP3_OVERLAP", "2")))
    return top_overlap < required_overlap


def index_version(knowledge_base: str) -> str:
    vector_dir = KNOWLEDGE_ROOT / knowledge_base / "vector_store" / "bge-large-zh"
    parts = []
    for path in (vector_dir / "index.faiss", vector_dir / "index.pkl"):
        stat = path.stat()
        parts.append(f"{stat.st_mtime_ns}:{stat.st_size}")
    return "|".join(parts)


def _tokens(text: str) -> list[str]:
    """Tokenize Chinese without depending on a system dictionary."""
    text = text.lower()
    latin = re.findall(r"[a-z0-9_]+", text)
    chinese = re.findall(r"[\u4e00-\u9fff]", text)
    bigrams = ["".join(chinese[i : i + 2]) for i in range(len(chinese) - 1)]
    return latin + chinese + bigrams


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


@dataclass
class KnowledgeIndex:
    index: Any
    metadatas: list[dict[str, Any]]
    embedder: Any
    bm25: Any


@lru_cache(maxsize=8)
def _load_index_version(knowledge_base: str, version: str) -> KnowledgeIndex:
    # Keep the API process lightweight until retrieval is actually requested.
    # On Windows, importing PyTorch in both the API process and an index-build
    # child process can exhaust commit space or crash a native DLL during a
    # rebuild, even before either process loads a model.
    import faiss
    from rank_bm25 import BM25Okapi
    from sentence_transformers import SentenceTransformer

    vector_dir = KNOWLEDGE_ROOT / knowledge_base / "vector_store" / "bge-large-zh"
    index_path = vector_dir / "index.faiss"
    metadata_path = vector_dir / "index.pkl"
    if not index_path.exists() or not metadata_path.exists():
        raise FileNotFoundError(f"知识库索引不存在：{knowledge_base}")

    index = faiss.read_index(str(index_path))
    with metadata_path.open("rb") as file:
        raw_metadatas = pickle.load(file)

    metadatas: list[dict[str, Any]] = []
    for position, raw in enumerate(raw_metadatas):
        metadata = raw if isinstance(raw, dict) else {"content": str(raw)}
        content = metadata.get("content") or metadata.get("text") or str(raw)
        metadatas.append({**metadata, "content": content, "chunk_id": position})

    model_path = Path(os.getenv("EMBED_MODEL_PATH", str(DEFAULT_EMBED_MODEL)))
    embedder = SentenceTransformer(str(model_path))
    bm25 = BM25Okapi([_tokens(item["content"]) for item in metadatas])
    if index.ntotal != len(metadatas):
        raise RuntimeError(
            f"索引与元数据不一致：vectors={index.ntotal}, metadata={len(metadatas)}"
        )
    if index_version(knowledge_base) != version:
        raise RuntimeError("索引在加载期间发生了更新")
    return KnowledgeIndex(index=index, metadatas=metadatas, embedder=embedder, bm25=bm25)


def load_index(knowledge_base: str) -> KnowledgeIndex:
    """Load an index keyed by its on-disk version, retrying across publication."""
    last_error: Exception | None = None
    for attempt in range(3):
        version = index_version(knowledge_base)
        try:
            return _load_index_version(knowledge_base, version)
        except RuntimeError as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(0.05)
    raise RuntimeError(f"无法加载一致的知识库索引：{knowledge_base}") from last_error


def clear_index_cache() -> None:
    """Release model-backed caches before publishing or rebuilding an index."""
    _load_index_version.cache_clear()
    load_reranker.cache_clear()
    gc.collect()
    # Avoid importing torch merely for cleanup. If retrieval already loaded it,
    # release allocator-held device memory before starting the build worker.
    torch_module = sys.modules.get("torch")
    cuda = getattr(torch_module, "cuda", None)
    if cuda is not None and cuda.is_available():
        cuda.empty_cache()


def preload_retrieval_models(knowledge_base: str = "samples") -> dict[str, Any]:
    """Load index and reranker before readiness to avoid first-user cold start."""
    started = time.perf_counter()
    store = load_index(knowledge_base)
    reranker = load_reranker()
    return {
        "knowledge_base": knowledge_base,
        "index_chunks": len(store.metadatas),
        "reranker_available": reranker is not None,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


@lru_cache(maxsize=1)
def load_reranker() -> Any | None:
    model_path = Path(os.getenv("RERANKER_MODEL_PATH", str(DEFAULT_RERANKER)))
    if not model_path.exists():
        return None
    try:
        from sentence_transformers import CrossEncoder
        import torch

        default_threads = min(os.cpu_count() or 1, 12)
        cpu_threads = max(1, int(os.getenv("RERANKER_CPU_THREADS", str(default_threads))))
        torch.set_num_threads(cpu_threads)

        max_length = int(
            os.getenv("RERANKER_MAX_LENGTH", str(DEFAULT_RERANKER_MAX_LENGTH))
        )
        if max_length <= 0:
            max_length = DEFAULT_RERANKER_MAX_LENGTH
        return CrossEncoder(
            str(model_path),
            num_labels=1,
            max_length=max_length,
        )
    except Exception:
        return None


def _rank_map(indices: list[int]) -> dict[int, int]:
    return {document_index: rank for rank, document_index in enumerate(indices, 1)}


def _hybrid_search_impl(
    query: str,
    knowledge_base: str,
    top_k: int = 5,
    score_threshold: float = 0.0,
    diagnostics: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Route, fuse weighted candidates, then selectively rerank."""
    import numpy as np

    total_started = time.perf_counter()
    load_started = time.perf_counter()
    store = load_index(knowledge_base)
    load_ms = (time.perf_counter() - load_started) * 1000
    strategy = analyze_query(query)
    candidate_k = min(len(store.metadatas), max(top_k * 4, 20))
    if candidate_k == 0:
        return []

    dense: list[int] = []
    dense_started = time.perf_counter()
    if strategy.dense_weight > 0:
        query_vector = store.embedder.encode(
            [query], normalize_embeddings=True
        ).astype("float32")
        _, dense_indices = store.index.search(query_vector, candidate_k)
        dense = [int(i) for i in dense_indices[0] if 0 <= i < len(store.metadatas)]
    dense_ms = (time.perf_counter() - dense_started) * 1000

    sparse_started = time.perf_counter()
    sparse_scores = np.asarray(store.bm25.get_scores(_tokens(query)))
    sparse = [
        int(index)
        for index in np.argsort(sparse_scores)[::-1]
        if sparse_scores[index] > 0
    ][:candidate_k]
    sparse_ms = (time.perf_counter() - sparse_started) * 1000

    fusion_started = time.perf_counter()
    dense_ranks = _rank_map(dense)
    sparse_ranks = _rank_map(sparse)
    candidate_ids = set(dense_ranks) | set(sparse_ranks)
    rrf_k = max(1, int(os.getenv("RRF_K", "60")))
    fused: list[tuple[int, float]] = []
    for document_id in candidate_ids:
        score = 0.0
        if document_id in dense_ranks:
            score += strategy.dense_weight / (rrf_k + dense_ranks[document_id])
        if document_id in sparse_ranks:
            score += strategy.sparse_weight / (rrf_k + sparse_ranks[document_id])
        fused.append((document_id, score))
    fused.sort(key=lambda item: item[1], reverse=True)
    fused = fused[:candidate_k]
    fusion_ms = (time.perf_counter() - fusion_started) * 1000

    candidates = []
    best_fusion = fused[0][1] if fused else 1.0
    for document_id, fusion_score in fused:
        metadata = store.metadatas[document_id]
        candidates.append(
            {
                "document_index": document_id,
                "content": metadata["content"],
                "source": metadata.get("file") or metadata.get("source") or "未知来源",
                "chunk_id": metadata.get("chunk_id", document_id),
                "metadata": _json_safe(metadata),
                "fusion_score": fusion_score / best_fusion,
                "retrieval_mode": strategy.mode,
                "dense_weight": strategy.dense_weight,
                "sparse_weight": strategy.sparse_weight,
                "reranked": False,
            }
        )

    rerank_requested = should_use_reranker(strategy, dense, sparse)
    reranker_load_started = time.perf_counter()
    reranker = load_reranker() if rerank_requested else None
    reranker_load_ms = (
        (time.perf_counter() - reranker_load_started) * 1000 if rerank_requested else 0.0
    )
    rerank_started = time.perf_counter()
    exact_preserved = 0
    if reranker and candidates:
        # Keep the wider retrieval pool for recall, but only send the leading
        # candidates through the expensive cross-encoder. When callers request
        # more than 10 results, rerank enough candidates to honor top_k.
        configured_k = max(top_k, int(os.getenv("RERANKER_CANDIDATE_K", "10")))
        if strategy.mode == "exact":
            configured_k = max(
                configured_k,
                int(os.getenv("EXACT_RERANKER_CANDIDATE_K", "20")),
            )
        reranker_input_k = min(len(candidates), configured_k)
        candidates = candidates[:reranker_input_k]
        pairs = [(query, item["content"]) for item in candidates]
        reranker_queue_started = time.perf_counter()
        with _RERANKER_GATE:
            reranker_queue_ms = (time.perf_counter() - reranker_queue_started) * 1000
            raw_scores = np.asarray(reranker.predict(pairs)).reshape(-1)
        for item, raw_score in zip(candidates, raw_scores):
            # BGE rerankers may expose logits, so normalize them to [0, 1].
            item["score"] = 1.0 / (1.0 + math.exp(-float(raw_score)))
            item["reranked"] = True
        candidates.sort(key=lambda item: item["score"], reverse=True)
        if strategy.mode == "exact" and top_k > 1:
            # Preserve the strongest lexical matches, then fill from semantic
            # reranking. This prevents clauses and measurements from being
            # displaced entirely by the cross-encoder.
            by_id = {item["document_index"]: item for item in candidates}
            reranked_top3 = {item["document_index"] for item in candidates[:3]}
            top3_overlap = len(set(sparse[:3]) & reranked_top3)
            # Strong disagreement means semantic reranking is uncertain for an
            # entity-heavy lookup, so retain four lexical results. Otherwise
            # two protected results leave more room for semantic recovery.
            preserve_k = min(4 if top3_overlap <= 1 else 2, top_k)
            protected = [by_id[item] for item in sparse[:preserve_k] if item in by_id]
            seen = {item["document_index"] for item in protected}
            candidates = protected + [
                item for item in candidates if item["document_index"] not in seen
            ]
            exact_preserved = len(protected)
    else:
        for item in candidates:
            item["score"] = item["fusion_score"]

    rerank_ms = (time.perf_counter() - rerank_started) * 1000 if reranker else 0.0

    filtered = [item for item in candidates if item["score"] >= score_threshold]
    if diagnostics is not None:
        diagnostics.update(
            {
                "pipeline_version": RETRIEVAL_PIPELINE_VERSION,
                "retrieval_mode": strategy.mode,
                "dense_weight": strategy.dense_weight,
                "sparse_weight": strategy.sparse_weight,
                "candidate_limit": candidate_k,
                "dense_candidates": len(dense),
                "sparse_candidates": len(sparse),
                "fused_candidates": len(fused),
                "returned_candidates": min(len(filtered), top_k),
                "reranker_requested": rerank_requested,
                "reranker_available": reranker is not None,
                "reranked_candidates": len(candidates) if reranker else 0,
                "exact_sparse_preserved": exact_preserved,
                "reranker_queue_ms": round(reranker_queue_ms, 2) if reranker else 0.0,
                "timings_ms": {
                    "index_load": round(load_ms, 2),
                    "dense": round(dense_ms, 2),
                    "sparse": round(sparse_ms, 2),
                    "fusion": round(fusion_ms, 2),
                    "reranker_load": round(reranker_load_ms, 2),
                    "rerank": round(rerank_ms, 2),
                    "total": round((time.perf_counter() - total_started) * 1000, 2),
                },
            }
        )
    results = []
    exact_context_radius = max(0, int(os.getenv("EXACT_CONTEXT_RADIUS", "2")))
    for item in filtered[:top_k]:
        result = dict(item)
        document_index = int(result.pop("document_index"))
        if strategy.mode == "exact" and exact_context_radius:
            source = result["source"]
            expanded_ids = [
                neighbor
                for neighbor in range(
                    max(0, document_index - exact_context_radius),
                    min(len(store.metadatas), document_index + exact_context_radius + 1),
                )
                if (
                    store.metadatas[neighbor].get("file")
                    or store.metadatas[neighbor].get("source")
                    or "鏈煡鏉ユ簮"
                )
                == source
            ]
            result["content"] = "\n\n".join(
                store.metadatas[neighbor]["content"] for neighbor in expanded_ids
            )
            result["covered_chunk_ids"] = expanded_ids
            result["metadata"] = {
                **result["metadata"],
                "expanded_chunk_ids": expanded_ids,
                "exact_context_radius": exact_context_radius,
            }
        results.append(result)
    return results


def hybrid_search(
    query: str,
    knowledge_base: str,
    top_k: int = 5,
    score_threshold: float = 0.0,
    diagnostics: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Bound concurrent model work to keep CPU latency and memory predictable."""
    queued_at = time.perf_counter()
    with _RETRIEVAL_GATE:
        queue_ms = (time.perf_counter() - queued_at) * 1000
        results = _hybrid_search_impl(
            query, knowledge_base, top_k, score_threshold, diagnostics
        )
    if diagnostics is not None:
        diagnostics["retrieval_queue_ms"] = round(queue_ms, 2)
    return results
