/**
 * 知识库配置文件
 */

module.exports = {
  // LLM配置
  llm: {
    // 默认模型
    defaultModel: process.env.DEFAULT_MODEL || 'deepseek-chat',
    
    // 默认参数
    defaultTemperature: 0.7,
    defaultMaxTokens: null,
    
    // 支持的模型列表
    supportedModels: [
      'deepseek-chat',
      'gpt-3.5-turbo',
      'gpt-4',
      'claude-3-sonnet'
    ]
  },

  // 文档检索配置
  search: {
    // 默认检索参数
    defaultTopK: 5,
    defaultScoreThreshold: 0.5,
    
    // 最大检索数量
    maxTopK: 20,
    
    // 支持的文件类型
    supportedFileTypes: [
      '.txt', '.md', '.docx', '.pdf', '.json', '.csv', '.xml', '.html', '.htm'
    ]
  },

  // 查询改写配置
  queryRewrite: {
    // 最大重试次数
    maxRetries: 2,
    
    // 历史对话轮数
    historyRounds: 3,
    
    // 温度参数
    temperature: 0.7
  },

  // 流式输出配置
  streaming: {
    // 字符输出延迟（毫秒）
    charDelay: 50,
    
    // 最大输出长度
    maxLength: 10000
  },

  // 知识库路径配置
  paths: {
    // 知识库根目录
    knowledgeBaseRoot: '../knowledge_base',
    
    // 临时文件目录
    tempDir: '../temp'
  },

  // API配置
  api: {
    // 请求超时时间（毫秒）
    timeout: 30000,
    
    // 最大请求体大小
    maxBodySize: '10mb',
    
    // 允许的文件大小（字节）
    maxFileSize: 10 * 1024 * 1024 // 10MB
  },

  // 日志配置
  logging: {
    // 是否启用详细日志
    verbose: process.env.NODE_ENV === 'development',
    
    // 日志级别
    level: process.env.LOG_LEVEL || 'info'
  }
}; 