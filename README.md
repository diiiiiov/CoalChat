# CoalChat

可配置的通用垂直领域 RAG 知识问答系统，以煤矿安全知识库作为参考实现。后端核心检索与问答链路不依赖具体行业：为新领域构建对应索引、配置 `SYSTEM_PROMPT` 和模型 API 后，即可复用到法律、医疗、金融、制造等知识密集型场景。当前仓库的前端默认选择 `samples` 煤矿知识库，迁移其他领域时还需将新知识库接入前端选项并完成领域提示词和检索效果验证。知识问答服务由 FastAPI 提供，包含：

- BGE + FAISS 向量召回和 BM25 稀疏召回，通过 RRF 融合候选；
- BGE Reranker 重排序和检索阈值过滤；
- 基于 `[#n]` 的行内引用、引用规范化和证据回查；
- FastAPI SSE 增量输出，前端使用 `ReadableStream` 实时消费；
- 模型 API 超时重试、请求断开取消和检索证据降级；
- Redis 证据持久化与检索缓存（不可用时自动降级到内存）；
- 无有效证据时拒答。

## 启动

安装前端与原 Express NLP 服务依赖：

```bash
npm install
cd backen && npm install
```

安装 FastAPI 知识服务依赖：

```bash
python -m pip install -r backend_fastapi/requirements.txt
```

Windows 下建议先在项目根目录创建虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend_fastapi\requirements.txt
```

配置模型服务（PowerShell 示例）：

```powershell
$env:LLM_API_URL="http://模型服务地址/v1/completions"
$env:LLM_MODEL_NAME="qwen_coalchat"
```

使用需要鉴权的 Chat Completions API 时，`.env` 应配置为：

```env
LLM_API_URL=https://服务商地址/v1/chat/completions
LLM_API_KEY=实际密钥
LLM_API_STYLE=chat
LLM_MODEL_NAME=服务商提供的模型名称
LLM_MAX_RETRIES=2
LLM_TIMEOUT_SECONDS=60

# 可选；不配置时使用内存
REDIS_URL=redis://localhost:6379/0
```

DeepSeek V4 Pro 官方配置示例：

```env
LLM_API_URL=https://api.deepseek.com/chat/completions
LLM_API_KEY=实际DeepSeek密钥
LLM_API_STYLE=chat
LLM_MODEL_NAME=deepseek-v4-pro
```

旧配置若误将密钥放入 `LLM_API_URL`，服务会临时兼容并在 `/health` 返回 `legacy_env_layout: true`；仍建议尽快按上面的格式修正。

同时启动前端、Express NLP 服务和 FastAPI 知识服务：

```bash
npm run dev:full
```

默认地址：前端 `http://localhost:5173`，Express `http://localhost:3000`，FastAPI `http://localhost:8000`。

知识问答接口：

- `POST /api/knowledge/chat`：普通 JSON 响应；
- `POST /api/knowledge/chat/stream`：SSE 流式响应；
- `GET /api/knowledge/evidence/{request_id}/{citation_id}`：引用证据回查；
- `GET /docs`：FastAPI 自动接口文档。

## 测试与评测

```powershell
npm run test:backend
npm run eval:retrieval
npm run eval:compare
npm run audit:index
```

- 单元测试覆盖引用清洗、模型协议适配、文本切分和内存降级存储；
- 检索评测输出 Recall@K、MRR、平均延迟与逐题结果；
- 索引审计用于检查知识库目录中是否存在未入库文件；
- `tests/smoke_test.py` 配合 `tests/mock_llm.py` 完成 SSE、普通问答和证据回查测试。
- `tests/real_api_smoke.py` 用于真实模型 API 的流式回答、引用及证据回查测试；运行前需启动 FastAPI。
- `tests/redis_persistence_test.py write/read` 可用两个独立进程验证 Redis 证据持久化。

### 300 条检索对比基线

`evaluation/coal_mine_qa_300.jsonl` 从当前 1,526 个知识片段中按 8 个文档来源分层抽样，使用 DeepSeek V4 Pro 生成 300 个唯一问题，每个来源 37–38 条。标签包含目标片段、同源相邻片段、来源和片段哈希。完整结果见 `evaluation/retrieval_comparison_report.md`。

| 方法 | Recall@5 | MRR@20 | nDCG@5 | 平均延迟 |
|---|---:|---:|---:|---:|
| BGE + FAISS | 0.5033 | 0.3587 | 0.2205 | 91.53 ms |
| BM25 | 0.8433 | 0.6463 | 0.4223 | 43.26 ms |
| 等权 RRF | 0.7333 | 0.5267 | 0.3466 | 134.81 ms |
| RRF + BGE Reranker | 0.8633 | 0.6648 | 0.4363 | 5655.28 ms |

这里的 Recall 将目标片段及其同源相邻片段视为相关；延迟为本机批处理吞吐量的单问题摊销值，不包含索引和模型加载，不代表线上 P95。该数据集由现有语料合成，适合工程回归和方案对比，不能替代真实用户问题的盲测。当前结果表明 BM25 是更合理的低延迟基线，等权 RRF 会受 Dense 噪声影响；Reranker 仅带来 2 个百分点的 Recall@5 收益，但 CPU 成本显著增加。

重新生成问题会调用模型 API：

```powershell
npm run eval:generate
npm run eval:compare
```

## Docker Compose

确认 `backen/.env` 已正确配置模型 API，然后运行：

```bash
docker compose up --build
```

Compose 会启动 FastAPI 和 Redis，模型文件及知识库通过只读卷挂载，服务健康检查地址为 `http://localhost:8000/health`。

## 索引备份

增量加入 TXT/Markdown 文档时可运行：

```powershell
.\.venv\Scripts\python.exe -m backend_fastapi.index_tools add-text --knowledge-base samples --filename "文件名.txt"
```

工具会先保留带时间戳的旧索引备份，再原子替换活动索引。
