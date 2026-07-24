from __future__ import annotations

import argparse
import json
import os
import pickle
import shutil
import time
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer


PROJECT_ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_ROOT = PROJECT_ROOT / "knowledge_base"


def split_text(text: str, chunk_size: int = 400, overlap: int = 80) -> list[str]:
    text = text.replace("\r\n", "\n").strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    separators = ("\n", "。", "；", "！", "？")
    while start < len(text):
        hard_end = min(start + chunk_size, len(text))
        end = hard_end
        if hard_end < len(text):
            search_from = start + int(chunk_size * 0.6)
            candidates = [text.rfind(separator, search_from, hard_end) for separator in separators]
            boundary = max(candidates)
            if boundary > start:
                end = boundary + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks


def _paths(knowledge_base: str) -> tuple[Path, Path, Path]:
    vector_dir = KNOWLEDGE_ROOT / knowledge_base / "vector_store" / "bge-large-zh"
    return vector_dir, vector_dir / "index.faiss", vector_dir / "index.pkl"


def _load_metadata(metadata_path: Path) -> list[dict]:
    with metadata_path.open("rb") as file:
        raw = pickle.load(file)
    return [item if isinstance(item, dict) else {"content": str(item)} for item in raw]


def audit(knowledge_base: str) -> dict:
    _, _, metadata_path = _paths(knowledge_base)
    metadata = _load_metadata(metadata_path)
    indexed_sources = {
        item.get("file") or item.get("source") for item in metadata if item.get("file") or item.get("source")
    }
    context_dir = KNOWLEDGE_ROOT / knowledge_base / "context"
    context_sources = {path.name for path in context_dir.iterdir() if path.is_file()}
    return {
        "knowledge_base": knowledge_base,
        "indexed_chunks": len(metadata),
        "context_files": len(context_sources),
        "indexed_files": len(indexed_sources),
        "missing_files": sorted(context_sources - indexed_sources),
    }


def add_text_file(
    knowledge_base: str,
    filename: str,
    chunk_size: int = 400,
    overlap: int = 80,
) -> dict:
    vector_dir, index_path, metadata_path = _paths(knowledge_base)
    source_path = KNOWLEDGE_ROOT / knowledge_base / "context" / filename
    if source_path.suffix.lower() not in {".txt", ".md"}:
        raise ValueError("增量工具仅允许 TXT/Markdown 文档")
    if not source_path.exists():
        raise FileNotFoundError(source_path)

    metadata = _load_metadata(metadata_path)
    if any((item.get("file") or item.get("source")) == filename for item in metadata):
        return {"status": "skipped", "reason": "already_indexed", "file": filename}

    chunks = split_text(
        source_path.read_text(encoding="utf-8", errors="ignore"),
        chunk_size,
        overlap,
    )
    if not chunks:
        raise ValueError("文档没有可索引内容")

    model_path = Path(
        os.getenv(
            "EMBED_MODEL_PATH",
            str(KNOWLEDGE_ROOT / "samples" / "vector_store" / "bge-large-zh"),
        )
    )
    model = SentenceTransformer(str(model_path))
    embeddings = model.encode(
        chunks,
        batch_size=32,
        show_progress_bar=True,
        normalize_embeddings=True,
    ).astype("float32")

    index = faiss.read_index(str(index_path))
    if index.d != embeddings.shape[1]:
        raise ValueError(f"向量维度不一致：index={index.d}, document={embeddings.shape[1]}")
    index.add(np.ascontiguousarray(embeddings))

    start_chunk_id = len(metadata)
    metadata.extend(
        {
            "file": filename,
            "content": chunk,
            "chunk_id": start_chunk_id + position,
        }
        for position, chunk in enumerate(chunks)
    )

    timestamp = time.strftime("%Y%m%d%H%M%S")
    temp_index = vector_dir / "index.faiss.tmp"
    temp_metadata = vector_dir / "index.pkl.tmp"
    backup_index = vector_dir / f"index.faiss.bak-{timestamp}"
    backup_metadata = vector_dir / f"index.pkl.bak-{timestamp}"

    faiss.write_index(index, str(temp_index))
    with temp_metadata.open("wb") as file:
        pickle.dump(metadata, file)
    # Keep recoverable snapshots before atomically replacing both active files.
    shutil.copy2(index_path, backup_index)
    shutil.copy2(metadata_path, backup_metadata)
    os.replace(temp_index, index_path)
    os.replace(temp_metadata, metadata_path)

    return {
        "status": "indexed",
        "file": filename,
        "added_chunks": len(chunks),
        "total_chunks": len(metadata),
        "backup_index": backup_index.name,
        "backup_metadata": backup_metadata.name,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    audit_parser = subparsers.add_parser("audit")
    audit_parser.add_argument("--knowledge-base", default="samples")
    add_parser = subparsers.add_parser("add-text")
    add_parser.add_argument("--knowledge-base", default="samples")
    add_parser.add_argument("--filename", required=True)
    add_parser.add_argument("--chunk-size", type=int, default=400)
    add_parser.add_argument("--overlap", type=int, default=80)
    args = parser.parse_args()

    if args.command == "audit":
        result = audit(args.knowledge_base)
    else:
        result = add_text_file(
            args.knowledge_base,
            args.filename,
            args.chunk_size,
            args.overlap,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
