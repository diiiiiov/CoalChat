from __future__ import annotations

import hashlib
import json
import os
import pickle
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_ROOT = PROJECT_ROOT / "knowledge_base"
_locks: dict[str, threading.RLock] = {}
_locks_guard = threading.Lock()


def _lock(knowledge_base: str) -> threading.RLock:
    with _locks_guard:
        return _locks.setdefault(knowledge_base, threading.RLock())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def registry_path(knowledge_base: str) -> Path:
    return KNOWLEDGE_ROOT / knowledge_base / "document_status.json"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _read(knowledge_base: str) -> dict[str, dict[str, Any]]:
    path = registry_path(knowledge_base)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    documents = payload.get("documents", {}) if isinstance(payload, dict) else {}
    return documents if isinstance(documents, dict) else {}


def _write(knowledge_base: str, documents: dict[str, dict[str, Any]]) -> None:
    path = registry_path(knowledge_base)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    payload = {"schema_version": 1, "updated_at": _now(), "documents": documents}
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def register_upload(
    knowledge_base: str,
    filename: str,
    content_hash: str,
    size: int,
    chunk_size: int,
    chunk_overlap: int,
) -> tuple[dict[str, Any], bool]:
    with _lock(knowledge_base):
        documents = _read(knowledge_base)
        previous = documents.get(filename, {})
        changed = previous.get("content_hash") != content_hash
        if not changed:
            return previous, False
        record = {
            "document_id": content_hash[:24],
            "filename": filename,
            "content_hash": content_hash,
            "size": size,
            "version": int(previous.get("version", 0)) + 1,
            "status": "uploaded",
            "parser": Path(filename).suffix.lower().lstrip(".") or "unknown",
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "chunk_count": 0,
            "index_version": None,
            "error": None,
            "updated_at": _now(),
        }
        documents[filename] = record
        _write(knowledge_base, documents)
        return record, True


def update_status(
    knowledge_base: str,
    filenames: Iterable[str],
    status: str,
    *,
    error: str | None = None,
    index_version: str | None = None,
    chunk_counts: dict[str, int] | None = None,
    block_summaries: dict[str, dict[str, int]] | None = None,
) -> None:
    with _lock(knowledge_base):
        documents = _read(knowledge_base)
        changed = False
        for filename in filenames:
            record = documents.get(filename)
            if not record:
                continue
            record.update(
                {
                    "status": status,
                    "error": error,
                    "updated_at": _now(),
                }
            )
            if index_version is not None:
                record["index_version"] = index_version
            if chunk_counts is not None:
                record["chunk_count"] = int(chunk_counts.get(filename, 0))
            if block_summaries is not None:
                record["block_summary"] = block_summaries.get(filename, {})
            changed = True
        if changed:
            _write(knowledge_base, documents)


def list_documents(knowledge_base: str) -> list[dict[str, Any]]:
    with _lock(knowledge_base):
        documents = _read(knowledge_base)
        return sorted(documents.values(), key=lambda item: item.get("filename", ""))


def remove_document(knowledge_base: str, filename: str) -> dict[str, Any] | None:
    with _lock(knowledge_base):
        documents = _read(knowledge_base)
        removed = documents.pop(filename, None)
        if removed is not None:
            _write(knowledge_base, documents)
        return removed


def chunk_counts_from_metadata(metadata_path: Path) -> dict[str, int]:
    if not metadata_path.exists():
        return {}
    with metadata_path.open("rb") as source:
        rows = pickle.load(source)
    counts: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        filename = row.get("file") or row.get("source")
        if filename:
            counts[str(filename)] = counts.get(str(filename), 0) + 1
    return counts


def load_document_blocks(knowledge_base: str, document_id: str) -> list[dict[str, Any]]:
    path = KNOWLEDGE_ROOT / knowledge_base / "parsed" / f"{document_id}.jsonl"
    if not path.exists():
        return []
    blocks: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            blocks.append(value)
    return blocks


def document_block_summaries(knowledge_base: str) -> dict[str, dict[str, int]]:
    summaries: dict[str, dict[str, int]] = {}
    for document in list_documents(knowledge_base):
        filename = str(document.get("filename", ""))
        document_id = str(document.get("document_id", ""))
        counts: dict[str, int] = {}
        for block in load_document_blocks(knowledge_base, document_id):
            block_type = str(block.get("block_type", "unknown"))
            counts[block_type] = counts.get(block_type, 0) + 1
        summaries[filename] = counts
    return summaries
