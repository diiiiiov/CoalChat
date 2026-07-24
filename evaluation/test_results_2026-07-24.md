# CoalChat 测试与检索对比实验报告

## 1. 测试概况

| 项目 | 结果 |
|---|---|
| 测试日期 | 2026-07-24 |
| 知识库片段数 | 1,526 |
| 评测问题数 | 300 |
| 覆盖文档来源 | 8 个，每个来源 37–38 条 |
| 评测模型 | DeepSeek V4 Pro（问题生成） |
| 向量模型 | BGE-large-zh |
| 重排序模型 | BGE Reranker Base |
| 检索候选数 | 20 |

评测问题从知识库片段中分层抽样后由模型生成，每条记录保存目标片段、同源相邻片段、来源和片段哈希。该数据集用于检索工程回归，不等同于真实用户盲测。

## 2. 评测集校验

- 问题总数：300
- 唯一问题数：300
- 唯一 ID 数：300
- 目标片段哈希匹配数：300/300
- 不符合长度约束的问题：0
- 包含“根据材料/上述/本文”等提示泄漏的问题：0
- 问题长度范围：13–55 字

## 3. 检索方案对比

Recall 将目标片段及其同源相邻片段视为相关片段。延迟是本机 CPU 批处理吞吐量的单问题摊销值，不包含索引和模型加载，也不代表线上 P95。

| 方法 | Recall@1 | Recall@3 | Recall@5 | MRR@20 | nDCG@5 | 精确目标 Recall@5 | 平均延迟 |
|---|---:|---:|---:|---:|---:|---:|---:|
| BGE + FAISS Dense | 0.2367 | 0.4000 | 0.5033 | 0.3587 | 0.2205 | 0.3700 | 91.53 ms |
| BM25 Sparse | 0.5000 | 0.7300 | 0.8433 | 0.6463 | 0.4223 | 0.7967 | 43.26 ms |
| 等权 RRF | 0.3667 | 0.6100 | 0.7333 | 0.5267 | 0.3466 | 0.6400 | 134.81 ms |
| RRF + BGE Reranker | 0.5167 | 0.7667 | 0.8633 | 0.6648 | 0.4363 | 0.8333 | 5655.28 ms |

### 结果分析

1. 煤矿安全文档包含大量专业术语、编号和数值，BM25 在本评测集上明显优于单独 Dense 检索。
2. 当前等权 RRF 受到 Dense 噪声影响，Recall@5 低于 BM25，说明融合权重仍需通过验证集调优。
3. Reranker 将 Recall@5 从 0.7333 提升到 0.8633，但 CPU 推理成本较高，主要延迟来自对每个问题的 20 个候选片段进行 Cross-Encoder 打分。
4. 当前环境为 CPU-only PyTorch，Reranker 平均额外耗时约 5.5 秒/问题；该数据不能直接作为线上 P95 延迟。

## 4. 功能与工程测试

| 测试项 | 命令或方式 | 结果 |
|---|---|---|
| Python 单元测试 | `npm run test:backend` | 5 passed |
| 前端生产构建 | `npm run build` | 通过 |
| 引用清洗与规范化 | 单元测试 | 通过 |
| 模型协议适配 | 单元测试 | 通过 |
| 文本切分 | 单元测试 | 通过 |
| 内存存储降级 | 单元测试 | 通过 |
| SSE 流式问答 | 真实 API Smoke Test | 通过 |
| 引用证据回查 | 真实 API Smoke Test | 通过 |
| Redis 跨进程持久化 | Redis persistence test | 通过 |
| 索引审计 | `npm run audit:index` | 8/8 个来源已入库 |

真实 API 流式测试返回 50 个 token 事件，首 token 约 21.3 秒，总耗时约 21.8 秒，返回 3 个证据来源，引用编号可完成回查。

## 5. 复现实验

```powershell
# 重新生成约 300 条问题，需要调用模型 API
npm run eval:generate

# 运行 Dense、BM25、RRF、RRF + Reranker 四组对比
npm run eval:compare

# 运行单元测试与前端构建
npm run test:backend
npm run build
```

详细逐题结果见：

- `evaluation/coal_mine_qa_300.jsonl`
- `evaluation/retrieval_comparison_report.json`
- `evaluation/retrieval_comparison_report.md`

