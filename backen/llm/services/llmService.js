/**
 * 生成对话提示词
 * @param {Object} data - 包含对话所需数据
 * @returns {string} 提示词
 */
function generateChatPrompt(data) {
  const { message, context, role } = data;
  
  let systemPrompt = `你是一个专业的煤矿安全助手，具备丰富的煤矿安全知识和经验。
你的职责是：
1. 回答用户关于煤矿安全的问题
2. 提供专业的安全建议和指导
3. 解释煤矿安全相关的技术概念
4. 帮助用户理解和遵守安全规程

请用专业、准确、易懂的语言回答用户问题。`;

  if (role) {
    systemPrompt += `\n\n当前角色：${role}`;
  }

  if (context) {
    systemPrompt += `\n\n对话上下文：${context}`;
  }

  return {
    system: systemPrompt,
    user: message
  };
}

module.exports = {
  generateChatPrompt
  };