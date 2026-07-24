const express = require('express');
const router = express.Router();
const llmController = require('../controllers/llmController');

// 通用对话接口（支持单轮和多轮对话）
router.post('/chat', llmController.chat);

module.exports = router;