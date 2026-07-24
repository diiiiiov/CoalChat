const express = require('express');
const router = express.Router();
const nlpController = require('../controllers/nlpController');

// 智能分类接口
router.post('/classify', nlpController.classify);

// 智能判别接口
router.post('/judge', nlpController.judge);

// 关键信息提取接口
router.post('/extract', nlpController.extract);

// 数值预测接口
router.post('/predict', nlpController.predict);

module.exports = router;