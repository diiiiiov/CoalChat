const axios = require('axios');
const {
  generateClassificationPrompt,
  generateJudgmentPrompt,
  generateExtractionPrompt,
  generatePredictionPrompt
} = require('../services/promptService');
const modelConfig = require('../config/modelConfig');

/**
 * 调用大模型API（直接使用 axios 对接自定义模型）
 */
async function callModelAPI(prompt) { // 注意：参数改为 prompt 字符串
  try {
    console.log('调用自定义模型 API，提示词:', prompt);
    console.log('API 地址:', modelConfig.apiUrl);

    const response = await axios.post(modelConfig.apiUrl, {
      model: modelConfig.modelParams.model,
      prompt: prompt, // 用 prompt 字段，和测试代码一致
      max_tokens: modelConfig.modelParams.max_tokens,
      temperature: modelConfig.modelParams.temperature,
      top_p: modelConfig.modelParams.top_p
    }, {
      headers: { 'Content-Type': 'application/json' }
    });

    console.log('模型响应:', response.data);
    // 假设响应结构是 { choices: [{ text: "回复内容" }] }（和 /v1/completions 格式对齐）
    return response.data.choices[0].text;
  } catch (error) {
    console.error('模型调用失败:', error.response?.data || error.message);
    throw new Error('调用大模型时发生错误');
  }
}

/**
 * 智能分类处理
 */
exports.classify = async (req, res) => {
  try {
    const { text1, text2, text3 } = req.body;

    const prompt = generateClassificationPrompt({
      category: text1,
      background: text2,
      text: text3
    });

    const result = await callModelAPI(prompt);
    res.json({ success: true, result });
  } catch (error) {
    res.status(500).json({
      success: false,
      message: error.message
    });
  }
};

/**
 * 智能判别处理
 */
exports.judge = async (req, res) => {
  try {
    const { judgmentText1: originalText, judgmentText2: standard } = req.body;

    if (!originalText || !standard) {
      return res.status(400).json({
        success: false,
        message: '原始语料和判定标准为必填项'
      });
    }

    const prompt = generateJudgmentPrompt({
      text: originalText,
      standard: standard
    });

    const result = await callModelAPI(prompt);
    res.json({ success: true, result });
  } catch (error) {
    res.status(500).json({
      success: false,
      message: error.message
    });
  }
};

/**
 * 关键信息提取处理
 */
exports.extract = async (req, res) => {
  try {
    const { extractionText1: originalText, extractionText2: target } = req.body;

    if (!originalText) {
      return res.status(400).json({
        success: false,
        message: '原始语料为必填项'
      });
    }

    const prompt = generateExtractionPrompt({
      text: originalText,
      target: target
    });

    const result = await callModelAPI(prompt);
    res.json({ success: true, result });
  } catch (error) {
    console.error('信息提取错误:', error);
    res.status(500).json({
      success: false,
      message: error.message
    });
  }
};

/**
 * 数值预测处理
 */
exports.predict = async (req, res) => {
  try {
    const { predictionText1: timeSeriesData } = req.body;

    const prompt = generatePredictionPrompt({
      timeSeriesData: timeSeriesData
    });

    const result = await callModelAPI(prompt);
    res.json({ success: true, result });
  } catch (error) {
    res.status(500).json({
      success: false,
      message: error.message
    });
  }
};
