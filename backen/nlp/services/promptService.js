/**
 * 生成智能分类提示词
 * @param {Object} data - 包含分类所需数据
 * @returns {string} 提示词
 */
function generateClassificationPrompt(data) {
  return `你是煤矿领域的NLP专家，需要完成文本智能分类任务。
业务背景：${data.background || '无特殊背景'}
指定分类类型：${data.category || '请根据文本内容自行判断合理分类'}
请对待分类文本进行精准分类，并给出分类依据。
待分类文本：${data.text}

输出格式：
分类结果：[具体分类]
分类依据：[说明分类理由]`;
}

/**
 * 生成智能判别提示词
 * @param {Object} data - 包含判别所需数据
 * @returns {string} 提示词
 */
function generateJudgmentPrompt(data) {
  return `你作为煤矿安全领域的专业专家，需严格依据给定判定标准，对原始语料开展智能判别工作。
判定标准：${data.standard || '暂未提供明确判定标准'}
请以专业、严谨的态度，基于上述标准，深入分析以下原始语料，给出精准且明确的判定结果、详细依据以及合理建议措施。
原始语料：${data.text || '无有效原始语料内容'}

输出需严格遵循以下格式：
判定结果：[符合/不符合/部分符合/无法判定，需清晰表明对标准的契合情况]
判定依据：[详细阐述判断过程与理由，结合煤矿安全专业知识，说明语料与标准的关联点]
建议措施：[依据判定结果，从煤矿安全管理、整改、预防等角度给出切实可行的建议]`;
}

/**
 * 生成关键信息提取提示词
 * @param {Object} data - 包含提取所需数据
 * @returns {string} 提示词
 */
function generateExtractionPrompt(data) {
  return `你是煤矿领域的信息提取专家，需要从文本中提取关键信息。
需要提取的内容：${data.target || '所有重要信息'}
请从以下原始语料中精准提取指定的关键信息，确保信息完整、准确。
原始语料：${data.text}

输出格式：
提取结果：
- [信息类别1]：[具体内容]
- [信息类别2]：[具体内容]
...
提取说明：[对提取结果的补充说明]`;
}

/**
 * 生成数值预测提示词
 * @param {Object} data - 包含预测所需数据
 * @returns {string} 提示词
 */
function generatePredictionPrompt(data) {
  return `你是煤矿领域的数据分析专家，擅长基于时序数据进行数值预测。
请根据以下历史时序数据，预测未来的数值变化趋势，并给出具体的预测结果和置信度。
时序数据：${data.timeSeriesData || '无数据'}

输出格式：
预测结果：[未来特定时间段的预测数值，至少包含3个时间点]
趋势分析：[说明数值变化趋势及可能原因]
置信度：[0-100%之间的数值，说明预测的可靠程度]
注意事项：[基于预测结果的建议和注意事项]`;
}

module.exports = {
  generateClassificationPrompt,
  generateJudgmentPrompt,
  generateExtractionPrompt,
  generatePredictionPrompt
};