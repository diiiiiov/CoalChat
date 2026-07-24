<template>
  <div class="settings-container">
    <div class="settings-header">
      <el-button 
        type="text" 
        class="back-btn" 
        @click="goBack"
      >
        <el-icon size="24"><ArrowLeft /></el-icon>
      </el-button>
      <h2 class="settings-title">设置</h2>
    </div>
    
    <!-- 主选项标签 -->
    <div class="mode-tabs">
      <el-button 
        :type="activeTab === 'llm' ? 'primary' : 'text'" 
        @click="activeTab = 'llm'"
      >
        LLM对话
      </el-button>
      <el-button 
        :type="activeTab === 'knowledge' ? 'primary' : 'text'" 
        @click="activeTab = 'knowledge'"
      >
        知识库管理
      </el-button>
    </div>
    
    <!-- LLM对话模式内容 -->
    <div v-if="activeTab === 'llm'">
      <h2 class="sub-title">LLM对话设置</h2>
      <h3 class="section-title">对话模式</h3>
      <div class="section-tip">选择普通大模型对话或知识库问答模式。</div>
      <el-radio-group v-model="chatModeStore.chatMode" class="mode-selector">
        <el-radio label="llm">LLM对话</el-radio>
        <el-radio label="knowledge">知识库问答</el-radio>
      </el-radio-group>
      <h3 class="section-title">Prompt模板</h3>
      <div class="section-tip">选择不同的Prompt模板以适配不同场景。</div>
      <el-select 
        v-model="selectedPrompt" 
        placeholder="请选择" 
        class="prompt-selector"
      >
        <el-option
          v-for="item in getPromptOptions()"
          :key="item.value"
          :label="item.label"
          :value="item.value"
        />
      </el-select>
      <h3 class="section-title">Temperature参数</h3>
      <div class="section-tip">控制生成内容的多样性，数值越高越随机，建议0.7~1.2。</div>
      <div class="temperature-section">
        <div class="temperature-header">
          <h2 class="sub-title inline-title">Temperature：</h2>
          <el-input-number
            v-model="temperature"
            :min="0"
            :max="2"
            :step="0.05"
            :precision="2"
            size="small"
            class="temperature-input"
          />
        </div>
        <div class="slider-with-labels">
          <span class="slider-label">0.00</span>
          <el-slider
            v-model="temperature"
            :min="0"
            :max="2"
            :step="0.05"
            :format-tooltip="formatTemperature"
            class="long-slider"
          />
          <span class="slider-label">2.00</span>
        </div>
      </div>
      <!-- 知识库问答模式特有内容 -->
      <template v-if="chatModeStore.chatMode === 'knowledge'">
        <h3 class="section-title">知识库配置</h3>
        <div class="section-tip">选择知识库及相关参数，仅知识库问答模式下可用。</div>
        <h3 class="section-title">请选择知识库</h3>
        <el-select 
          v-model="selectedKnowledgeBase" 
          placeholder="请选择" 
          class="knowledge-selector"
        >
          <el-option
            v-for="item in knowledgeBaseOptions"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
        <h3 class="section-title">匹配知识条数</h3>
        <el-input-number
          v-model="matchCount"
          :min="1"
          :max="10"
          :step="1"
          size="small"
          class="match-count-input"
        />
        <h3 class="section-title">知识匹配分数阈值</h3>
        <div class="section-tip">分数越高，匹配越严格，建议1.0左右。</div>
        <div class="score-threshold-section">
          <div class="score-threshold-header">
            <h3 class="sub-sub-title inline-title">知识匹配分数阈值：</h3>
            <el-input-number
              v-model="scoreThreshold"
              :min="0"
              :max="2"
              :step="0.05"
              :precision="2"
              size="small"
              class="score-threshold-input"
            />
          </div>
          <div class="slider-with-labels">
            <span class="slider-label">0.00</span>
            <el-slider
              v-model="scoreThreshold"
              :min="0"
              :max="2"
              :step="0.05"
              :format-tooltip="formatScoreThreshold"
              class="long-slider"
            />
            <span class="slider-label">2.00</span>
          </div>
        </div>
      </template>
    </div>
    
    <!-- 知识库管理内容 -->
    <div v-if="activeTab === 'knowledge'" class="knowledge-scroll-area">
      <h2 class="sub-title">知识库管理</h2>
      <!-- 查询关键字和匹配条数 -->
      <div style="margin-bottom: 8px;">
        <div class="section-title">查询关键字</div>
        <el-input v-model="searchKeyword" placeholder="" style="width: 260px; margin-bottom: 16px;" />
        <div class="section-title">匹配条数</div>
        <div style="display: flex; align-items: center; width: 260px;">
          <span style="width: 24px; text-align: left; font-size: 13px; color: #666;">{{matchCount}}</span>
          <el-slider v-model="matchCount" :min="1" :max="100" style="flex: 1; margin: 0 8px;" />
          <span style="width: 24px; text-align: right; font-size: 13px; color: #666;">100</span>
        </div>
      </div>
      <!-- 选择/新建知识库 -->
      <h3 class="section-title">选择或新建知识库</h3>
      <div class="section-tip">请选择已有知识库，或输入新名称新建。</div>
      <div style="margin-bottom: 16px;">
        <el-select v-model="selectedKnowledgeBase" placeholder="请选择或新建知识库" style="width: 350px;">
          <el-option v-for="item in knowledgeBaseOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
      </div>
      <!-- 上传文件区 -->
      <h3 class="section-title">上传知识文件</h3>
      <div class="section-tip">支持多种格式，单文件最大200MB，可拖拽或点击上传。</div>
      <el-upload
        ref="uploadRef"
        drag
        :action="'/api/knowledge/upload'"
        :auto-upload="false"
        :data="getUploadData"
        :on-success="handleUploadSuccess"
        :on-change="handleFileChange"
        :show-file-list="false"
        multiple
        style="width: 100%; max-width: 600px; margin-bottom: 16px;"
      >
        <i class="el-icon-upload"></i>
        <div class="el-upload__text">Drag and drop files here<br/>Limit 200MB per file • HTML, HTM, MHTML, ...</div>
        <el-button size="small" style="margin-top: 8px;">Browse files</el-button>
      </el-upload>
      <!-- 自定义文件列表 -->
      <div v-for="(file, idx) in fileList" :key="file.name" style="display: flex; align-items: center; margin: 4px 0;">
        <span style="margin-right: 8px;">{{ file.name }}</span>
        <el-icon v-if="file.status === 'loading'" style="color: #409EFF"><Loading /></el-icon>
        <el-icon v-else-if="file.status === 'success'" style="color: #67C23A"><CircleCheck /></el-icon>
        <el-icon v-else-if="file.status === 'error'" style="color: #F56C6C"><CircleClose /></el-icon>
        <el-button
          v-if="file.status === 'pending' || file.status === 'loading'"
          type="text"
          @click="removeFile(idx, file.status)"
          style="margin-left: 4px; color: #909399;"
          circle
          size="small"
        >
          <el-icon><Close /></el-icon>
        </el-button>
      </div>
      <!-- 简介输入框 -->
      <h3 class="section-title">知识库简介</h3>
      <div class="section-tip">可填写该知识库的用途、内容范围等。</div>
      <el-input type="textarea" rows="2" placeholder="请输入知识库简介" v-model="knowledgeBaseDesc" style="margin-bottom: 16px; max-width: 600px;" />
      <!-- 文本处理设置 -->
      <h3 class="section-title">文件处理设置</h3>
      <div class="section-tip">设置分段长度、重合长度等，影响知识入库效果。</div>
      <el-card style="margin-bottom: 0; border-radius: 10px; padding: 12px 20px; display: inline-block; min-width: 0; box-shadow: none; background: #fff;">
        <div class="file-setting-row">
          <span>单段文本最大长度：</span>
          <el-input-number v-model="maxTextLen" :min="50" :max="2000" :step="10" style="width:120px; margin-right:32px;" />
          <span>相邻文本重合长度：</span>
          <el-input-number v-model="overlapLen" :min="0" :max="500" :step="1" style="width:120px; margin-right:32px;" />
        </div>
      </el-card>
      <div style="margin: 16px 0 24px 0;">
        <el-button type="primary" @click="submitUpload">添加文件到知识库</el-button>
      </div>
      <!-- 文件列表表格 -->
      <h3 class="section-title">知识库文件列表</h3>
      <div class="section-tip">展示当前知识库下所有已上传文件，可进行批量操作。</div>
      <div style="margin-bottom: 24px;">
        <div style="margin-bottom: 8px;">知识库 <b>{{selectedKnowledgeBase}}</b> 中已有文件：</div>
        <el-table :data="fileList" border style="width: 100%; max-width: 900px;">
          <el-table-column prop="index" label="序号" width="60" />
          <el-table-column prop="name" label="文档名称" />
          <el-table-column prop="loader" label="文档加载器" />
          <el-table-column prop="category" label="分类" />
        </el-table>
        <div style="margin-top: 8px; text-align: right;">
          <el-pagination layout="prev, pager, next" :total="17" :page-size="10" small />
        </div>
        <div style="margin-top: 12px; display: flex; gap: 12px;">
          <el-button>下载选中文档</el-button>
          <el-button>重新添加至向量库</el-button>
          <el-button>从向量库删除</el-button>
          <el-button>从知识库中删除</el-button>
        </div>
      </div>
      <!-- 文档内容表格 -->
      <div style="margin-bottom: 12px; display: flex; gap: 12px;">
        <el-button type="primary">依源文件重建向量库</el-button>
        <el-button type="primary">删除知识库</el-button>
      </div>
      <h3 class="section-title">文档内容</h3>
      <div class="section-tip">可查看文档分段内容，支持编辑和删除。</div>
      <div style="margin-bottom: 24px;">
        <el-table :data="docContentList" border style="width: 100%; max-width: 900px;">
          <el-table-column prop="index" label="N" width="60" />
          <el-table-column prop="content" label="内容" />
        </el-table>
      </div>
      <el-button type="primary">保存更改</el-button>
    </div>
  </div>
</template>

<script setup>
import { ArrowLeft, Loading, CircleCheck, CircleClose, Close } from '@element-plus/icons-vue';
import { useRouter } from 'vue-router';
import { ref, watch, onMounted } from 'vue';
import { useChatModeStore } from '../store/chatMode';
import axios from 'axios'; // Added axios import
import { ElMessage } from 'element-plus'; // Added ElMessage import
import { ElMessageBox } from 'element-plus'; // 新增 ElMessageBox 导入

const router = useRouter();
const activeTab = ref('llm');
const chatModeStore = useChatModeStore();
const selectedPrompt = ref('default');
const temperature = ref(1.0); // 默认值1.0
const selectedKnowledgeBase = ref('samples');
const knowledgeBaseOptions = ref([
  { value: 'samples', label: 'samples' },
  { value: 'test', label: 'test' },
  { value: 'meian', label: 'meian' }
]);
const matchCount = ref(3); // 默认值改为3
const scoreThreshold = ref(1.0); // 默认值为1.0
const knowledgeBaseDesc = ref('关于test的知识库');
const maxTextLen = ref(50);
const overlapLen = ref(5);
// 恢复 fileList 的原始静态内容
const fileList = ref([]); // [{ name, status: 'loading'|'success'|'error' }]
const docContentList = ref([
  { index: 1, content: '中华人民共和国劳动法 第一章 总则 第一条 ...' },
  { index: 2, content: '第三章 国家采取各种措施，促进劳动就业 ...' }
]);
const searchKeyword = ref('');
const uploadRef = ref(null)

function goBack() {
  router.go(-1);
}

function formatTemperature(val) {
  return val.toFixed(2); // 显示两位小数
}

function formatScoreThreshold(val) {
  return val.toFixed(2); // 显示两位小数
}

const getPromptOptions = () => {
  return chatModeStore.chatMode === 'knowledge' 
    ? [
        { value: 'default', label: 'default' },
        { value: 'text', label: 'text' },
        { value: 'empty', label: 'empty' }
      ]
    : [
        { value: 'default', label: 'default' },
        { value: 'with_history', label: 'with_history' },
        { value: 'py', label: 'py' }
      ];
};

function getUploadData() {
  return {
    knowledge_base: selectedKnowledgeBase.value,
    chunk_size: maxTextLen.value,
    chunk_overlap: overlapLen.value
  }
}
function handleFileChange(file, fileListRaw) {
  // 优先保留已有 fileList 的 status，仅为新文件赋 pending
  fileList.value = fileListRaw.map(f => {
    const old = fileList.value.find(ff => ff.name === f.name);
    return old ? { ...old } : { name: f.name, status: 'pending' };
  });
}
function submitUpload() {
  // 所有 pending 文件设为 loading
  fileList.value.forEach(f => {
    if (f.status === 'pending') f.status = 'loading';
  });
  uploadRef.value && uploadRef.value.submit();
}
function handleUploadSuccess(res) {
  if (res.files) {
    const uploadedNames = res.files.map(f => f.filename);
    fileList.value.forEach(f => {
      if (uploadedNames.includes(f.name)) {
        f.status = 'loading';
      }
    });
  }
  // 调用重建向量库
  axios.post('/api/knowledge/rebuild_vector', {
    knowledge_base: selectedKnowledgeBase.value,
    chunk_size: maxTextLen.value,
    chunk_overlap: overlapLen.value
  }).then(() => {
    // 重建成功，所有 loading 文件状态设为 success
    fileList.value.forEach(f => {
      if (f.status === 'loading') f.status = 'success';
    });
    ElMessage.success('向量库重建成功！');
  }).catch(() => {
    // 重建失败，所有 loading 文件状态设为 error
    fileList.value.forEach(f => {
      if (f.status === 'loading') f.status = 'error';
    });
    ElMessage.error('向量库重建失败');
  });
}

function removePendingFile(idx) {
  // 移除 fileList 中的文件
  if (!fileList.value || idx < 0 || idx >= fileList.value.length) return;
  const removed = fileList.value.splice(idx, 1)[0];
  // 彻底同步 el-upload 的 fileList
  if (uploadRef.value) {
    uploadRef.value.clearFiles();
    fileList.value.forEach(f => {
      // 构造一个 File 对象模拟 el-upload 的文件
      const fakeFile = new File([new Blob()], f.name);
      uploadRef.value.handleStart(fakeFile);
    });
  }
}

// 新增 removeFile 方法
function removeFile(idx, status) {
  const file = fileList.value[idx];
  if (!file) return;
  if (status === 'pending') {
    removePendingFile(idx);
  } else if (status === 'loading') {
    ElMessageBox.confirm('文件正在上传或重建，确定要强制取消吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    }).then(() => {
      axios.post('/api/knowledge/cancel_upload', {
        knowledge_base: selectedKnowledgeBase.value,
        filename: file.name
      }).then(res => {
        if (res.data && res.data.code === 0) {
          // 彻底移除 fileList
          fileList.value = fileList.value.filter(f => f.name !== file.name);
          // 彻底同步 el-upload 的 fileList
          if (uploadRef.value) {
            uploadRef.value.clearFiles();
            fileList.value.forEach(f => {
              const fakeFile = new File([new Blob()], f.name);
              uploadRef.value.handleStart(fakeFile);
            });
          }
          ElMessage.success('已取消并清理后端文件');
        } else {
          ElMessage.error('后端取消失败: ' + (res.data && res.data.msg ? res.data.msg : '未知错误'));
        }
      }).catch(err => {
        ElMessage.error('后端取消失败: ' + (err && err.message ? err.message : '网络错误'));
      });
    });
  }
}

// 保存设置到localStorage
function saveSettings() {
  const settings = {
    activeTab: activeTab.value,
    chatMode: chatModeStore.chatMode,
    selectedPrompt: selectedPrompt.value,
    temperature: temperature.value,
    selectedKnowledgeBase: selectedKnowledgeBase.value,
    matchCount: matchCount.value,
    scoreThreshold: scoreThreshold.value
  };
  localStorage.setItem('coalchatSettings', JSON.stringify(settings));
}

// 读取设置
onMounted(() => {
  const saved = localStorage.getItem('coalchatSettings');
  if (saved) {
    const s = JSON.parse(saved);
    if (s.activeTab) activeTab.value = s.activeTab;
    if (s.chatMode) chatModeStore.setChatMode(s.chatMode);
    if (s.selectedPrompt) selectedPrompt.value = s.selectedPrompt;
    if (typeof s.temperature === 'number') temperature.value = s.temperature;
    if (s.selectedKnowledgeBase) selectedKnowledgeBase.value = s.selectedKnowledgeBase;
    if (typeof s.matchCount === 'number') matchCount.value = s.matchCount;
    if (typeof s.scoreThreshold === 'number') scoreThreshold.value = s.scoreThreshold;
  } else {
    // 没有保存时，设置默认值
    chatModeStore.setChatMode('llm');
  }
});

// 监听其它设置项变化，自动保存
watch([
  activeTab,
  selectedPrompt,
  temperature,
  selectedKnowledgeBase,
  matchCount,
  scoreThreshold
], saveSettings, { deep: true });
// 单独监听 chatModeStore.chatMode，确保切换时能保存
watch(() => chatModeStore.chatMode, saveSettings);
</script>

<style scoped>
.settings-container {
  padding: 20px;
  height: 100vh;
  overflow-y: auto;
}

.mode-tabs {
  display: flex;
  gap: 10px;
  margin: 20px 0;
}

.mode-tabs .el-button {
  font-size: 1.2em;
  font-weight: bold;
  padding: 10px 20px;
}

.sub-title {
  font-size: 1.5em;
  margin: 20px 0 10px 0; /* 调整上下边距 */
  color: #222831;
  font-weight: normal;
}

.mode-selector {
  margin: 0 0 20px 0;
}

.prompt-selector {
  width: 300px;
  margin-bottom: 30px;
}

.settings-header {
  display: flex;
  align-items: center;
  margin-bottom: 20px;
}

.back-btn {
  margin-right: 10px;
  padding: 0;
  height: auto;
}

.back-btn .el-icon {
  font-size: 24px;
}

.settings-title {
  margin: 0;
  font-size: 1.5em;
  line-height: 1.5;
}

/* 新增Temperature区域样式 */
.temperature-section {
  margin-bottom: 30px;
}

.temperature-header {
  display: flex;
  align-items: center;
  gap: 15px;
  margin-bottom: 10px;
}

.inline-title {
  margin: 0 !important;
  min-width: 120px;
}

.long-slider {
  width: 100%;
  max-width: 500px;
}

.temperature-input {
  width: 100px;
}

/* 新增滑块标签样式 */
.slider-with-labels {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  max-width: 500px;
}

.slider-label {
  font-size: 0.8em;
  color: #606266;
  min-width: 30px;
  text-align: center;
}

.long-slider {
  flex: 1;
}

.sub-sub-title {
  font-size: 1.2em;
  margin: 10px 0;
  color: #222831;
  font-weight: normal;
}

.knowledge-selector {
  width: 300px;
  margin-bottom: 20px;
}

.match-count-input {
  width: 300px; /* 加长宽度 */
  margin-bottom: 20px;
}

.score-threshold-section {
  margin-bottom: 20px;
}

.score-threshold-header {
  display: flex;
  align-items: center;
  gap: 15px;
  margin-bottom: 10px;
}

.score-threshold-input {
  width: 100px;
}

.knowledge-scroll-area {
  max-width: none;
  margin: 0;
}

.section-title {
  font-size: 1.1em;
  font-weight: bold;
  margin: 24px 0 4px 0;
  color: #2740b0;
}

.section-tip {
  font-size: 0.95em;
  color: #888;
  margin-bottom: 8px;
  margin-left: 2px;
}

.file-setting-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
</style>