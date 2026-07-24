import os
import json
import argparse
import torch
from typing import List, Dict, Any
from transformers import AutoModelForSequenceClassification, AutoTokenizer


def load_reranker(model_path: str):
    """加载微调好的reranker模型和分词器"""
    try:
        # 加载时添加trust_remote_code=True，支持自定义模型
        tokenizer = AutoTokenizer.from_pretrained(
            model_path,
            trust_remote_code=True,
            encoding='utf-8'  # 明确指定编码
        )
        model = AutoModelForSequenceClassification.from_pretrained(
            model_path,
            trust_remote_code=True,
            num_labels=1  # 明确单类别输出
        )
        return model, tokenizer
    except Exception as e:
        print(f"错误：加载模型失败 - {str(e)}", file=sys.stderr)
        raise


def clean_text(text: str) -> str:
    """清理文本中的乱码和不可见字符"""
    if not text:
        return ""
    # 修复编码错误（替换无法解码的字符）
    cleaned = text.encode('utf-8', errors='replace').decode('utf-8')
    # 移除控制字符和特殊符号（保留中文、英文、数字和基本标点）
    cleaned = ''.join([c for c in cleaned if c.isprintable() or '\u4e00' <= c <= '\u9fff'])
    return cleaned.strip()


def rerank(query: str, documents: List[Dict[str, Any]], model, tokenizer, config: Dict[str, Any]):
    """使用reranker对文档进行重排序（修复编码和文本处理）"""
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)
    model.eval()

    # 清理文档内容，解决乱码问题
    cleaned_documents = []
    for doc in documents:
        cleaned_content = clean_text(doc.get("content", ""))
        cleaned_documents.append({
            **doc,
            "content": cleaned_content
        })

    # 提取文档内容（已清理）
    doc_contents = [doc.get("content", "") for doc in cleaned_documents]
    if not all(doc_contents):
        raise ValueError("文档列表中包含无内容的项（可能因清理后为空）")

    # 准备输入（带编码保护）
    inputs = []
    for doc in doc_contents:
        # 确保查询和文档内容都是UTF-8编码
        safe_query = clean_text(query)
        safe_doc = doc
        text_pair = f"{safe_query} [SEP] {safe_doc}"
        inputs.append(text_pair)

    # 批量处理
    batch_size = config.get("batch_size", 8)
    scores = []

    for i in range(0, len(inputs), batch_size):
        batch = inputs[i:i + batch_size]
        encoding = tokenizer(
            batch,
            padding=True,
            truncation=True,
            max_length=config.get("max_length", 512),
            return_tensors="pt"
        )
        encoding = {k: v.to(device) for k, v in encoding.items()}

        with torch.no_grad():
            outputs = model(** encoding)
            logits = outputs.logits  # 单类别输出：shape为 [batch_size, 1]

            # 适配单类别输出
            batch_scores = torch.sigmoid(logits).squeeze(1).cpu().numpy()  # 转为 [batch_size]
            scores.extend(batch_scores.tolist())

    # 结合原始分数和reranker分数
    if "original_score_weight" in config and "reranker_weight" in config:
        final_scores = []
        for i, doc in enumerate(cleaned_documents):
            original_score = doc.get("score", 0.0)
            reranker_score = scores[i]
            final_score = (config["original_score_weight"] * original_score +
                           config["reranker_weight"] * reranker_score)
            final_scores.append(final_score)
    else:
        final_scores = scores

    # 排序并返回结果
    sorted_docs = sorted(
        [
            {
                "content": doc["content"],
                "score": final_scores[i],
                "original_score": doc.get("score", 0.0),
                "reranker_score": scores[i]
            } 
            for i, doc in enumerate(cleaned_documents)
        ],
        key=lambda x: x["score"],
        reverse=True
    )

    return sorted_docs


def main():
    import sys
    # 设置标准输出编码为UTF-8（关键修复）
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

    parser = argparse.ArgumentParser(description='使用微调的reranker模型对检索结果进行重排序')
    parser.add_argument('--query', type=str, help='用户查询')
    parser.add_argument('--query_file', type=str, help='存储查询的文件路径')
    parser.add_argument('--documents', type=str, required=True, help='包含文档的JSON文件路径')
    parser.add_argument('--model_path', type=str, required=True, help='微调的reranker模型路径')
    parser.add_argument('--config', type=str, required=True, help='配置文件路径')
    parser.add_argument('--top_k', type=int, default=3, help='返回的文档数量')

    args = parser.parse_args()

    # 读取查询（带编码保护）
    if args.query:
        query = clean_text(args.query)
    elif args.query_file:
        try:
            with open(args.query_file, 'r', encoding='utf-8') as f:  # 明确指定UTF-8读取
                query = clean_text(f.read().strip())
        except Exception as e:
            print(f"错误：读取查询文件失败 - {str(e)}", file=sys.stderr)
            return
    else:
        print("错误：必须提供--query或--query_file参数", file=sys.stderr)
        return

    # 读取文档（带编码保护）
    try:
        with open(args.documents, 'r', encoding='utf-8') as f:  # 明确指定UTF-8读取
            documents = json.load(f)
            # 确保文档是列表格式
            if not isinstance(documents, list):
                raise ValueError("文档必须是列表格式")
            # 清理每个文档的内容
            documents = [
                {
                    **doc,
                    "content": clean_text(doc.get("content", ""))
                } 
                for doc in documents
            ]
    except Exception as e:
        print(f"错误：读取文档文件失败 - {str(e)}", file=sys.stderr)
        return

    # 检查文档有效性
    if not documents:
        print("错误：文档列表为空", file=sys.stderr)
        return

    # 读取配置
    try:
        with open(args.config, 'r', encoding='utf-8') as f:  # 明确指定UTF-8读取
            config = json.load(f)
    except Exception as e:
        print(f"错误：读取配置文件失败 - {str(e)}", file=sys.stderr)
        return

    # 加载模型
    try:
        model, tokenizer = load_reranker(args.model_path)
    except Exception as e:
        print(f"错误：加载模型失败 - {str(e)}", file=sys.stderr)
        return

    # 执行重排序
    try:
        reranked_docs = rerank(query, documents, model, tokenizer, config)
    except Exception as e:
        print(f"错误：重排序过程失败 - {str(e)}", file=sys.stderr)
        return

    # 返回top_k结果
    top_docs = reranked_docs[:args.top_k]

    # 输出结果（确保JSON序列化时保留中文）
    print(json.dumps(top_docs, ensure_ascii=False, indent=2))  # ensure_ascii=False是关键


if __name__ == "__main__":
    main()


# import os
# import json
# import argparse
# import numpy as np
# from typing import List, Dict, Any
# from transformers import AutoModelForSequenceClassification, AutoTokenizer
# import torch


# def load_reranker(model_path: str):
#     """加载微调好的reranker模型和分词器"""
#     try:
#         tokenizer = AutoTokenizer.from_pretrained(model_path)
#         model = AutoModelForSequenceClassification.from_pretrained(model_path)
#         return model, tokenizer
#     except Exception as e:
#         print(f"错误：加载模型失败 - {str(e)}")
#         raise


# def rerank(query: str, documents: List[Dict[str, Any]], model, tokenizer, config: Dict[str, Any]):
#     """使用reranker对文档进行重排序"""
#     device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
#     model = model.to(device)
#     model.eval()

#     # 提取文档内容
#     doc_contents = [doc.get("content", "") for doc in documents]
#     if not all(doc_contents):
#         raise ValueError("文档列表中包含无内容的项")

#     # 准备输入
#     inputs = []
#     for doc in doc_contents:
#         text_pair = f"{query} [SEP] {doc}"  # 保持原格式
#         inputs.append(text_pair)

#     # 批量处理
#     batch_size = config.get("batch_size", 8)
#     scores = []

#     for i in range(0, len(inputs), batch_size):
#         batch = inputs[i:i + batch_size]
#         encoding = tokenizer(batch, padding=True, truncation=True,
#                              max_length=config.get("max_length", 512), return_tensors="pt")
#         encoding = {k: v.to(device) for k, v in encoding.items()}

#         with torch.no_grad():
#             outputs = model(**encoding)
#             logits = outputs.logits  # 单类别输出：shape为 [batch_size, 1]

#             # 关键修改：适配单类别输出
#             batch_scores = torch.sigmoid(logits).squeeze(1).cpu().numpy()  # 转为 [batch_size]
#             scores.extend(batch_scores.tolist())

#     # 结合原始分数和reranker分数（保持原逻辑）
#     if "original_score_weight" in config and "reranker_weight" in config:
#         final_scores = []
#         for i, doc in enumerate(documents):
#             original_score = doc.get("score", 0.0)
#             reranker_score = scores[i]
#             final_score = (config["original_score_weight"] * original_score +
#                            config["reranker_weight"] * reranker_score)
#             final_scores.append(final_score)
#     else:
#         final_scores = scores

#     # 排序并返回结果
#     sorted_docs = sorted(
#         [{"content": doc["content"], "score": final_scores[i], "original_score": doc.get("score", 0.0),
#           "reranker_score": scores[i]} for i, doc in enumerate(documents)],
#         key=lambda x: x["score"],
#         reverse=True
#     )

#     return sorted_docs
