import argparse
import hashlib
import io
import os
import pickle
import re
import shutil
import sys
import time
from pathlib import Path

import faiss
import numpy as np
import tqdm
from sentence_transformers import SentenceTransformer


sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]
sys.path.append(str(SCRIPT_DIR.parent))
sys.path.append(str(PROJECT_ROOT))

try:
    from text_splitter import ChineseRecursiveTextSplitter  # noqa: E402
except ImportError:
    ChineseRecursiveTextSplitter = None
    from backend_fastapi.index_tools import split_text as _fallback_split_text

from backend_fastapi.document_blocks import parse_document, persist_blocks


def split_text(text: str, chunk_size: int = 300, overlap: int = 50) -> list[str]:
    if ChineseRecursiveTextSplitter is None:
        return _fallback_split_text(text, chunk_size, overlap)
    splitter = ChineseRecursiveTextSplitter(
        keep_separator=True,
        is_separator_regex=True,
        chunk_size=chunk_size,
        chunk_overlap=overlap,
    )
    return splitter.split_text(text)


def _content_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _section_title(chunk: str) -> str | None:
    first_line = next((line.strip() for line in chunk.splitlines() if line.strip()), "")
    if len(first_line) <= 80 and (
        first_line.startswith("#")
        or re.match(r"^第[一二三四五六七八九十百千万\d]+[章节条]", first_line)
    ):
        return first_line.lstrip("# ")
    return None


def read_all_texts(
    input_dir: str, chunk_size: int = 300, overlap: int = 50
) -> tuple[list[str], list[dict]]:
    allowed_extensions = {".txt", ".md", ".docx", ".pdf", ".pptx", ".csv"}
    files = [
        str(path)
        for path in sorted(Path(input_dir).iterdir())
        if path.is_file() and path.suffix.lower() in allowed_extensions
    ]

    documents: list[str] = []
    metadatas: list[dict] = []
    parse_errors: list[str] = []
    parsed_dir = Path(input_dir).parent / "parsed"
    for file_path in tqdm.tqdm(files, desc="处理文件"):
        try:
            document_hash, blocks = parse_document(
                Path(file_path), parsed_dir / "assets"
            )
            document_id = document_hash[:24]
            persist_blocks(parsed_dir, document_id, blocks)
        except Exception as exc:
            message = f"[文件解析失败] {file_path}: {exc}"
            parse_errors.append(message)
            print(message, file=sys.stderr)
            continue
        file_rows: list[tuple[str, dict]] = []
        for block in blocks:
            if block.block_type == "page_image" or (
                block.block_type == "image"
                and block.metadata.get("vision_status") != "completed"
            ):
                continue
            for chunk in split_text(block.content, chunk_size, overlap):
                file_rows.append(
                    (
                        chunk,
                        {
                            "file": os.path.basename(file_path),
                            "content": chunk,
                            "document_id": document_id,
                            "document_hash": document_hash,
                            "block_id": block.block_id,
                            "block_type": block.block_type,
                            "page": block.page,
                            "bbox": block.bbox,
                            "section_title": block.section_title or _section_title(chunk),
                            "content_hash": _content_hash(chunk),
                            "evidence_locator": {
                                "page": block.page,
                                "bbox": block.bbox,
                                "block_id": block.block_id,
                            },
                        },
                    )
                )
        for chunk_index, (chunk, metadata) in enumerate(file_rows):
            metadata.update(
                {
                    "document_chunk_id": chunk_index,
                    "previous_chunk_id": chunk_index - 1 if chunk_index > 0 else None,
                    "next_chunk_id": chunk_index + 1 if chunk_index + 1 < len(file_rows) else None,
                }
            )
            documents.append(chunk)
            metadatas.append(metadata)
    if parse_errors:
        raise RuntimeError("\n".join(parse_errors))
    return documents, metadatas


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_dir", required=True)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--chunk_size", type=int, default=300)
    parser.add_argument("--overlap", type=int, default=50)
    parser.add_argument("--model", default=os.getenv("EMBED_MODEL_PATH"))
    parser.add_argument("--show_samples", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    documents, metadatas = read_all_texts(
        args.input_dir, args.chunk_size, args.overlap
    )
    print(f"共读取到 {len(documents)} 个文档片段")
    if not documents:
        raise SystemExit("没有可用的文档片段，向量库未生成")

    if args.show_samples:
        for index, metadata in enumerate(metadatas[:10], 1):
            print(f"\n片段 {index}（{metadata['file']}）：\n{metadata['content']}")

    default_model = (
        PROJECT_ROOT / "knowledge_base" / "samples" / "vector_store" / "bge-large-zh"
    )
    model_path = args.model or str(default_model)
    model = SentenceTransformer(model_path)
    embeddings = model.encode(
        documents,
        show_progress_bar=True,
        batch_size=32,
        normalize_embeddings=True,
    ).astype("float32")

    # 归一化向量使用内积等价于余弦相似度。
    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(np.ascontiguousarray(embeddings))
    index_path = output_dir / "index.faiss"
    metadata_path = output_dir / "index.pkl"
    temp_index = output_dir / "index.faiss.tmp"
    temp_metadata = output_dir / "index.pkl.tmp"
    timestamp = time.strftime("%Y%m%d%H%M%S")
    if index_path.exists():
        shutil.copy2(index_path, output_dir / f"index.faiss.bak-{timestamp}")
    if metadata_path.exists():
        shutil.copy2(metadata_path, output_dir / f"index.pkl.bak-{timestamp}")
    faiss.write_index(index, str(temp_index))
    with temp_metadata.open("wb") as file:
        pickle.dump(metadatas, file)
    os.replace(temp_index, index_path)
    os.replace(temp_metadata, metadata_path)
    print(f"向量库已保存到 {output_dir}")


if __name__ == "__main__":
    main()
