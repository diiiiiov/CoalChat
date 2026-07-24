import argparse
import glob
import io
import os
import pickle
import sys
from pathlib import Path

import faiss
import numpy as np
import tqdm
from sentence_transformers import SentenceTransformer


sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]
sys.path.append(str(SCRIPT_DIR.parent))

from document_loaders import (  # noqa: E402
    FilteredCSVloader,
    RapidOCRDocLoader,
    RapidOCRPDFLoader,
    RapidOCRPPTLoader,
)
from text_splitter import ChineseRecursiveTextSplitter  # noqa: E402


def split_text(text: str, chunk_size: int = 300, overlap: int = 50) -> list[str]:
    splitter = ChineseRecursiveTextSplitter(
        keep_separator=True,
        is_separator_regex=True,
        chunk_size=chunk_size,
        chunk_overlap=overlap,
    )
    return splitter.split_text(text)


def _load_file(file_path: str) -> str:
    extension = Path(file_path).suffix.lower()
    if extension == ".txt":
        return Path(file_path).read_text(encoding="utf-8", errors="ignore")
    if extension == ".docx":
        documents = RapidOCRDocLoader(file_path=file_path).load()
        return "\n".join(document.page_content for document in documents)
    if extension == ".pdf":
        documents = RapidOCRPDFLoader(file_path=file_path).load()
        return "\n".join(document.page_content for document in documents)
    if extension == ".pptx":
        documents = RapidOCRPPTLoader(file_path=file_path).load()
        return "\n".join(document.page_content for document in documents)
    if extension == ".csv":
        try:
            documents = FilteredCSVloader(
                file_path=file_path,
                columns_to_read=["content"],
                source_column="source",
            ).load()
            return "\n".join(document.page_content for document in documents)
        except Exception:
            import pandas as pd

            return pd.read_csv(file_path, encoding="utf-8").to_string(index=False)
    return ""


def read_all_texts(
    input_dir: str, chunk_size: int = 300, overlap: int = 50
) -> tuple[list[str], list[dict]]:
    files: list[str] = []
    for extension in ("*.txt", "*.docx", "*.pdf", "*.pptx", "*.csv"):
        files.extend(glob.glob(os.path.join(input_dir, extension)))

    documents: list[str] = []
    metadatas: list[dict] = []
    for file_path in tqdm.tqdm(files, desc="处理文件"):
        try:
            text = _load_file(file_path)
        except Exception as exc:
            print(f"[文件解析失败] {file_path}: {exc}", file=sys.stderr)
            continue
        if not text.strip():
            continue
        for chunk_index, chunk in enumerate(split_text(text, chunk_size, overlap)):
            documents.append(chunk)
            metadatas.append(
                {
                    "file": os.path.basename(file_path),
                    "content": chunk,
                    "chunk_id": chunk_index,
                }
            )
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
    faiss.write_index(index, str(output_dir / "index.faiss"))
    with (output_dir / "index.pkl").open("wb") as file:
        pickle.dump(metadatas, file)
    print(f"向量库已保存到 {output_dir}")


if __name__ == "__main__":
    main()
