import argparse
import os
import sys
import json
import requests
from sentence_transformers import SentenceTransformer, util
from rank_bm25 import BM25Okapi
from transformers import AutoTokenizer
from dotenv import load_dotenv

# 加载环境变量（优先使用后端传递的环境变量）
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../../.env'))

# 设置标准输出编码为UTF-8
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# 从环境变量读取后端配置（与modelConfig.js完全对齐）
LLM_API_URL = os.environ.get("LLM_API_URL")  # 对应后端apiUrl
LLM_MODEL_NAME = os.environ.get("LLM_MODEL_NAME")  # 对应后端modelParams.model
EMBED_MODEL_PATH = os.environ.get("EMBED_MODEL_PATH")  # 嵌入模型路径
API_KEY = os.environ.get("API_KEY", "")  # 可选API密钥

# 校验必要配置
if not all([LLM_API_URL, LLM_MODEL_NAME, EMBED_MODEL_PATH]):
    error_output = {
        "success": False,
        "error": "模型配置不完整，请检查环境变量：LLM_API_URL/LLM_MODEL_NAME/EMBED_MODEL_PATH"
    }
    print(json.dumps(error_output, ensure_ascii=False), file=sys.stderr)
    sys.exit(1)

# 模型路径配置（与后端保持一致）
MODEL_PATH = {
    "embed_model": {"bge-large-zh": EMBED_MODEL_PATH}
}
EMBEDDING_MODEL = "bge-large-zh"  # 与后端检索用嵌入模型一致

# 替换 rewrite_query.py 中的相关函数
def calculate_bm25_model(curr_ctx):
    """无需本地LLM模型，使用简单分词器替代"""
    if isinstance(curr_ctx, str):
        curr_ctx = [curr_ctx]
    # 使用空格分词（简单替代，也可使用 jieba 等中文分词库）
    tokenized_context = [doc.split() for doc in curr_ctx]
    return BM25Okapi(tokenized_context)

def calculate_bm25_score(bm25, response):
    """使用相同的简单分词方式"""
    tokenized_response = response.split()  # 空格分词
    scores = bm25.get_scores(tokenized_response)
    if not scores or all(s == 0 for s in scores):
        return 0.0
    return sum(scores) / len(scores)
# def calculate_bm25_model(curr_ctx):
#     """初始化BM25模型（基于后端配置的LLM分词器）"""
#     try:
#         tokenizer = AutoTokenizer.from_pretrained(
#             MODEL_PATH["llm_model"][LLM_MODEL_NAME],
#             use_fast=False,
#             trust_remote_code=True
#         )
#     except Exception as e:
#         error_output = {
#             "success": False,
#             "error": f"加载分词器失败 - {str(e)}"
#         }
#         print(json.dumps(error_output, ensure_ascii=False), file=sys.stderr)
#         sys.exit(1)

#     if isinstance(curr_ctx, str):
#         curr_ctx = [curr_ctx]
#     tokenized_context = [tokenizer.tokenize(doc) for doc in curr_ctx]
#     return BM25Okapi(tokenized_context)


# def calculate_bm25_score(bm25, response):
#     """计算BM25分数"""
#     tokenizer = AutoTokenizer.from_pretrained(
#         MODEL_PATH["llm_model"][LLM_MODEL_NAME],
#         use_fast=False,
#         trust_remote_code=True
#     )
#     tokenized_response = tokenizer.tokenize(response)
#     scores = bm25.get_scores(tokenized_response)
#     if not scores or all(s == 0 for s in scores):
#         return 0.0
#     return sum(scores) / len(scores)


def calculate_embedding_scores(model, curr_ctx, responses):
    """计算嵌入向量相似度分数"""
    embeddings = model.encode([curr_ctx] + responses, normalize_embeddings=True)
    p_embeddings = embeddings[0]
    q_embeddings = embeddings[1:]
    scores = (q_embeddings @ p_embeddings.T).tolist()
    return scores


class RewriteQuestion:
    def __init__(self, history, query, max_retries=2):
        # 打印配置信息（用于调试）
        print(f"[配置信息] LLM API: {LLM_API_URL}", file=sys.stderr)
        print(f"[配置信息] 模型名称: {LLM_MODEL_NAME}", file=sys.stderr)
        print(f"[配置信息] 嵌入模型路径: {EMBED_MODEL_PATH}", file=sys.stderr)

        self.instruction = '''
        给定问题及历史对话，遵循以下准则改写查询：
        1. 去语境化：消除歧义、补充缺失信息，保持原意且不重复历史问题；
        2. 区分话题：新话题保留原意，当前话题按准则1改写；
        3. 保留专有名词；
        4. 输出单个以问号结尾的问题。
        '''
        # 构造符合completions接口的prompt
        self.prompt = f"{self.instruction}\n历史对话: {history}\n原始问题: {query}\n重写问题: "
        self.history = history
        self.query = query
        self.max_retries = max_retries

        # 初始化BM25模型
        if isinstance(history, str):
            history = [history]
        self.bm25 = calculate_bm25_model(history)

        # 加载嵌入模型
        try:
            self.model = SentenceTransformer(MODEL_PATH["embed_model"][EMBEDDING_MODEL])
        except Exception as e:
            error_output = {
                "success": False,
                "error": f"加载嵌入模型失败 - {str(e)}"
            }
            print(json.dumps(error_output, ensure_ascii=False), file=sys.stderr)
            sys.exit(1)

    def generate_once(self):
        """调用后端配置的大模型API生成改写结果"""
        try:
            # 构建请求头（含可选API密钥）
            headers = {"Content-Type": "application/json"}
            if API_KEY:
                headers["Authorization"] = f"Bearer {API_KEY}"

            # 发送请求（适配completions接口格式）
            response = requests.post(
                LLM_API_URL,
                headers=headers,
                json={
                    "model": LLM_MODEL_NAME,
                    "prompt": self.prompt,
                    "temperature": 0.7,
                    "max_tokens": 2048,
                    "stop": ["\n"]  # 遇到换行停止生成
                },
                timeout=30  # 设置超时时间
            )
            response.raise_for_status()  # 抛出HTTP错误

            # 解析completions格式响应
            return response.json()["choices"][0]["text"].strip()
        except Exception as e:
            print(f"[生成错误] {str(e)}", file=sys.stderr)
            return None

    def forward(self):
        """生成并选择最佳改写结果"""
        rewritten_questions = []
        for _ in range(self.max_retries):
            result = self.generate_once()
            if result:
                rewritten_questions.append(result)

        # 过滤无效结果（必须以问号结尾）
        rewritten_questions = [
            rq for rq in rewritten_questions 
            if rq and rq.endswith("?")
        ]

        # 无有效结果时返回原始查询
        if not rewritten_questions:
            print("[警告] 未生成有效改写结果，返回原始查询", file=sys.stderr)
            return self.query

        # 计算综合评分并选择最佳结果
        try:
            bm25_scores = [calculate_bm25_score(self.bm25, rq) for rq in rewritten_questions]
            dense_scores = calculate_embedding_scores(self.model, self.history, rewritten_questions)
            combined_scores = [0.5 * bm25 + 1 * dense for bm25, dense in zip(bm25_scores, dense_scores)]
            return rewritten_questions[combined_scores.index(max(combined_scores))]
        except Exception as e:
            print(f"[评分错误] {str(e)}，返回第一个候选结果", file=sys.stderr)
            return rewritten_questions[0]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", required=True, help="历史对话文本")
    parser.add_argument("--query", required=True, help="原始查询文本")
    parser.add_argument("--output", required=True, help="改写结果输出文件路径")
    args = parser.parse_args()

    try:
        rewrite = RewriteQuestion(history=args.history, query=args.query)
        result = rewrite.forward()

        output = {
            "success": True,
            "rewritten_query": result,
            "original_query": args.query,
            "model_used": LLM_MODEL_NAME
        }
        # 写入输出文件
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False)

    except Exception as e:
        error_output = {
            "success": False,
            "error": str(e),
            "original_query": args.query
        }
        print(json.dumps(error_output, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

# import argparse
# import os
# import sys
# import json
# import requests
# from sentence_transformers import SentenceTransformer, util
# from rank_bm25 import BM25Okapi
# from transformers import AutoTokenizer
# from dotenv import load_dotenv
# import os
# # 加载项目根目录的 .env 文件（根据实际路径调整）
# load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../../.env'))

# # 设置标准输出编码为UTF-8
# sys.stdout.reconfigure(encoding='utf-8')
# sys.stderr.reconfigure(encoding='utf-8')

# # 配置模型路径（使用环境变量或相对路径）
# MODEL_PATH = {
#     "llm_model": {"deepseek-chat": os.environ.get(
#         "LLM_MODEL_PATH",
#         os.path.join(os.getcwd(), "knowledge_base", "deepseek-llm-7b-chat")
#     )},
#     "embed_model": {"bge-large-zh": os.environ.get(
#         "EMBED_MODEL_PATH",
#         os.path.join(os.getcwd(), "knowledge_base", "samples", "vector_store", "bge-large-zh")
#     )}
# }
# LLM_MODELS = ["deepseek-chat"]
# EMBEDDING_MODEL = "bge-large-zh"

# # 从环境变量获取 API 密钥
# OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
# DEEPSEEK_API_BASE = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com")

# # 检查 API 密钥是否存在
# if not OPENAI_API_KEY:
#     error_output = {
#         "success": False,
#         "error": "未设置 OPENAI_API_KEY 环境变量"
#     }
#     print(json.dumps(error_output, ensure_ascii=False), file=sys.stderr)
#     sys.exit(1)


# def calculate_bm25_model(curr_ctx):
#     tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH["llm_model"][LLM_MODELS[0]], use_fast=False,
#                                               trust_remote_code=True)
#     if isinstance(curr_ctx, str):
#         curr_ctx = [curr_ctx]
#     tokenized_context = [tokenizer.tokenize(doc) for doc in curr_ctx]
#     return BM25Okapi(tokenized_context)


# def calculate_bm25_score(bm25, response):
#     tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH["llm_model"][LLM_MODELS[0]], use_fast=False,
#                                               trust_remote_code=True)
#     tokenized_response = tokenizer.tokenize(response)
#     scores = bm25.get_scores(tokenized_response)
#     if not scores or all(s == 0 for s in scores):
#         return 0.0
#     return sum(scores) / len(scores)


# def calculate_embedding_scores(model, curr_ctx, responses):
#     embeddings = model.encode([curr_ctx] + responses, normalize_embeddings=True)
#     p_embeddings = embeddings[0]
#     q_embeddings = embeddings[1:]
#     scores = (q_embeddings @ p_embeddings.T).tolist()
#     return scores


# class RewriteQuestion:
#     def __init__(self, history, query, max_retries=2):
#         self.instruction = '''
#         给定问题及历史对话，遵循以下准则改写查询：
#         1. 去语境化：消除歧义、补充缺失信息，保持原意且不重复历史问题；
#         2. 区分话题：新话题保留原意，当前话题按准则1改写；
#         3. 保留专有名词；
#         4. 输出单个以问号结尾的问题。
#         '''
#         self.prompt = f"{self.instruction}\n历史对话: {history}\n原始问题: {query}\n重写问题: "
#         self.messages = [
#             {"role": "system", "content": "你是优秀的查询改写器。"},
#             {"role": "user", "content": self.prompt}
#         ]
#         self.history = history
#         self.query = query
#         self.max_retries = max_retries

#         if isinstance(history, str):
#             history = [history]
#         self.bm25 = calculate_bm25_model(history)

#         try:
#             self.model = SentenceTransformer(MODEL_PATH["embed_model"][EMBEDDING_MODEL])
#         except Exception as e:
#             error_output = {
#                 "success": False,
#                 "error": f"加载嵌入模型失败 - {str(e)}"
#             }
#             print(json.dumps(error_output, ensure_ascii=False), file=sys.stderr)
#             sys.exit(1)

#     def generate_once(self):
#         try:
#             response = requests.post(
#                 f"{DEEPSEEK_API_BASE}/v1/chat/completions",
#                 headers={
#                     "Content-Type": "application/json",
#                     "Authorization": f"Bearer {OPENAI_API_KEY}"
#                 },
#                 json={
#                     "model": "deepseek-chat",
#                     "messages": self.messages,
#                     "temperature": 0.7,
#                     "max_tokens": 2048
#                 }
#             )
#             response.raise_for_status()
#             return response.json()["choices"][0]["message"]["content"].strip()
#         except Exception as e:
#             print(f"错误：生成改写失败 - {str(e)}", file=sys.stderr)
#             return None

#     def forward(self):
#         rewritten_questions = []
#         for _ in range(self.max_retries):
#             result = self.generate_once()
#             if result:
#                 rewritten_questions.append(result)

#         rewritten_questions = [rq for rq in rewritten_questions if rq and rq.endswith("?")]

#         if not rewritten_questions:
#             print("警告：未能生成有效的查询改写，返回原始查询", file=sys.stderr)
#             return self.query

#         try:
#             bm25_scores = [calculate_bm25_score(self.bm25, rq) for rq in rewritten_questions]
#             dense_scores = calculate_embedding_scores(self.model, self.history, rewritten_questions)
#             combined_scores = [0.5 * bm25 + 1 * dense for bm25, dense in zip(bm25_scores, dense_scores)]
#             return rewritten_questions[combined_scores.index(max(combined_scores))]
#         except Exception as e:
#             print(f"错误：计算最佳改写失败 - {str(e)}，返回第一个候选", file=sys.stderr)
#             return rewritten_questions[0]


# if __name__ == "__main__":
#     parser = argparse.ArgumentParser()
#     parser.add_argument("--history", required=True, help="历史对话文本")
#     parser.add_argument("--query", required=True, help="原始查询文本")
#     args = parser.parse_args()

#     try:
#         rewrite = RewriteQuestion(history=args.history, query=args.query)
#         result = rewrite.forward()

#         output = {
#             "success": True,
#             "rewritten_query": result,
#             "original_query": args.query
#         }
#         print(json.dumps(output, ensure_ascii=False))

#     except Exception as e:
#         error_output = {
#             "success": False,
#             "error": str(e),
#             "original_query": args.query
#         }
#         print(json.dumps(error_output, ensure_ascii=False), file=sys.stderr)
#         sys.exit(1)
