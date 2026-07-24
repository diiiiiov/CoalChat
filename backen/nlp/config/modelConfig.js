// config/modelConfig.js
module.exports = {
  apiUrl: process.env.LLM_API_URL || 'http://localhost:8080/v1/completions',
  modelParams: {
    model: process.env.LLM_MODEL_NAME || 'default-model',
    temperature: 0.7,
    max_tokens: 4096,
    top_p: 0.9
  }
};