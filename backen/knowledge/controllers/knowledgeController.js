const { exec, spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const { knowledgeBasePrompts } = require('../services/promptService');
const modelConfig = require('../config/modelConfig');
const axios = require('axios');
const os = require("os");
const { promisify } = require('util');
const { v4: uuidv4 } = require('uuid');

// 配置环境变量供Python脚本使用
process.env.LLM_API_URL = modelConfig.apiUrl;
process.env.LLM_MODEL_NAME = modelConfig.modelParams.model;
process.env.EMBED_MODEL_PATH = path.resolve(__dirname, '../../../knowledge_base/samples/vector_store/bge-large-zh');
// 如需API密钥可添加
// process.env.API_KEY = 'your-api-key';

console.log('【初始化】knowledge模块加载的modelConfig:', modelConfig);
console.log('【初始化】设置的环境变量 - LLM_API_URL:', process.env.LLM_API_URL);
console.log('【初始化】设置的环境变量 - LLM_MODEL_NAME:', process.env.LLM_MODEL_NAME);
console.log('【初始化】设置的环境变量 - EMBED_MODEL_PATH:', process.env.EMBED_MODEL_PATH);

// 工具函数：promisify exec
const execAsync = promisify(require('child_process').exec);

// 全局进程管理：记录重建向量库的进程
const vectorBuildProcesses = new Map();

// 路径配置（使用绝对路径避免相对路径问题）
const RERANK_SCRIPT_PATH = path.resolve(__dirname, '../scripts/rerank_infer.py');
const REWRITE_SCRIPT_PATH = path.resolve(__dirname, '../scripts/rewrite_query.py');
const RERANK_CONFIG_PATH = path.resolve(__dirname, '../bge-reranker-base/config.json');
const RERANK_MODEL_PATH = path.resolve(__dirname, '../bge-reranker-base');

// 验证关键路径是否存在
console.log('【路径验证】查询改写脚本:', REWRITE_SCRIPT_PATH, '存在:', fs.existsSync(REWRITE_SCRIPT_PATH));
console.log('【路径验证】重排序脚本:', RERANK_SCRIPT_PATH, '存在:', fs.existsSync(RERANK_SCRIPT_PATH));
console.log('【路径验证】重排序配置:', RERANK_CONFIG_PATH, '存在:', fs.existsSync(RERANK_CONFIG_PATH));
console.log('【路径验证】重排序模型:', RERANK_MODEL_PATH, '存在:', fs.existsSync(RERANK_MODEL_PATH));

/**
 * 调用查询改写脚本，生成优化后的查询
 * @param {string} originalQuery 原始查询
 * @param {any} history 历史对话（可能为任意类型）
 * @returns {Promise<string>} 改写后的查询
 */
async function rewriteQuery(originalQuery, history = "") {
    console.log('\n===== 进入查询改写流程 =====');

    // 关键修复：确保history始终为字符串类型
    if (typeof history !== 'string') {
        console.warn('【查询改写】history不是字符串类型，自动转换为字符串');
        try {
            // 尝试将对象/数组转换为JSON字符串，空值转换为空字符串
            history = history ? JSON.stringify(history) : "";
        } catch (e) {
            console.error('【查询改写】转换history为字符串失败:', e.message);
            history = ""; // 转换失败时使用空字符串
        }
    }

    console.log('【查询改写】原始查询:', originalQuery);
    console.log('【查询改写】历史对话:', history || '无');

    try {
        // 生成临时文件存储结果
        const tmpOutputPath = path.join(os.tmpdir(), `rewrite_result_${uuidv4()}.json`);
        console.log('【查询改写】临时输出文件路径:', tmpOutputPath);

        // 处理特殊字符转义
        const escapedHistory = history.replace(/"/g, '\\"').replace(/\n/g, '\\n');
        const escapedQuery = originalQuery.replace(/"/g, '\\"').replace(/\n/g, '\\n');

        // 调用Python脚本
        const args = [
            `"${REWRITE_SCRIPT_PATH}"`,
            `--history "${escapedHistory}"`,
            `--query "${escapedQuery}"`,
            `--output "${tmpOutputPath}"`
        ];
        const command = `python ${args.join(' ')}`;
        console.log('【查询改写】执行命令:', command);

        const start = Date.now();
        const { stdout, stderr } = await execAsync(command, {
            maxBuffer: 1024 * 1024 * 10,
            timeout: 30000 // 30秒超时
        });
        console.log(`【查询改写】脚本执行耗时: ${Date.now() - start}ms`);

        // 输出Python脚本的完整输出
        console.log('【查询改写脚本 stdout】:', stdout);
        if (stderr) console.warn('【查询改写脚本 stderr】:', stderr);

        // 验证输出文件是否存在
        if (!fs.existsSync(tmpOutputPath)) {
            throw new Error("查询改写脚本未生成输出文件");
        }

        // 读取改写结果
        const result = JSON.parse(fs.readFileSync(tmpOutputPath, 'utf8'));
        console.log('【查询改写】脚本返回结果:', result);

        // 清理临时文件
        fs.unlinkSync(tmpOutputPath);
        console.log('【查询改写】临时文件已清理');

        const finalQuery = result.success ? result.rewritten_query : originalQuery;
        console.log('【查询改写】最终使用的查询:', finalQuery);
        return finalQuery;
    } catch (err) {
        console.error('【查询改写】执行失败:', err.message);
        if (err.stderr) console.error('【查询改写失败详情】:', err.stderr);
        console.log('【查询改写】降级使用原始查询');
        return originalQuery;
    }
}

/**
 * 调用重排序脚本，优化文档相关性
 * @param {string} query 查询文本（改写后）
 * @param {Array} docs 原始检索结果
 * @returns {Promise<Array>} 重排序后的文档
 */
async function rerankDocuments(query, docs) {
    console.log('\n===== 进入重排序流程 =====');
    console.log('【重排序】基于查询:', query);
    console.log('【重排序】原始文档数量:', docs.length);
    if (docs.length === 0) {
        console.log('【重排序】无原始文档，直接返回空数组');
        return [];
    }

    try {
        // 生成临时文件（仅用于输入文档）
        const tmpDocsPath = path.join(os.tmpdir(), `docs_${uuidv4()}.json`);
        console.log('【重排序】临时文档文件路径:', tmpDocsPath);

        // 写入原始文档到临时文件
        fs.writeFileSync(tmpDocsPath, JSON.stringify(docs), 'utf8');
        console.log('【重排序】原始文档已写入临时文件');

        // 处理特殊字符转义
        const escapedQuery = query.replace(/"/g, '\\"').replace(/\n/g, '\\n');

        // 关键修复：移除--output参数，脚本将直接输出JSON结果
        const args = [
            `"${RERANK_SCRIPT_PATH}"`,
            `--query "${escapedQuery}"`,
            `--documents "${tmpDocsPath}"`,
            `--model_path "${RERANK_MODEL_PATH}"`,
            `--config "${RERANK_CONFIG_PATH}"`,
            `--top_k ${docs.length}`
        ];
        const command = `python ${args.join(' ')}`;
        console.log('【重排序】执行命令:', command);

        const start = Date.now();
        const { stdout, stderr } = await execAsync(command, {
            maxBuffer: 1024 * 1024 * 20,
            timeout: 60000 // 60秒超时
        });
        console.log(`【重排序】脚本执行耗时: ${Date.now() - start}ms`);

        // 输出Python脚本的完整输出
        console.log('【重排序脚本 stdout】:', stdout);
        if (stderr) console.warn('【重排序脚本 stderr】:', stderr);

        // 直接从stdout解析结果（不再读取输出文件）
        const rerankedDocs = JSON.parse(stdout);
        console.log('【重排序】重排序后文档数量:', rerankedDocs.length);

        // 清理临时文件
        fs.unlinkSync(tmpDocsPath);
        console.log('【重排序】临时文件已清理');

        return rerankedDocs;
    } catch (err) {
        console.error('【重排序】执行失败:', err.message);
        if (err.stderr) console.error('【重排序失败详情】:', err.stderr);
        console.log('【重排序】降级使用原始文档');
        return docs;
    }
}

// 上传文件接口：接收文件并返回上传结果
exports.uploadKnowledgeFile = async (req, res) => {
    console.log('\n===== 处理文件上传请求 =====');
    try {
        const { knowledge_base, chunk_size, chunk_overlap } = req.body;
        console.log('【文件上传】知识库:', knowledge_base, '分段:', chunk_size, '重合:', chunk_overlap);
        console.log('【文件上传】收到文件数量:', req.files?.length || 0);

        if (!req.files || req.files.length === 0) {
            throw new Error('未收到上传文件');
        }

        res.json({
            code: 0,
            msg: '上传成功',
            files: req.files.map(f => ({ filename: f.filename, path: f.path })),
            success: true
        });
    } catch (err) {
        console.error('【文件上传】处理失败:', err.message);
        res.status(500).json({ code: 1, msg: err.message });
    }
};

// 重建向量库接口：调用Python脚本构建FAISS向量库
exports.rebuildVectorStore = async (req, res) => {
    console.log('\n===== 处理重建向量库请求 =====');
    const { knowledge_base, chunk_size = 300, chunk_overlap = 50 } = req.body;
    console.log('【重建向量库】参数:', { knowledge_base, chunk_size, chunk_overlap });

    if (!knowledge_base) {
        console.error('【重建向量库】缺少knowledge_base参数');
        return res.status(400).json({ code: 1, msg: '缺少 knowledge_base 参数' });
    }

    const scriptPath = path.resolve(__dirname, '../scripts/build_faiss.py');
    const kbPath = path.resolve(__dirname, '../../../knowledge_base', knowledge_base, 'context');
    const vectorPath = path.resolve(__dirname, '../../../knowledge_base', knowledge_base, 'vector_store/bge-large-zh');

    console.log('【重建向量库】脚本路径:', scriptPath, '存在:', fs.existsSync(scriptPath));
    console.log('【重建向量库】知识库目录:', kbPath, '存在:', fs.existsSync(kbPath));

    // 递归创建向量库目录
    try {
        fs.mkdirSync(vectorPath, { recursive: true });
        console.log('【重建向量库】向量库目录已创建:', vectorPath);
    } catch (err) {
        console.error('【重建向量库】创建目录失败:', err.message);
        return res.status(500).json({ code: 1, msg: '创建向量库目录失败' });
    }

    // 拼接Python执行命令
    const cmd = `python "${scriptPath}" --input_dir "${kbPath}" --output_dir "${vectorPath}" --chunk_size ${chunk_size} --overlap ${chunk_overlap} --show_samples`;
    console.log('【重建向量库】执行命令:', cmd);

    try {
        const child = exec(cmd, { maxBuffer: 1024 * 1024 * 20 }, (error, stdout, stderr) => {
            // 进程结束后从Map中移除
            vectorBuildProcesses.delete(knowledge_base);
            console.log('【重建向量库】进程已结束，退出码:', error ? error.code : 0);
            console.log('【FAISS脚本输出】', stdout);

            if (error) {
                console.error('【FAISS脚本错误】', stderr || error.message);
                return res.status(500).json({
                    code: 1,
                    msg: '向量库重建失败',
                    error: stderr || error.message
                });
            }

            res.json({ code: 0, msg: '向量库重建成功', output: stdout });
        });

        // 记录进程，用于取消操作
        vectorBuildProcesses.set(knowledge_base, child);
        console.log('【重建向量库】进程已启动，PID:', child.pid);

        // 立即返回正在处理的状态
        res.json({ code: 0, msg: '向量库重建已启动', pid: child.pid });
    } catch (err) {
        console.error('【重建向量库】启动进程失败:', err.message);
        res.status(500).json({ code: 1, msg: '启动重建进程失败' });
    }
};

// 知识库问答接口：检索向量库 + 调用大模型生成回答
exports.knowledgeBaseChat = async (req, res) => {
    console.log('\n===== 处理知识库问答请求 =====');
    const {
        query,
        knowledge_base_name,
        top_k = 3,
        score_threshold = 0.3,
        model_name = 'qwen_coalchat',
        temperature = 0.7,
        prompt_name = 'default',
        history = ""
    } = req.body;

    console.log('【问答请求】参数:', {
        query,
        knowledge_base_name,
        top_k,
        model_name
    });

    // 校验必要参数
    if (!query) {
        console.error('【问答请求】缺少query参数');
        return res.status(400).json({ code: 1, msg: '缺少 query 参数' });
    }
    if (!knowledge_base_name) {
        console.error('【问答请求】缺少knowledge_base_name参数');
        return res.status(400).json({ code: 1, msg: '缺少 knowledge_base_name 参数' });
    }

    const scriptPath = path.resolve(__dirname, '../scripts/search_faiss.py');
    const vectorPath = path.resolve(__dirname, '../../../knowledge_base', knowledge_base_name, 'vector_store/bge-large-zh');
    const indexPath = path.resolve(vectorPath, 'index.faiss');
    const metaPath = path.resolve(vectorPath, 'index.pkl');
    const modelPath = process.env.EMBED_MODEL_PATH;

    console.log('【问答请求】检索脚本路径:', scriptPath, '存在:', fs.existsSync(scriptPath));
    console.log('【问答请求】向量库索引路径:', indexPath, '存在:', fs.existsSync(indexPath));
    console.log('【问答请求】向量库元数据路径:', metaPath, '存在:', fs.existsSync(metaPath));

    try {
        // 步骤1：查询改写
        const rewrittenQuery = await rewriteQuery(query, history);

        // 步骤2：写入改写后的查询到临时文件
        const tmpQueryPath = path.join(os.tmpdir(), `query_${Date.now()}_${uuidv4()}.txt`);
        fs.writeFileSync(tmpQueryPath, rewrittenQuery, 'utf8');
        console.log('【问答请求】查询临时文件已创建:', tmpQueryPath);

        // 步骤3：执行Python脚本检索向量库
        const args = [
            scriptPath,
            '--query_file', tmpQueryPath,
            '--index', indexPath,
            '--meta', metaPath,
            '--model', modelPath,
            '--top_k', String(top_k)
        ];
        console.log('【问答请求】检索命令参数:', args);

        const py = spawn('python', args, { shell: true });
        console.log('【问答请求】检索进程已启动，PID:', py.pid);

        let stdout = '', stderr = '';

        py.stdout.on('data', data => {
            const str = data.toString().trim();
            stdout += str;
            console.log(`【检索脚本 stdout】[PID:${py.pid}]:`, str);
        });

        py.stderr.on('data', data => {
            const str = data.toString().trim();
            stderr += str;
            console.warn(`【检索脚本 stderr】[PID:${py.pid}]:`, str);
        });

        // 处理脚本执行结果
        py.on('close', async (code) => {
            console.log(`【问答请求】检索进程已结束，退出码:`, code);

            // 清理临时文件
            try {
                fs.unlinkSync(tmpQueryPath);
                console.log('【问答请求】查询临时文件已清理');
            } catch (e) {
                console.warn('【问答请求】清理临时文件失败:', e.message);
            }

            // 脚本执行失败
            if (code !== 0) {
                console.error('【问答请求】检索失败，退出码:', code);
                return res.status(500).json({
                    code: 1,
                    msg: '知识库检索失败',
                    error: stderr,
                    detail: code,
                    stdout
                });
            }

            // 解析检索结果并清洗文本
            let docs = [];
            try {
                console.log('【问答请求】开始解析检索结果:', stdout.substring(0, 200) + '...');
                const rawDocs = JSON.parse(stdout);
                docs = rawDocs.map(doc => ({
                    content: doc.content
                        .replace(/<\/?think>/g, '')
                        .replace(/嗯，用户问的是.*?更详细信息/g, '')
                        .trim(),
                    score: doc.score // 保留原始分数用于重排序
                }));
                console.log('【问答请求】检索结果解析完成，文档数量:', docs.length);
            } catch (e) {
                console.error('【问答请求】解析检索结果失败:', e.message);
                console.error('【问答请求】原始检索输出:', stdout);
                return res.status(500).json({
                    code: 1,
                    msg: '知识库检索结果解析失败',
                    error: e.message,
                    raw: stdout
                });
            }

            // 步骤4：结果重排序
            const rerankedDocs = await rerankDocuments(rewrittenQuery, docs);

            // 构建上下文
            const context = rerankedDocs.map(d => d.content).join('\n');
            console.log('【问答请求】构建的上下文长度:', context.length, '字符');

            // 选择Prompt模板
            let promptTpl = knowledgeBasePrompts[rerankedDocs.length === 0 ? 'empty' : (prompt_name || 'default')]
                || knowledgeBasePrompts['default'];
            console.log('【问答请求】使用的Prompt模板:', prompt_name || 'default');

            // 替换模板变量
            const prompt = promptTpl.replace('{{ context }}', context).replace('{{ question }}', query);
            console.log('【问答请求】生成的Prompt长度:', prompt.length, '字符');

            // 调用大模型生成回答
            try {
                console.log('【问答请求】开始调用大模型:', modelConfig.apiUrl);
                const start = Date.now();
                const aiRes = await callCustomModel({ prompt, max_tokens: 512 });
                console.log(`【问答请求】大模型调用完成，耗时: ${Date.now() - start}ms`);

                res.json({
                    code: 0,
                    data: {
                        answer: aiRes,
                        docs: rerankedDocs.map(d => d.content),
                        rewritten_query: rewrittenQuery
                    }
                });
            } catch (e) {
                console.error('【问答请求】大模型调用失败:', e.message);
                res.json({
                    code: 1,
                    msg: '大模型调用失败',
                    error: e.message
                });
            }
        });

        // 监听进程错误
        py.on('error', (err) => {
            console.error('【问答请求】检索进程错误:', err.message);
            res.status(500).json({ code: 1, msg: '检索进程启动失败', error: err.message });
        });

    } catch (err) {
        console.error('【问答请求】整体流程失败:', err.message);
        res.status(500).json({ code: 1, msg: err.message });
    }
};

// 取消操作接口：终止进程 + 清理文件/向量库
exports.cancelKnowledgeOperation = async (req, res) => {
    console.log('\n===== 处理取消操作请求 =====');
    const { knowledge_base, filename } = req.body;
    console.log('【取消操作】参数:', { knowledge_base, filename });

    if (!knowledge_base) {
        console.error('【取消操作】缺少knowledge_base参数');
        return res.status(400).json({ code: 1, msg: '缺少 knowledge_base 参数' });
    }

    try {
        // 终止重建进程
        const child = vectorBuildProcesses.get(knowledge_base);
        if (child) {
            console.log('【取消操作】终止重建进程，PID:', child.pid);
            child.kill('SIGKILL');
            vectorBuildProcesses.delete(knowledge_base);
        } else {
            console.log('【取消操作】无正在运行的重建进程');
        }

        // 删除上传的文件
        if (filename) {
            const filePath = path.resolve(__dirname, '../../../knowledge_base', knowledge_base, 'context', filename);
            console.log('【取消操作】尝试删除文件:', filePath);
            if (fs.existsSync(filePath)) {
                fs.unlinkSync(filePath);
                console.log('【取消操作】文件已删除');
            } else {
                console.log('【取消操作】文件不存在');
            }
        }

        // 删除向量库目录
        const vectorPath = path.resolve(__dirname, '../../../knowledge_base', knowledge_base, 'vector_store/bge-large-zh');
        console.log('【取消操作】尝试删除向量库目录:', vectorPath);
        if (fs.existsSync(vectorPath)) {
            fs.rmSync(vectorPath, { recursive: true, force: true });
            console.log('【取消操作】向量库目录已删除');
        } else {
            console.log('【取消操作】向量库目录不存在');
        }

        res.json({ code: 0, msg: '已取消并清理相关文件' });
    } catch (err) {
        console.error('【取消操作】处理失败:', err);
        res.status(500).json({ code: 1, msg: err.message });
    }
};

// 调用大模型API：封装请求逻辑
async function callCustomModel({ prompt, max_tokens }) {
    const { apiUrl, modelParams } = modelConfig;
    const data = {
        model: modelParams.model,
        prompt,
        max_tokens: max_tokens || 512,
        temperature: 0.7
    };

    try {
        console.log('【大模型调用】请求参数:', { model: data.model, max_tokens: data.max_tokens });
        const resp = await axios.post(apiUrl, data, {
            headers: { 'Content-Type': 'application/json' },
            timeout: 30000
        });
        console.log('【大模型调用】响应状态:', resp.status);
        return resp.data.choices?.[0]?.text || 'AI无回复';
    } catch (err) {
        console.error('【大模型调用】错误详情:', err.response?.data || err.message);
        throw new Error(`模型调用失败: ${err.message}`);
    }
}
