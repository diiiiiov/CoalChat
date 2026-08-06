import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = "D:/coalchat/outputs/coalchat_question_bank";

const groups = [
  ["第一层", "项目概览", String.raw`
请用一分钟介绍 CoalChat 项目。
项目主要解决什么业务问题？
为什么选择煤矿安全作为落地场景？
系统的主要用户是谁？
项目有哪些核心功能？
相比直接调用大模型，这个项目增加了什么能力？
什么是 RAG？它在本项目中处于什么位置？
系统从用户提问到返回答案的完整流程是什么？
项目使用了哪些主要技术栈？
你在项目中主要负责哪些模块？
项目目前支持哪些问答模式？
这个项目中最有价值的技术工作是什么？`],
  ["第二层", "知识库与数据处理", String.raw`
知识库中的数据来自哪里？
当前知识库包含多少文档和多少片段？
文档是如何解析和清洗的？
为什么需要将长文档切分成片段？
当前 chunk_size 和 chunk_overlap 分别是多少？
为什么要设置片段重叠？
片段太长或太短分别会产生什么问题？
如何确定最合适的切片大小？
如何保存片段的来源、编号等元数据？
新增文档以后，索引如何更新？
如何确认知识库文件都已经进入索引？
PDF、Word、TXT 文档的处理方式有什么差异？
表格、条款编号和跨页内容应当怎样切分？
文档更新后，如何避免检索缓存返回旧结果？`],
  ["第三层", "Embedding 与单路检索", String.raw`
Embedding 模型的作用是什么？
为什么选择 BGE-large-zh？
文档向量和问题向量是怎样计算的？
为什么需要对向量进行归一化？
FAISS 在项目中承担什么职责？
FAISS 返回的分数表示什么？
BM25 的基本原理是什么？
BM25 为什么适合专业规范文档？
Dense 检索和 Sparse 检索的主要区别是什么？
哪类问题更适合向量检索？
哪类问题更适合 BM25？
只使用向量检索可能出现哪些问题？
举一个本项目中向量检索 Recall@5 未命中、BM25 命中的真实例子。
如果用户使用同义词或口语化表达，BM25 为什么可能失效？
专业术语、数字、年份和条款编号为什么容易成为向量检索的弱点？`],
  ["第四层", "混合检索与 Reranker", String.raw`
为什么需要混合检索？
RRF 的基本计算公式是什么？
为什么使用排名融合，而不是直接融合 Dense 和 BM25 的原始分数？
RRF 中的常数 k=60 有什么作用？
Dense 和 BM25 的候选集合是如何合并的？
当前两条检索通道的权重是否相同？
等权融合有什么潜在问题？
为什么本项目等权 RRF 的 Recall@5 反而低于 BM25？
如何为 Dense 和 Sparse 学习更加合理的融合权重？
BGE Reranker 和 Embedding 模型有什么区别？
为什么 Cross-Encoder 通常比双塔向量检索更准确？
为什么不能直接让 Reranker 对全部 1,526 个片段打分？
Reranker 的候选数量如何选择？
Reranker 分数为什么要经过 Sigmoid 归一化？
score_threshold 在检索流程中有什么作用？
请完整介绍四组消融实验的数据。
Recall@5 从 0.7333 提升到 0.8633 意味着什么？
最终方案只比 BM25 高 2 个百分点，是否值得使用？
如果线上响应时间要求在一秒以内，你会选择哪种检索方案？
如何设计动态路由，让简单问题跳过 Reranker？
是否可以用 Reranker 蒸馏或训练轻量化模型？`],
  ["第五层", "评测集与指标", String.raw`
300 题评测集是如何构建的？
为什么要从不同文档来源进行分层抽样？
每个文档来源抽取了多少题？
为什么由目标片段反向生成问题？
使用大模型生成评测问题会带来哪些偏差？
为什么这套评测集不能等同于真实用户盲测？
评测集的人工标注成本是多少？
如何检测重复问题？
如何避免问题中出现“根据上述材料”等信息泄漏？
为什么要保存目标片段的哈希？
为什么将目标片段的相邻片段也视为相关片段？
这种相关性定义可能带来什么指标偏差？
Recall@1、Recall@3、Recall@5 分别表示什么？
MRR@20 衡量的是什么？
nDCG@5 与 Recall@5 有什么不同？
“精确目标 Recall@5”和普通 Recall@5 有什么区别？
为什么检索评测不能只看 Recall@5？
当前 300 题是否包含不可回答问题？
如何构建一套更接近真实线上分布的评测集？
如何避免用测试集反复调参造成过拟合？
应当怎样划分训练集、验证集和测试集？
延迟数据为什么不能直接当作线上 P95？
如何评估生成答案的正确性、完整性和引用忠实度？`],
  ["第六层", "生成、引用与拒答", String.raw`
检索结果是怎样组织进 Prompt 的？
为什么要求模型只能依据证据回答？
[#n] 引用协议是如何设计的？
引用编号和检索片段之间如何建立映射？
模型生成不存在的 [#99] 时，系统如何处理？
[1]、[＃1] 等不规范格式如何统一？
用户点击引用以后，系统如何回查原始证据？
为什么引用回查需要同时携带 request_id 和 citation_id？
引用证据保存在哪里？有效期是多久？
Redis 不可用时如何降级？
当前引用协议能否保证引用内容一定支持生成结论？
“引用编号合法”和“引用语义正确”有什么区别？
如何检查每一个事实性陈述都有引用？
如何使用 NLI 或大模型裁判验证引用忠实度？
如果一段回答包含多个事实，应当如何分配引用？
没有检索到文档时，系统为什么必须拒答？
拒答阈值过高造成误判怎么办？
如何同时控制错误回答率和错误拒答率？
什么是双阈值或灰区机制？
拒答以后怎样给用户提供恢复路径？
如何区分“知识库没有答案”和“模型服务发生故障”？
如果检索到了错误证据，但模型严格依据它回答，系统是否仍然算正确？
如何防御 Prompt Injection，例如文档中包含“忽略系统提示”？
如果模型输出没有任何引用，后端应当怎样处理？
为什么引用校验最好在服务端完成，而不是只依赖前端？`],
  ["第七层", "Node、Python 与前端协作", String.raw`
为什么项目同时使用 Node.js 和 Python？
Express 服务负责哪些功能？
FastAPI 服务负责哪些功能？
Vue 前端如何选择调用 Express 或 FastAPI？
当前是 Express 调用 Python，还是前端分别调用两个服务？
为什么不直接把全部后端功能都迁移到 Python？
为什么不在 Node 中直接运行 FAISS 和 BGE？
三个服务分别监听哪些端口？
SSE 流式问答的完整通信过程是什么？
SSE 与 WebSocket 相比有什么优缺点？
前端如何解析 sources、token、done 和 error 事件？
普通 JSON 问答和 SSE 流式问答分别适用于什么场景？
用户取消请求以后，后端如何停止无效生成？
如果 FastAPI 服务宕机，会不会影响原有 NLP 功能？
如何为 Node 和 Python 服务传递统一的请求 ID？
线上是否应该让前端直接访问两个后端？
如何使用 Express 或 API Gateway 统一鉴权、限流和反向代理？
两套服务如何共享模型 API 配置？
Node 和 Python 的数据结构不一致时如何管理接口版本？
如何保证前端、Express 和 FastAPI 可以一次启动？`],
  ["第八层", "缓存、并发与可靠性", String.raw`
系统中有哪些缓存？
检索缓存的 Key 包含哪些字段？
为什么缓存 Key 必须包含索引版本？
缓存命中后为什么仍然要生成新的 request_id？
Redis 和内存缓存分别有什么优缺点？
多实例部署时为什么不能只使用进程内存？
证据过期后用户点击引用会发生什么？
如何避免 Redis 中保存过多证据造成内存膨胀？
BGE 模型和索引为什么要在进程内缓存？
FastAPI 中为什么使用 asyncio.to_thread 执行检索？
CPU 密集型检索会不会阻塞事件循环？
多个并发请求同时调用 Reranker 时会发生什么？
如何限制 Reranker 并发，防止服务器被打满？
模型 API 超时后如何重试？
为什么重试次数不能无限增加？
SSE 已经输出部分内容后模型失败，应如何处理？
如何实现幂等、限流、熔断和降级？
如何监控检索耗时、首 Token 延迟和完整响应耗时？
需要记录哪些日志才能排查一次错误回答？
如何对知识问答接口进行压力测试？`],
  ["第九层", "性能优化与上线设计", String.raw`
当前系统最主要的性能瓶颈是什么？
为什么 CPU Reranker 每题需要约 5.5 秒？
使用 GPU 后预计哪些部分会得到加速？
如何通过减少候选数量降低 Reranker 延迟？
批处理为什么可以提升推理吞吐量？
批处理吞吐和单请求实时延迟有什么区别？
如何缓存查询向量和重排序结果？
是否可以先用 BM25 判断查询类型，再决定是否执行 Dense？
如何对热门问题进行答案缓存？
答案缓存会产生哪些过期和可信度问题？
如何进行水平扩容？
FAISS 索引在多实例之间如何分发和更新？
更新索引期间如何保证服务不中断？
如何使用蓝绿索引或版本化索引？
如果知识库扩大到一百万个片段，需要调整什么？
Flat FAISS、IVF、HNSW 分别适用于什么场景？
如何估算模型、索引、BM25 语料和缓存的内存占用？
如何保护模型 API Key？
CORS、鉴权和限流应该放在哪一层？
项目上线前还缺少哪些安全与可观测性能力？`],
  ["第十层", "开放性与压力追问", String.raw`
BM25 已经达到 0.8433，为什么不删除 Dense？
等权 RRF 比 BM25 差，是否说明混合检索设计失败？
最终只提升 2 个百分点，却增加约 5.5 秒延迟，这个优化是否有业务价值？
300 题由大模型生成，评测结果是否可信？
没有专家逐题标注，为什么可以使用这套实验数据？
为什么 Recall@5 高不代表最终答案一定正确？
如果知识库本身包含错误内容，RAG 如何处理？
如果用户的问题同时涉及多个文档，当前评测方式是否有效？
如何支持多轮问题中的代词消解，例如“它的审批人是谁”？
当前请求虽然携带历史消息，检索过程是否真正使用了历史？
如何实现多轮查询改写，同时避免改写偏离原问题？
如何证明 Reranker 的提升不是测试集偶然波动？
是否应该给 Recall@5 计算置信区间？
如何使用 Bootstrap 或显著性检验比较两种检索方法？
如果重新做这个项目，你最先重构哪个部分？
项目目前最大的技术债是什么？
哪些能力已经真实实现，哪些仍属于后续设计？
怎样把系统迁移到法律、医疗或制造业？
迁移领域时哪些组件可以复用，哪些必须重新训练或配置？
如果只给你一周时间继续优化，你会优先做哪三件事？`],
  ["专题", "分块策略", String.raw`
为什么需要分块，整篇文档向量化有什么问题？
为什么选择 300 字符和 50 字符重叠？
片段太长、太短分别有什么影响？
重叠太大会造成什么问题？
固定长度分块会不会切断语义？
为什么把相邻片段也作为相关片段？
如何处理标题、条款、表格和跨片段答案？
如何通过实验选择最佳分块参数？
分块大小会怎样影响 Dense、BM25 和 Reranker？
如果知识库扩大，分块策略需要怎么调整？`],
];

const mustAnswerText = new Set([
  "为什么需要混合检索？",
  "请完整介绍四组消融实验的数据。",
  "300 题评测集是如何构建的？",
  "评测集的人工标注成本是多少？",
  "[#n] 引用协议是如何设计的？",
  "拒答阈值过高造成误判怎么办？",
  "为什么项目同时使用 Node.js 和 Python？",
  "当前是 Express 调用 Python，还是前端分别调用两个服务？",
]);

const focusText = new Set([
  "为什么本项目等权 RRF 的 Recall@5 反而低于 BM25？",
  "Recall@5 从 0.7333 提升到 0.8633 意味着什么？",
  "当前引用协议能否保证引用内容一定支持生成结论？",
  "BM25 已经达到 0.8433，为什么不删除 Dense？",
  "等权 RRF 比 BM25 差，是否说明混合检索设计失败？",
  "最终只提升 2 个百分点，却增加约 5.5 秒延迟，这个优化是否有业务价值？",
  "哪些能力已经真实实现，哪些仍属于后续设计？",
  "为什么选择 300 字符和 50 字符重叠？",
  "固定长度分块会不会切断语义？",
  "如何通过实验选择最佳分块参数？",
]);

const rows = [];
let id = 1;
for (const [level, module, raw] of groups) {
  for (const question of raw.trim().split("\n").map((x) => x.trim()).filter(Boolean)) {
    const priority = mustAnswerText.has(question) ? "必答" : focusText.has(question) ? "重点" : "常规";
    rows.push([id++, level, module, question, priority, "未准备", ""]);
  }
}

if (rows.length !== 200) {
  throw new Error(`题目数量异常：${rows.length}，预期 200`);
}

const workbook = Workbook.create();
const allSheet = workbook.worksheets.add("问题总表");
const focusSheet = workbook.worksheets.add("必答与重点");
const guideSheet = workbook.worksheets.add("复习说明");

const headers = [["序号", "难度层级", "模块", "问题", "优先级", "准备状态", "个人备注"]];
allSheet.getRange("A1:G1").values = headers;
allSheet.getRange(`A2:G${rows.length + 1}`).values = rows;
const allTable = allSheet.tables.add(`A1:G${rows.length + 1}`, true, "QuestionBankTable");
allTable.style = "TableStyleMedium2";
allTable.showFilterButton = true;
allSheet.freezePanes.freezeRows(1);
allSheet.freezePanes.freezeColumns(3);
allSheet.showGridLines = false;
allSheet.getRange("A1:G1").format = {
  fill: "#1F4E78",
  font: { bold: true, color: "#FFFFFF", size: 11 },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
allSheet.getRange(`A2:G${rows.length + 1}`).format = {
  font: { name: "Microsoft YaHei", size: 10 },
  verticalAlignment: "center",
};
allSheet.getRange(`D2:D${rows.length + 1}`).format.wrapText = true;
allSheet.getRange(`G2:G${rows.length + 1}`).format.wrapText = true;
allSheet.getRange(`A2:C${rows.length + 1}`).format.horizontalAlignment = "center";
allSheet.getRange(`E2:F${rows.length + 1}`).format.horizontalAlignment = "center";
allSheet.getRange(`A2:A${rows.length + 1}`).format.numberFormat = "0";
allSheet.getRange("A:A").format.columnWidth = 8;
allSheet.getRange("B:B").format.columnWidth = 12;
allSheet.getRange("C:C").format.columnWidth = 25;
allSheet.getRange("D:D").format.columnWidth = 68;
allSheet.getRange("E:E").format.columnWidth = 10;
allSheet.getRange("F:F").format.columnWidth = 12;
allSheet.getRange("G:G").format.columnWidth = 30;
allSheet.getRange("1:1").format.rowHeight = 28;
allSheet.getRange(`2:${rows.length + 1}`).format.rowHeight = 34;
allSheet.getRange(`F2:F${rows.length + 1}`).dataValidation = {
  rule: { type: "list", values: ["未准备", "准备中", "已掌握"] },
};
allSheet.getRange(`E2:E${rows.length + 1}`).conditionalFormats.add("containsText", {
  text: "必答",
  format: { fill: "#FCE4D6", font: { bold: true, color: "#C00000" } },
});
allSheet.getRange(`E2:E${rows.length + 1}`).conditionalFormats.add("containsText", {
  text: "重点",
  format: { fill: "#FFF2CC", font: { bold: true, color: "#9C6500" } },
});
allSheet.getRange(`F2:F${rows.length + 1}`).conditionalFormats.add("containsText", {
  text: "已掌握",
  format: { fill: "#E2F0D9", font: { color: "#375623" } },
});
allSheet.getRange(`F2:F${rows.length + 1}`).conditionalFormats.add("containsText", {
  text: "准备中",
  format: { fill: "#DDEBF7", font: { color: "#1F4E78" } },
});

const priorityRows = rows.filter((row) => row[4] !== "常规");
focusSheet.getRange("A1:G1").values = headers;
focusSheet.getRange(`A2:G${priorityRows.length + 1}`).values = priorityRows;
const focusTable = focusSheet.tables.add(`A1:G${priorityRows.length + 1}`, true, "PriorityQuestionsTable");
focusTable.style = "TableStyleMedium9";
focusTable.showFilterButton = true;
focusSheet.freezePanes.freezeRows(1);
focusSheet.showGridLines = false;
focusSheet.getRange("A1:G1").format = {
  fill: "#7F6000",
  font: { bold: true, color: "#FFFFFF", size: 11 },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
focusSheet.getRange(`A2:G${priorityRows.length + 1}`).format = {
  font: { name: "Microsoft YaHei", size: 10 },
  verticalAlignment: "center",
};
focusSheet.getRange(`D2:D${priorityRows.length + 1}`).format.wrapText = true;
focusSheet.getRange(`A2:C${priorityRows.length + 1}`).format.horizontalAlignment = "center";
focusSheet.getRange(`E2:F${priorityRows.length + 1}`).format.horizontalAlignment = "center";
focusSheet.getRange("A:A").format.columnWidth = 8;
focusSheet.getRange("B:B").format.columnWidth = 12;
focusSheet.getRange("C:C").format.columnWidth = 25;
focusSheet.getRange("D:D").format.columnWidth = 68;
focusSheet.getRange("E:E").format.columnWidth = 10;
focusSheet.getRange("F:F").format.columnWidth = 12;
focusSheet.getRange("G:G").format.columnWidth = 30;
focusSheet.getRange("1:1").format.rowHeight = 28;
focusSheet.getRange(`2:${priorityRows.length + 1}`).format.rowHeight = 38;
focusSheet.getRange(`F2:F${priorityRows.length + 1}`).dataValidation = {
  rule: { type: "list", values: ["未准备", "准备中", "已掌握"] },
};

guideSheet.showGridLines = false;
guideSheet.getRange("A1:F1").merge();
guideSheet.getRange("A1").values = [["CoalChat 项目答辩问题集"]];
guideSheet.getRange("A1:F1").format = {
  fill: "#1F4E78",
  font: { bold: true, color: "#FFFFFF", size: 18 },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
guideSheet.getRange("A1:F1").format.rowHeight = 40;
guideSheet.getRange("A3:B3").values = [["统计项", "数量"]];
guideSheet.getRange("A4:A8").values = [["总题数"], ["必答题"], ["重点题"], ["常规题"], ["分块专题题"]];
guideSheet.getRange("B4:B8").formulas = [
  ["=COUNTA('问题总表'!$A$2:$A$201)"],
  ["=COUNTIF('问题总表'!$E$2:$E$201,\"必答\")"],
  ["=COUNTIF('问题总表'!$E$2:$E$201,\"重点\")"],
  ["=COUNTIF('问题总表'!$E$2:$E$201,\"常规\")"],
  ["=COUNTIF('问题总表'!$C$2:$C$201,\"分块策略\")"],
];
guideSheet.getRange("A3:B8").format.borders = { preset: "all", style: "thin", color: "#D9E2F3" };
guideSheet.getRange("A3:B3").format = {
  fill: "#D9EAF7",
  font: { bold: true, color: "#1F4E78" },
  horizontalAlignment: "center",
};
guideSheet.getRange("B4:B8").format = {
  font: { bold: true, color: "#1F4E78", size: 12 },
  horizontalAlignment: "center",
  numberFormat: "0",
};
guideSheet.getRange("D3:F3").merge();
guideSheet.getRange("D3").values = [["建议复习顺序"]];
guideSheet.getRange("D3:F3").format = {
  fill: "#FFF2CC",
  font: { bold: true, color: "#7F6000" },
  horizontalAlignment: "center",
};
guideSheet.getRange("D4:F8").merge(true);
guideSheet.getRange("D4:F8").values = [
  ["1. 先掌握“必答与重点”工作表中的问题"],
  ["2. 再按第一层到第十层逐级复习"],
  ["3. 分块策略作为独立专题准备"],
  ["4. 在“准备状态”列持续更新掌握情况"],
  ["5. 在“个人备注”中记录答题口径和项目证据"],
];
guideSheet.getRange("D4:F8").format = {
  fill: "#FFFBEB",
  font: { color: "#595959", size: 11 },
  verticalAlignment: "center",
  wrapText: true,
  borders: { preset: "outside", style: "thin", color: "#E6D690" },
};
guideSheet.getRange("A10:F10").merge();
guideSheet.getRange("A10").values = [["优先级说明"]];
guideSheet.getRange("A10:F10").format = {
  fill: "#E2F0D9",
  font: { bold: true, color: "#375623" },
};
guideSheet.getRange("A11:F13").merge(true);
guideSheet.getRange("A11:F13").values = [
  ["必答：前序明确要求必须回答的核心问题，建议准备 1～2 分钟完整口径。"],
  ["重点：容易被继续追问、最能体现项目理解深度的问题。"],
  ["常规：用于补齐基础知识和扩展追问，可按模块逐步准备。"],
];
guideSheet.getRange("A11:F13").format = { wrapText: true, verticalAlignment: "center" };
guideSheet.getRange("A:A").format.columnWidth = 18;
guideSheet.getRange("B:B").format.columnWidth = 12;
guideSheet.getRange("C:C").format.columnWidth = 4;
guideSheet.getRange("D:F").format.columnWidth = 18;
guideSheet.getRange("4:13").format.rowHeight = 28;

await fs.mkdir(outputDir, { recursive: true });

for (const [sheetName, range, fileName] of [
  ["问题总表", "A1:G30", "preview_all.png"],
  ["必答与重点", `A1:G${Math.min(priorityRows.length + 1, 30)}`, "preview_focus.png"],
  ["复习说明", "A1:F13", "preview_guide.png"],
]) {
  const preview = await workbook.render({ sheetName, range, scale: 1.4, format: "png" });
  await fs.writeFile(`${outputDir}/${fileName}`, new Uint8Array(await preview.arrayBuffer()));
}

const check = await workbook.inspect({
  kind: "table",
  range: "问题总表!A1:G12",
  include: "values,formulas",
  tableMaxRows: 12,
  tableMaxCols: 7,
});
console.log(check.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
});
console.log(errors.ndjson);

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(`${outputDir}/CoalChat_项目答辩问题集.xlsx`);
console.log(JSON.stringify({ output: `${outputDir}/CoalChat_项目答辩问题集.xlsx`, total: rows.length, priority: priorityRows.length }));
