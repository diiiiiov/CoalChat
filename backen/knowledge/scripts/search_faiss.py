import os
import sys
import argparse
import pickle
import json
import faiss
from sentence_transformers import SentenceTransformer

import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--query', required=False, type=str, help='检索问题')
    parser.add_argument('--query_file', type=str, help='包含检索问题的文本文件')
    parser.add_argument('--index', required=True, type=str, help='faiss 索引文件路径')
    parser.add_argument('--meta', required=True, type=str, help='元数据 pkl 路径')
    parser.add_argument('--model', required=True, type=str, help='embedding 模型路径')
    parser.add_argument('--top_k', type=int, default=3, help='返回top_k条')
    args = parser.parse_args()

    if args.query_file:
        with open(args.query_file, 'r', encoding='utf-8') as f:
            query = f.read()
    else:
        query = args.query

    # 加载模型
    model = SentenceTransformer(args.model)
    # 加载 faiss 索引
    index = faiss.read_index(args.index)
    # 加载元数据
    with open(args.meta, 'rb') as f:
        metadatas = pickle.load(f)

    # 编码 query
    q_emb = model.encode([query], normalize_embeddings=True)
    # 检索
    D, I = index.search(q_emb, args.top_k)
    results = []
    for idx, score in zip(I[0], D[0]):
        if idx < len(metadatas):
            meta = metadatas[idx]
            if isinstance(meta, dict):
                content = meta.get('content') or meta.get('text') or meta.get('file') or str(meta)
            else:
                content = str(meta)
            results.append({
                'content': content,
                'score': float(score),
                'meta': meta
            })
    print(json.dumps(results, ensure_ascii=False))

if __name__ == '__main__':
    main() 