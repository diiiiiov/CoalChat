const axios = require('axios');
const { generateChatPrompt } = require('../services/llmService');
const modelConfig = require('../config/modelConfig');

// 调用自定义大模型API的函数
async function callCustomModel({ prompt, max_tokens }) {
  const { apiUrl, modelParams } = modelConfig;
  const data = {
    model: modelParams.model,
    prompt,
    max_tokens: max_tokens || modelParams.max_tokens
  };
  try {
    const resp = await axios.post(apiUrl, data, {
      headers: { 'Content-Type': 'application/json' },
      timeout: 20000
    });
    return resp.data.choices?.[0]?.text || 'AI无回复';
  } catch (err) {
    throw err;
  }
}

/**
 * 通用对话处理
 */
exports.chat = async (req, res) => {
  try {
    const { message, messages, context, role } = req.body;
    let chatPrompt = '';
    if (messages && Array.isArray(messages) && messages.length > 0) {
      // 多轮对话模式，拼接历史消息
      chatPrompt = messages.map(m => `${m.role === 'user' ? '用户' : '助手'}: ${m.content}`).join('\n');
      if (message) chatPrompt += `\n用户: ${message}`;
    } else if (message) {
      // 单轮对话模式
      const promptData = generateChatPrompt({ message, context, role });
      chatPrompt = `${promptData.system}\n用户: ${promptData.user}`;
    } else {
      return res.status(400).json({
        success: false,
        message: '请提供message或messages参数'
      });
    }
    // 调用大模型
    const result = await callCustomModel({ prompt: chatPrompt, max_tokens: 512 });
    console.log('大模型调用成功');
    res.json({ 
      success: true, 
      result,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      message: error.message
    });
  }
};