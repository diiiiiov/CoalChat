<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/Vue.js-4FC08D?style=flat-square&logo=vue.js" alt="Vue.js">
  <img src="https://img.shields.io/badge/BGE-FAISS-534AB7?style=flat-square" alt="BGE + FAISS">
  <img src="https://img.shields.io/badge/Redis-DC382D?style=flat-square&logo=redis" alt="Redis">
  <img src="https://img.shields.io/badge/License-MIT-green?style=flat-square" alt="MIT License">
</p>

<h1 align="center">CoalChat</h1>

<p align="center"><strong>面向垂直领域的可配置 RAG 知识问答系统</strong></p>

<p align="center">
  当前以煤矿安全知识库作为参考实现；替换知识文档、系统提示词和模型 API 后，
  可扩展到制造、法律、金融等其他垂直领域。
</p>

---

## 项目概览

CoalChat 由 Vue 前端、Express NLP 服务和 FastAPI 知识服务组成。知识服务负责文档解析、向量索引、混合检索、引用证据、流式生成和文档生命周期管理。

本轮优化后的主要能力：

| 能力 | 当前实现 |
|---|---|
| 动态检索路由 | 根据精确数值、语义、关系推理、总结类问题选择不同的稠密/稀疏检索权重 |
| 混合召回 | BGE + FAISS 稠密检索、BM25 稀疏检索、加权 RRF 融合 |
| 选择性重排 | 根据问题类型与两路召回结果的一致性决定是否调用 BGE Reranker |
| 上下文查询改写 | 对包含指代或上下文依赖的多轮问题生成独立检索问题，可关闭 |
| 引用与证据回查 | 回答内使用 `[#n]`，自动清理无效引用，并支持按请求回查原始证据 |
| 文档生命周期 | 上传去重、内容哈希、版本递增、状态记录、重建、取消与删除后自动重建 |
| 结构化文档解析 | 支持 TXT、Markdown、CSV、PDF、DOCX、PPTX；保留页码、边界框、章节、表格和图片信息 |
| OCR 与可选视觉描述 | 扫描 PDF 自动 OCR；视觉模型默认关闭，只有显式配置后才会产生外部 API 调用 |
| 索引热更新 | 索引按磁盘版本加载，重建发布后无需重启 API；重建前释放模型缓存以降低 Windows 内存压力 |
| 可观测性 | 返回查询改写、召回模式、候选数量、各阶段耗时、Token 用量估算和引用覆盖率 |
| 流式输出与降级 | FastAPI SSE；Redis 不可用时退回内存；模型不可用时返回降级答案 |

## 系统架构

```text
Vue :5173
   │
   ├── Express NLP :3000
   │
   └── FastAPI Knowledge API :8000
          │
          ├── 历史压缩与独立问题改写
          ├── 查询分析：exact / semantic / relational / summary
          ├── BGE + FAISS ─┐
          ├── BM25 ────────┴─ 加权 RRF ─ 选择性 Reranker
          ├── LLM 生成与 [#n] 引用规范化
          ├── Redis / 内存：检索缓存与证据存储
          └── 文档注册表、结构化块、OCR 与图片资产
```

## 技术栈

| 分类 | 技术 |
|---|---|
| 前端 | Vue 3、Vite、Element Plus |
| NLP 服务 | Node.js、Express |
| 知识服务 | Python、FastAPI、Uvicorn |
| 向量检索 | Sentence Transformers、BGE、FAISS |
| 稀疏检索 | BM25 |
| 重排序 | BGE Reranker / CrossEncoder |
| 文档解析 | pdfplumber、pypdfium2、python-docx、python-pptx |
| OCR | RapidOCR + ONNX Runtime |
| 状态与缓存 | Redis，可自动降级为进程内内存 |

## 快速开始

### 1. 安装依赖

前端与 Express 服务：

```bash
npm install
cd backen
npm install
cd ..
```

Windows 下建议在项目根目录创建虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend_fastapi\requirements.txt
```

Linux/macOS：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r backend_fastapi/requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为项目根目录下的 `.env`，至少配置模型接口：

```env
LLM_API_URL=https://provider.example/v1/chat/completions
LLM_API_KEY=your-api-key
LLM_API_STYLE=chat
LLM_MODEL_NAME=provider-model-id
```

支持 `chat` 和 `completion` 两种接口格式。旧配置如果误将密钥放入 `LLM_API_URL`，服务会临时兼容，并在 `/health` 返回 `legacy_env_layout: true`；建议尽快迁移到标准配置。

### 3. 启动全部服务

```powershell
npm run dev:full
```

默认地址：

- 前端：<http://localhost:5173>
- Express：<http://localhost:3000>
- FastAPI：<http://localhost:8000>
- FastAPI 接口文档：<http://localhost:8000/docs>

也可以分别启动：

```powershell
npm run server
npm run server:knowledge
npm run dev
```

## 知识库与文档处理

默认知识库目录结构：

```text
knowledge_base/<knowledge_base>/
├── context/                         # 原始知识文档
├── vector_store/bge-large-zh/
│   ├── index.faiss                  # FAISS 索引
│   └── index.pkl                    # 片段元数据
├── parsed/
│   ├── <document_id>.jsonl          # 结构化文档块
│   └── assets/<document_id>/        # PDF、DOCX、PPTX 提取出的图片
└── document_status.json             # 文档版本、状态与片段统计
```

支持的上传格式：

| 格式 | 解析结果 |
|---|---|
| TXT / Markdown | 段落、标题与章节信息 |
| CSV | Markdown 表格块 |
| PDF | 文本区域、表格、页码、边界框、图片；纯扫描页进入 OCR |
| DOCX | 标题、正文、表格与内嵌图片 |
| PPTX | 幻灯片文本、表格、图片与位置坐标 |

不启用视觉模型时，未描述的图片仍会作为结构化资产保存，但不会作为无意义文本写入向量索引。扫描页的 OCR 文本会进入索引。

### 手动重建索引

通过 API 重建：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/api/knowledge/rebuild_vector `
  -ContentType 'application/json' `
  -Body '{"knowledge_base":"samples","chunk_size":300,"chunk_overlap":50}'
```

也可以直接运行构建脚本：

```powershell
.\.venv\Scripts\python.exe backen\knowledge\scripts\build_faiss.py `
  --input_dir knowledge_base\samples\context `
  --output_dir knowledge_base\samples\vector_store\bge-large-zh `
  --chunk_size 300 `
  --overlap 50
```

重建使用临时文件原子发布索引，并保留旧索引备份。API 重建前会释放已经缓存的嵌入和重排模型，避免 Windows 下主进程与构建子进程叠加占用内存。

## 检索流程

1. 根据对话历史判断是否需要将当前问题改写为独立问题。
2. 分析问题类型：
   - `exact`：条款、编号、百分比、尺寸等强精确特征，优先 BM25，不调用重排；
   - `semantic`：一般语义问题，保留稠密召回并适当偏向当前基准表现更好的稀疏召回；
   - `relational`：原因、影响、关系、流程类问题，提高稠密召回权重；
   - `summary`：总结和概述类问题，扩大语义召回作用。
3. 对 FAISS 与 BM25 候选执行加权 RRF 融合。
4. `auto` 模式下，根据问题类型和两路 Top 3 的重合度决定是否重排。
5. 按分数阈值过滤，生成带 `[#n]` 引用的回答并保存证据。

索引加载使用磁盘版本作为缓存键。重建完成后，新请求会自动加载新版本，不需要重启 FastAPI。

## API

### 问答接口

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/knowledge/chat` | 返回完整 JSON 回答、来源和追踪信息 |
| `POST` | `/api/knowledge/chat/stream` | SSE 流式返回来源、Token 和完成事件 |
| `GET` | `/api/knowledge/evidence/{request_id}/{citation_id}` | 回查指定引用对应的完整证据 |
| `GET` | `/health` | 服务、LLM 配置、检索版本和状态存储健康信息 |

问答请求示例：

```json
{
  "query": "甲烷浓度达到 1.0% 时应该怎么处理？",
  "knowledge_base_name": "samples",
  "top_k": 5,
  "score_threshold": 0.0,
  "model_name": "provider-model-id",
  "temperature": 0.2,
  "history": []
}
```

普通问答响应中的 `trace` 包含：

- 是否发生查询改写；
- 检索路由与稠密/稀疏权重；
- 各路候选数、融合候选数和是否重排；
- 索引加载、稠密检索、BM25、融合、重排、生成和总耗时；
- 模型返回的 Token 用量，或本地估算值；
- 可用来源数、已引用来源数和句子级引用覆盖率。

### 文档管理接口

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/knowledge/upload` | `multipart/form-data` 上传文档；字段名为 `file`，支持多文件 |
| `POST` | `/api/knowledge/rebuild_vector` | 重建指定知识库索引 |
| `POST` | `/api/knowledge/cancel_upload` | 取消正在运行的重建，或取消指定文件 |
| `GET` | `/api/knowledge/documents` | 获取文档版本、状态、片段数和结构化块统计 |
| `DELETE` | `/api/knowledge/documents/{filename}` | 删除文档并自动重建；不允许删除知识库最后一个文档 |
| `GET` | `/api/knowledge/documents/{filename}/blocks` | 获取结构化块，可按页码和块类型过滤 |
| `GET` | `/api/knowledge/assets/{knowledge_base}/{document_id}/{asset_name}` | 获取解析出的图片资产 |
| `GET` | `/api/knowledge/parser-capabilities` | 查看当前环境的解析、OCR 和视觉模型能力 |

同名同内容文件会返回 `unchanged`，不会重复写入；同名但内容变化时，文档版本号自动递增。

## 配置参考

### LLM 与缓存

| 变量 | 默认值 | 说明 |
|---|---:|---|
| `LLM_API_URL` | 空 | Chat/Completion API 地址 |
| `LLM_API_KEY` | 空 | 模型 API 密钥 |
| `LLM_API_STYLE` | `auto` | `auto`、`chat` 或 `completion` |
| `LLM_MODEL_NAME` | `qwen_coalchat` | 默认模型名称 |
| `LLM_TIMEOUT_SECONDS` | `60` | 请求总超时 |
| `LLM_CONNECT_TIMEOUT_SECONDS` | `10` | 连接超时 |
| `LLM_MAX_RETRIES` | `2` | 可重试错误的最大重试次数 |
| `REDIS_URL` | 空 | 为空时使用进程内内存 |
| `EVIDENCE_TTL_SECONDS` | `3600` | 引用证据保存时间 |
| `RETRIEVAL_CACHE_TTL_SECONDS` | `300` | 检索缓存保存时间 |

### 检索

| 变量 | 默认值 | 说明 |
|---|---:|---|
| `EMBED_MODEL_PATH` | samples 中的 BGE 路径 | 嵌入模型目录 |
| `RERANKER_MODEL_PATH` | `backen/knowledge/bge-reranker-base` | 重排模型目录 |
| `QUERY_REWRITE_ENABLED` | `true` | 是否启用多轮查询改写 |
| `RERANKER_POLICY` | `auto` | `auto`、`always` 或 `never` |
| `RERANKER_CANDIDATE_K` | `10` | 送入重排器的候选数 |
| `RERANKER_SKIP_TOP3_OVERLAP` | `2` | 两路 Top 3 达到此重合数时跳过自动重排 |
| `RERANKER_MAX_LENGTH` | `320` | CrossEncoder 最大输入长度 |
| `RRF_K` | `60` | RRF 平滑参数 |

### OCR 与视觉描述

| 变量 | 默认值 | 说明 |
|---|---:|---|
| `MULTIMODAL_OCR_ENABLED` | `true` | 扫描 PDF 是否启用 OCR |
| `OCR_MAX_PAGES_PER_DOCUMENT` | `200` | 单文档最大 OCR 页数 |
| `VISION_DESCRIPTION_ENABLED` | `false` | 是否调用外部视觉模型 |
| `VISION_API_URL` | 空 | OpenAI 兼容视觉模型地址 |
| `VISION_API_KEY` | 空 | 视觉模型密钥 |
| `VISION_MODEL_NAME` | 空 | 视觉模型名称 |
| `VISION_MAX_IMAGES_PER_DOCUMENT` | `20` | 单文档最大视觉描述图片数 |
| `VISION_MAX_TOKENS` | `512` | 单次视觉描述最大输出 Token |
| `VISION_TIMEOUT_SECONDS` | `60` | 视觉模型请求超时 |

> 视觉描述默认关闭。只有同时启用 `VISION_DESCRIPTION_ENABLED` 并配置 URL 和模型名称后，系统才会发送外部请求。

完整配置模板见 [`.env.example`](.env.example)。

## 测试与评测

```powershell
npm run test:backend
npm run build
npm run eval:retrieval
npm run eval:compare
npm run audit:index
```

- 后端单元测试覆盖引用清洗、模型协议、文本切分、查询改写、动态路由、重排策略和内存存储；
- `tests/mock_llm.py` 与 `tests/smoke_test.py` 用于验证普通问答、SSE、引用规范化和证据回查；
- `tests/real_api_smoke.py` 用于真实模型 API 冒烟测试；
- `tests/redis_persistence_test.py write/read` 可跨进程验证 Redis 证据持久化；
- 检索评测输出 Recall@K、MRR、nDCG、延迟和逐题结果；
- 索引审计用于发现知识库目录中未进入索引的文档。

## 300 条检索基线

`evaluation/coal_mine_qa_300.jsonl` 从 1,526 个知识片段中分层采样 300 条问题。完整结果见 `evaluation/retrieval_comparison_report.md`。

| 方法 | Recall@5 | MRR@20 | nDCG@5 | 平均延迟 |
|---|---:|---:|---:|---:|
| BGE + FAISS | 0.5033 | 0.3587 | 0.2205 | 91.53 ms |
| BM25 | 0.8433 | 0.6463 | 0.4223 | 43.26 ms |
| 等权 RRF | 0.7333 | 0.5267 | 0.3466 | 134.81 ms |
| RRF + BGE Reranker | 0.8633 | 0.6648 | 0.4363 | 5655.28 ms |

> 该基线将目标片段及同来源相邻片段视为相关结果。延迟是本地批处理摊销值，不代表生产 P95。结果说明 BM25 是较强的低延迟基线，而 Reranker 虽提高召回率，但 CPU 成本明显；因此当前实现采用动态加权和选择性重排。

重新生成评测问题会调用模型 API：

```powershell
npm run eval:generate
npm run eval:compare
```

## Docker Compose

确认模型 API 配置正确后运行：

```bash
docker compose up --build
```

Compose 默认启动 FastAPI 和 Redis，健康检查地址为 <http://localhost:8000/health>。

当前 `docker-compose.yml` 将 `knowledge_base` 以只读方式挂载，适合查询服务。如果要在容器内使用上传、删除或重建接口，需要将该卷挂载改为可写，并确保容器对目录具有写权限：

```yaml
volumes:
  - ./knowledge_base:/app/knowledge_base
```

## 常见问题

### `http://localhost:5173` 无法访问

确认 `npm run dev` 或 `npm run dev:full` 正在运行，并检查终端中 Vite 实际监听的地址。FastAPI 单独启动不会提供前端页面。

### 向量库重建失败

1. 检查 `knowledge_base/<name>/context` 中是否存在受支持的文档；
2. 检查 `EMBED_MODEL_PATH` 是否指向完整的 Sentence Transformers 模型；
3. 调用 `/api/knowledge/documents` 查看文档的 `status` 和 `error`；
4. Windows 内存紧张时关闭重复启动的 Python/FastAPI 进程，再保留一个知识服务进行重建；
5. 当前版本会在重建前释放检索模型缓存，降低 `OSError 1455` 或原生扩展访问异常的概率。

### OCR 或视觉描述没有执行

调用 `/api/knowledge/parser-capabilities` 检查能力状态。OCR 需要 RapidOCR；视觉描述还需要显式启用并配置兼容接口。普通含文本 PDF 不会重复执行整页 OCR。

## License

[MIT](LICENSE)
