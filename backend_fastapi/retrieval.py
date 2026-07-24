from __future__ import annotations

import math
import os
import pickle
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import faiss
import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder, SentenceTransformer


PROJECT_ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_ROOT = PROJECT_ROOT / "knowledge_base"
DEFAULT_EMBED_MODEL = (
    KNOWLEDGE_ROOT / "samples" / "vector_store" / "bge-large-zh"
)
DEFAULT_RERANKER = PROJECT_ROOT / "backen" / "knowledge" / "bge-reranker-base"


def index_version(knowledge_base: str) -> str:
    index_path = KNOWLEDGE_ROOT / knowledge_base / "vector_store" / "bge-large-zh" / "index.faiss"
    stat = index_path.stat()
    return f"{stat.st_mtime_ns}:{stat.st_size}"


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
    embedder: SentenceTransformer
    bm25: BM25Okapi


@lru_cache(maxsize=4)
def load_index(knowledge_base: str) -> KnowledgeIndex:
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
    return KnowledgeIndex(index=index, metadatas=metadatas, embedder=embedder, bm25=bm25)


@lru_cache(maxsize=1)
def load_reranker() -> CrossEncoder | None:
    model_path = Path(os.getenv("RERANKER_MODEL_PATH", str(DEFAULT_RERANKER)))
    if not model_path.exists():
        return None
    try:
        return CrossEncoder(str(model_path), num_labels=1)
    except Exception:
        return None


def _rank_map(indices: list[int]) -> dict[int, int]:
    return {document_index: rank for rank, document_index in enumerate(indices, 1)}


def hybrid_search(
    query: str,
    knowledge_base: str,
    top_k: int = 5,
    score_threshold: float = 0.0,
) -> list[dict[str, Any]]:
    """Fuse dense and BM25 candidates with RRF, then optionally rerank."""
    store = load_index(knowledge_base)
    candidate_k = min(len(store.metadatas), max(top_k * 4, 20))
    if candidate_k == 0:
        return []

    query_vector = store.embedder.encode(
        [query], normalize_embeddings=True
    ).astype("float32")
    _, dense_indices = store.index.search(query_vector, candidate_k)
    dense = [int(i) for i in dense_indices[0] if 0 <= i < len(store.metadatas)]

    sparse_scores = np.asarray(store.bm25.get_scores(_tokens(query)))
    sparse = np.argsort(sparse_scores)[::-1][:candidate_k].astype(int).tolist()

    dense_ranks = _rank_map(dense)
    sparse_ranks = _rank_map(sparse)
    candidate_ids = set(dense_ranks) | set(sparse_ranks)
    rrf_k = 60
    fused: list[tuple[int, float]] = []
    for document_id in candidate_ids:
        score = 0.0
        if document_id in dense_ranks:
            score += 1.0 / (rrf_k + dense_ranks[document_id])
        if document_id in sparse_ranks:
            score += 1.0 / (rrf_k + sparse_ranks[document_id])
        fused.append((document_id, score))
    fused.sort(key=lambda item: item[1], reverse=True)
    fused = fused[:candidate_k]

    candidates = []
    best_fusion = fused[0][1] if fused else 1.0
    for document_id, fusion_score in fused:
        metadata = store.metadatas[document_id]
        candidates.append(
            {
                "content": metadata["content"],
                "source": metadata.get("file") or metadata.get("source") or "未知来源",
                "chunk_id": metadata.get("chunk_id", document_id),
                "metadata": _json_safe(metadata),
                "fusion_score": fusion_score / best_fusion,
            }
        )

    reranker = load_reranker()
    if reranker and candidates:
        pairs = [(query, item["content"]) for item in candidates]
        raw_scores = np.asarray(reranker.predict(pairs)).reshape(-1)
        for item, raw_score in zip(candidates, raw_scores):
            # BGE rerankers may expose logits, so normalize them to [0, 1].
            item["score"] = 1.0 / (1.0 + math.exp(-float(raw_score)))
        candidates.sort(key=lambda item: item["score"], reverse=True)
    else:
        for item in candidates:
            item["score"] = item["fusion_score"]

    filtered = [item for item in candidates if item["score"] >= score_threshold]
    return filtered[:top_k]
