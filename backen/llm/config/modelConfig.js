// config/modelConfig.js
module.exports = {
  apiUrl: process.env.LLM_API_URL || 'http://localhost:8080/v1/completions',
  modelParams: {
    model: process.env.LLM_MODEL_NAME || 'default-model',
    max_tokens: 512
  }
};