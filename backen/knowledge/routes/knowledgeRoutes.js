const express = require('express');
const router = express.Router();
const multer = require('multer');
const path = require('path');
const { uploadKnowledgeFile, knowledgeBaseChat, rebuildVectorStore } = require('../controllers/knowledgeController');
const { cancelKnowledgeOperation } = require('../controllers/knowledgeController');
const iconv = require('iconv-lite');

// 设置 multer 存储目录
const storage = multer.diskStorage({
  destination: function (req, file, cb) {
    // knowledge_base/知识库名/context/
    const kb = req.body.knowledge_base;
    const dest = path.join(__dirname, '../../../knowledge_base', kb, 'context');
    require('fs').mkdirSync(dest, { recursive: true });
    cb(null, dest);
  },
  filename: function (req, file, cb) {
    cb(null, iconv.decode(Buffer.from(file.originalname, 'binary'), 'utf8'));
  }
});
const upload = multer({ storage });

router.post('/upload', upload.array('file'), uploadKnowledgeFile);
router.post('/rebuild_vector', rebuildVectorStore);
router.post('/chat', knowledgeBaseChat);
router.post('/cancel_upload', cancelKnowledgeOperation);

module.exports = router;
