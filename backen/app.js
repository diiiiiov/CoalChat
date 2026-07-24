const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '.env') });
// require('dotenv').config();
const express = require('express');
const cors = require('cors');
const nlpRoutes = require('./nlp/routes/nlpRoutes');
const llmRoutes = require('./llm/routes/llmRoutes');
const knowledgeRoutes = require('./knowledge/routes/knowledgeRoutes');

const app = express();
const PORT = process.env.PORT || 3000;

// 验证环境变量
// console.log('加载的 PORT:', process.env.PORT);

// 中间件
app.use(cors({
  methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization']
}));
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// 健康检查接口
app.get('/health', (req, res) => {
  res.json({ 
    status: 'ok', 
    service: 'coal-chat-backend',
    timestamp: new Date().toISOString(),
    modules: ['nlp', 'llm', 'knowledge']
  });
});

// 根路径 - API文档
app.get('/', (req, res) => {
  res.json({ 
    message: '煤矿安全问答系统后端服务已启动',
    version: '1.0.0',
    modules: {
      nlp: {
        description: '自然语言处理模块',
        endpoints: {
          classify: '/api/nlp/classify',
          judge: '/api/nlp/judge',
          extract: '/api/nlp/extract',
          predict: '/api/nlp/predict'
        }
      },
      llm: {
        description: 'LLM对话模块',
        endpoints: {
          chat: '/api/llm/chat (支持单轮和多轮对话)'
        }
      }
    },
    healthCheck: '/health'
  });
});

// 路由
app.use('/api/nlp', nlpRoutes);
app.use('/api/llm', llmRoutes);
app.use('/api/knowledge', knowledgeRoutes);

// 404处理
app.use('*', (req, res) => {
  res.status(404).json({
    success: false,
    message: '接口不存在',
    availableEndpoints: {
      nlp: '/api/nlp/*',
      llm: '/api/llm/*',
      knowledge: '/api/knowledge/*',
      health: '/health',
      docs: '/'
    }
  });
});

// 全局错误处理中间件
app.use((err, req, res, next) => {
  console.error('全局错误:', err.stack);
  res.status(500).json({ 
    success: false, 
    message: '服务器内部错误',
    timestamp: new Date().toISOString()
  });
});

// 启动服务器
app.listen(PORT, () => {
  console.log(`煤矿安全问答系统后端服务运行在端口 ${PORT}`);
  console.log(`健康检查: http://localhost:${PORT}/health`);
  console.log(`API文档: http://localhost:${PORT}/`);
  console.log(`NLP模块: http://localhost:${PORT}/api/nlp`);
  console.log(`LLM模块: http://localhost:${PORT}/api/llm`);
  console.log(`知识库模块: http://localhost:${PORT}/api/knowledge`);
});