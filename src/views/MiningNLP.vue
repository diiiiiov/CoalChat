<template>
  <div class="mining-nlp-container">
    <!-- 功能按钮组 -->
    <div class="function-buttons">
      <el-button
        class="classification-btn"
        :class="{ 'disabled-btn': isClassificationDisabled }"
        @click="handleClassification"
        :disabled="isClassificationDisabled"
      >
        <el-icon><Collection /></el-icon>
        <span>智能分类</span>
      </el-button>

      <el-button
        class="classification-btn"
        :class="{ 'disabled-btn': isJudgmentDisabled }"
        @click="handleJudgment"
        :disabled="isJudgmentDisabled"
      >
        <el-icon><DataAnalysis /></el-icon>
        <span>智能判别</span>
      </el-button>

      <el-button
        class="classification-btn"
        :class="{ 'disabled-btn': isExtractionDisabled }"
        @click="handleExtraction"
        :disabled="isExtractionDisabled"
      >
        <el-icon><Document /></el-icon>
        <span>关键信息提取</span>
      </el-button>

      <el-button
        class="classification-btn"
        :class="{ 'disabled-btn': isPredictionDisabled }"
        @click="handlePrediction"
        :disabled="isPredictionDisabled"
      >
        <el-icon><TrendCharts /></el-icon>
        <span>数值预测模型</span>
      </el-button>
    </div>

    <!-- 内容区域容器 -->
    <div class="content-container">
      <!-- 智能分类内容区 -->
      <div v-if="textbox1Visible || textbox2Visible || textbox3Visible || resultVisible" class="classification-content">
        <div class="input-group">
          <!-- 文本框1 -->
          <div class="textbox" v-if="textbox1Visible">
            <h2 class="textbox-title">指定类型</h2>
            <el-input v-model="text1" placeholder="请输入分类类型（如：合同纠纷、安全事故等）" type="textarea" :rows="10" />
          </div>

          <!-- 文本框2 -->
          <div class="textbox" v-if="textbox2Visible">
            <h2 class="textbox-title">业务背景</h2>
            <el-input v-model="text2" placeholder="请输入相关业务背景信息" type="textarea" :rows="10" />
          </div>
        </div>

        <div class="text-content-group">
          <!-- 文本框3 -->
          <div class="textbox" v-if="textbox3Visible">
            <h2 class="textbox-title">待分类文本</h2>
            <el-input v-model="text3" placeholder="请输入需要分类的文本内容" type="textarea" :rows="10" />
          </div>

          <!-- 分类结果展示区域 -->
          <div class="textbox result-textbox" v-if="resultVisible">
            <h2 class="textbox-title">分类结果</h2>
            <el-input
              v-model="classificationResult"
              placeholder="分类结果将显示在这里"
              type="textarea"
              :rows="10"
              readonly
            />
          </div>
        </div>

        <!-- 底部操作按钮 -->
        <div class="action-buttons">
          <el-button type="primary" @click="showExample">查看示例</el-button>
          <el-button type="success" @click="autoClassify">一键分类</el-button>
          <el-button class="clear-btn" @click="clearContent">清空内容</el-button>
        </div>
      </div>

      <!-- 智能判别内容区 -->
      <div v-if="judgmentBox1Visible || judgmentBox2Visible || judgmentBox3Visible" class="judgment-content">
        <div class="judgment-group">
          <!-- 判别文本框1 -->
          <div class="textbox" v-if="judgmentBox1Visible">
            <h2 class="textbox-title">原始语料</h2>
            <el-input v-model="judgmentText1" placeholder="请输入需要判别的原始文本" type="textarea" :rows="10" />
          </div>

          <!-- 判别文本框2 -->
          <div class="textbox" v-if="judgmentBox2Visible">
            <h2 class="textbox-title">判定标准</h2>
            <el-input v-model="judgmentText2" placeholder="请输入判别标准和依据" type="textarea" :rows="10" />
          </div>

          <!-- 判别文本框3 -->
          <div class="textbox" v-if="judgmentBox3Visible">
            <h2 class="textbox-title">判定结果</h2>
            <el-input v-model="judgmentText3" placeholder="判定结果将显示在这里" type="textarea" :rows="10" />
          </div>
        </div>

        <!-- 智能判别底部操作按钮 -->
        <div class="action-buttons">
          <el-button type="primary" @click="showJudgmentExample">查看示例</el-button>
          <el-button type="success" @click="autoJudgment">一键判别</el-button>
          <el-button class="clear-btn" @click="clearJudgmentContent">清空内容</el-button>
        </div>
      </div>

      <!-- 关键信息提取内容区 -->
      <div v-if="extractionBox1Visible || extractionBox2Visible || extractionBox3Visible" class="extraction-content">
        <div class="extraction-group">
          <!-- 提取文本框1 -->
          <div class="textbox large-textbox" v-if="extractionBox1Visible">
            <h2 class="textbox-title">原始语料</h2>
            <el-input v-model="extractionText1" placeholder="请输入需要提取信息的原始文本" type="textarea" :rows="10" />
          </div>

          <div class="extraction-result-group">
            <!-- 提取文本框2 -->
            <div class="textbox" v-if="extractionBox2Visible">
              <h2 class="textbox-title">抽取内容</h2>
              <el-input v-model="extractionText2" placeholder="请指定需要提取的内容类型" type="textarea" :rows="10" />
            </div>

            <!-- 提取文本框3 -->
            <div class="textbox" v-if="extractionBox3Visible">
              <h2 class="textbox-title">抽取结果</h2>
              <el-input v-model="extractionText3" placeholder="提取结果将显示在这里" type="textarea" :rows="10" />
            </div>
          </div>
        </div>

        <!-- 关键信息提取底部操作按钮 -->
        <div class="action-buttons">
          <el-button type="primary" @click="showExtractionExample">查看示例</el-button>
          <el-button type="success" @click="autoExtraction">一键提取</el-button>
          <el-button class="clear-btn" @click="clearExtractionContent">清空内容</el-button>
        </div>
      </div>

      <!-- 数值预测模型内容区 -->
      <div v-if="predictionBox1Visible || predictionBox2Visible" class="prediction-content">
        <div class="prediction-group">
          <!-- 预测文本框1 -->
          <div class="textbox" v-if="predictionBox1Visible">
            <h2 class="textbox-title">时序数据</h2>
            <el-input v-model="predictionText1" placeholder="请输入历史时序数据" type="textarea" :rows="10" />
          </div>

          <!-- 预测文本框2 -->
          <div class="textbox" v-if="predictionBox2Visible">
            <h2 class="textbox-title">预测结果</h2>
            <el-input v-model="predictionText2" placeholder="预测结果将显示在这里" type="textarea" :rows="10" />
          </div>
        </div>

        <!-- 数值预测模型底部操作按钮 -->
        <div class="action-buttons">
          <el-button type="primary" @click="showPredictionExample">查看示例</el-button>
          <el-button type="success" @click="autoPrediction">一键预测</el-button>
          <el-button class="clear-btn" @click="clearPredictionContent">清空内容</el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { Collection, DataAnalysis, Document, TrendCharts } from '@element-plus/icons-vue';
import { ref } from 'vue';
import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_NLP_API_URL || 'http://localhost:3000/api/nlp'
});

// 智能分类相关状态
const textbox1Visible = ref(false);
const textbox2Visible = ref(false);
const textbox3Visible = ref(false);
const resultVisible = ref(false);
const text1 = ref('');
const text2 = ref('');
const text3 = ref('');
const classificationResult = ref('');
const isClassificationDisabled = ref(false);
const isJudgmentDisabled = ref(false);
const isExtractionDisabled = ref(false);

// 智能判别相关状态
const judgmentBox1Visible = ref(false); // 原始语料文本框显示
const judgmentBox2Visible = ref(false); // 判定标准文本框显示
const judgmentBox3Visible = ref(false); // 判定结果文本框显示（统一变量名）
const judgmentText1 = ref(''); // 原始语料内容（正确对应）
const judgmentText2 = ref(''); // 判定标准内容
const judgmentText3 = ref(''); // 判定结果内容（与模板v-model对应）

// 关键信息提取相关状态
const extractionBox1Visible = ref(false);
const extractionBox2Visible = ref(false);
const extractionBox3Visible = ref(false);
const extractionText1 = ref('');
const extractionText2 = ref('');
const extractionText3 = ref('');

// 数值预测模型相关状态
const predictionBox1Visible = ref(false);
const predictionBox2Visible = ref(false);
const predictionText1 = ref('');
const predictionText2 = ref('');
const isPredictionDisabled = ref(false);

// 功能切换逻辑与之前一致...
const handleClassification = () => {
  textbox1Visible.value = true;
  textbox2Visible.value = true;
  textbox3Visible.value = true;
  resultVisible.value = true;

  judgmentBox1Visible.value = false;
  judgmentBox2Visible.value = false;
  judgmentBox3Visible.value = false;
  extractionBox1Visible.value = false;
  extractionBox2Visible.value = false;
  extractionBox3Visible.value = false;
  predictionBox1Visible.value = false;
  predictionBox2Visible.value = false;

  isClassificationDisabled.value = true;
  isJudgmentDisabled.value = false;
  isExtractionDisabled.value = false;
  isPredictionDisabled.value = false;
};

const handleJudgment = () => {
  judgmentBox1Visible.value = true;
  judgmentBox2Visible.value = true;
  judgmentBox3Visible.value = true;

  textbox1Visible.value = false;
  textbox2Visible.value = false;
  textbox3Visible.value = false;
  resultVisible.value = false;
  extractionBox1Visible.value = false;
  extractionBox2Visible.value = false;
  extractionBox3Visible.value = false;
  predictionBox1Visible.value = false;
  predictionBox2Visible.value = false;

  isClassificationDisabled.value = false;
  isJudgmentDisabled.value = true;
  isExtractionDisabled.value = false;
  isPredictionDisabled.value = false;
};

const handleExtraction = () => {
  extractionBox1Visible.value = true;
  extractionBox2Visible.value = true;
  extractionBox3Visible.value = true;

  textbox1Visible.value = false;
  textbox2Visible.value = false;
  textbox3Visible.value = false;
  resultVisible.value = false;
  judgmentBox1Visible.value = false;
  judgmentBox2Visible.value = false;
  judgmentBox3Visible.value = false;
  predictionBox1Visible.value = false;
  predictionBox2Visible.value = false;

  isClassificationDisabled.value = false;
  isJudgmentDisabled.value = false;
  isExtractionDisabled.value = true;
  isPredictionDisabled.value = false;
};

const handlePrediction = () => {
  predictionBox1Visible.value = true;
  predictionBox2Visible.value = true;

  textbox1Visible.value = false;
  textbox2Visible.value = false;
  textbox3Visible.value = false;
  resultVisible.value = false;
  judgmentBox1Visible.value = false;
  judgmentBox2Visible.value = false;
  judgmentBox3Visible.value = false;
  extractionBox1Visible.value = false;
  extractionBox2Visible.value = false;
  extractionBox3Visible.value = false;

  isClassificationDisabled.value = false;
  isJudgmentDisabled.value = false;
  isExtractionDisabled.value = false;
  isPredictionDisabled.value = true;
};


const showExample = () => {
  text1.value = "安全隐患类型：顶板隐患、瓦斯超标、机电故障";
  text2.value = "业务背景：煤矿井下采掘工作面安全检查，需根据现场记录判断隐患类型";
  text3.value = "2024-06-10 采掘工作面检查记录：工作面回风巷瓦斯浓度0.8%，未超标；2103工作面顶板出现局部裂隙，长度约30cm，深度5cm；运输机皮带跑偏，已停机处理。";
  classificationResult.value = "";
};


const showExtractionExample = () => {
  extractionText1.value = "2024-06-10 14:30 采掘工作面检查记录：2103工作面回风巷瓦斯浓度0.8%，未超标；顶板出现局部裂隙，长度约30cm，深度5cm；运输机皮带跑偏，已停机处理。";
  extractionText2.value = "需提取：时间、地点、隐患类型、隐患描述、处理状态";
  extractionText3.value = ""; // 清空示例结果，点击一键提取后生成
};

const showPredictionExample = () => {
  predictionText1.value = "2024-06-01 08:00\t0.5%\n2024-06-01 12:00\t0.6%\n2024-06-01 16:00\t0.55%\n2024-06-02 08:00\t0.7%\n2024-06-02 12:00\t0.8%";
  predictionText2.value = ""; // 清空示例结果，点击一键预测后生成
};

const autoClassify = async () => {
  try {
    const response = await api.post('/classify', {
      text1: text1.value,
      text2: text2.value,
      text3: text3.value
    });
    classificationResult.value = response.data.result;
  } catch (error) {
    alert('分类失败: ' + (error.response?.data?.message || error.message));
  }
};

const autoJudgment = async () => {
  try {
    const response = await api.post('/judge', {
      judgmentText1: judgmentText1.value,
      judgmentText2: judgmentText2.value
    });

    // 更新结构化结果
    judgmentText3.value = response.data.result;
    // 确保结果文本框可见（如果之前被隐藏）
    judgmentBox3Visible.value = true;
  } catch (error) {
    alert('判别失败: ' + (error.response?.data?.message || error.message));
  }
};

// 修改示例函数
const showJudgmentExample = () => {
  judgmentText1.value = "2024-06-10 检查记录：工作面顶板出现30cm裂隙，深度5cm，支护强度符合设计标准"; // 原始语料示例
  judgmentText2.value = "判定标准：顶板裂隙长度≥50cm或深度≥10cm为不符合；支护强度不符合设计标准为不符合；其余为符合";
  judgmentText3.value = ""; };// 清空结果

//   judgmentResultVisible.value = false; // 隐藏结果区域
// };

// 修改清空函数
const autoExtraction = async () => {
  try {
    // 验证输入
    if (!extractionText1.value) {
      alert('请输入需要提取信息的原始文本');
      return;
    }

    console.log('发送信息提取请求:', {
      extractionText1: extractionText1.value,
      extractionText2: extractionText2.value
    });

    // 调用后端提取接口
    const response = await api.post('/extract', {
      extractionText1: extractionText1.value,
      extractionText2: extractionText2.value
    });

    console.log('信息提取响应:', response.data);

    // 确保结果框可见
    extractionBox3Visible.value = true;

    // 处理提取结果
    if (response.data && response.data.success && response.data.result) {
      extractionText3.value = response.data.result;
    } else {
      throw new Error('提取结果格式不正确');
    }
  } catch (error) {
    console.error('提取失败:', error);
    alert('提取失败: ' + (error.response?.data?.message || error.message));
  }
};

// 修改 showExtractionExample 函数，使其与实际功能一致

async function autoPrediction() {
try {
// 验证输入
if (!predictionText1.value) {
alert('请输入历史时序数据');
return;
}

// 调用后端预测接口
const response = await api.post('/predict', {
predictionText1: predictionText1.value // 传递时序数据
});

// 赋值真实预测结果
predictionText2.value = response.data.result;
} catch (error) {
console.error('预测失败：', error);
alert('预测失败: ' + (error.response?.data?.message || error.message));
}
}

  const clearContent = () => {
    text1.value = '';
    text2.value = '';
    text3.value = '';
    classificationResult.value = '';
  };
  const clearJudgmentContent = () => {
    judgmentText1.value = ''; // 清空原始语料
    judgmentText2.value = '';
    judgmentText3.value = '';
  };

  const clearExtractionContent = () => {
    extractionText1.value = '';
    extractionText2.value = '';
    extractionText3.value = '';
  };

  const clearPredictionContent = () => {
    predictionText1.value = '';
    predictionText2.value = '';
  };
</script>

<style scoped>
.mining-nlp-container {
  position: relative;
  min-height: 100vh;
  padding: 20px;
  box-sizing: border-box;
  background-color: #f5f5f5;
}

/* 功能按钮组样式 */
.function-buttons {
  display: flex;
  gap: 20px;
  margin-bottom: 30px;
  padding: 15px;
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
  margin-top: 50px;
}

.classification-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  width: 140px;
  height: 40px;
  font-size: 14px;
  background-color: #2740b0;
  border-color: #2740b0;
  color: white;
  transition: all 0.3s ease;
}

.classification-btn:hover {
  background-color: #3850c8;
  border-color: #3850c8;
  color: white;
}

.classification-btn:active {
  background-color: #1e3391;
  border-color: #1e3391;
}

.disabled-btn {
  background-color: #e5e7eb !important;
  border-color: #e5e7eb !important;
  color: #9ca3af !important;
  cursor: not-allowed;
}

/* 内容容器样式 */
.content-container {
  width: 100%;
  box-sizing: border-box;
}

/* 通用文本框样式 */
.textbox {
  background: white;
  padding: 15px;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
  display: flex;
  flex-direction: column;
}

.textbox-title {
  margin: 0 0 12px 0;
  font-size: 16px;
  color: #1f2329;
  font-weight: 500;
  padding-bottom: 8px;
  border-bottom: 1px solid #f0f0f0;
}

.textbox .el-textarea__inner {
  height: 280px;
  min-height: 280px;
  resize: none;
  border-radius: 4px;
  font-size: 14px;
  line-height: 1.5;
}

/* 智能分类布局 */
.classification-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.input-group {
  display: flex;
  gap: 20px;
}

.input-group .textbox {
  flex: 1;
}

.text-content-group {
  display: flex;
  gap: 20px;
}

.text-content-group .textbox {
  flex: 1;
}

.result-textbox {
  border: 1px solid #e6f7ff;
  background-color: #f0faff;
}

.result-textbox .el-textarea__inner {
  background-color: rgba(255, 255, 255, 0.8);
}

/* 智能判别布局 */
.judgment-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.judgment-group {
  display: flex;
  gap: 20px;
}

.judgment-group .textbox {
  flex: 1;
}

/* 关键信息提取布局 */
.extraction-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.extraction-group {
  display: flex;
  gap: 20px;
}

.large-textbox {
  flex: 2;
}

.extraction-result-group {
  display: flex;
  flex: 1;
  gap: 20px;
}

.extraction-result-group .textbox {
  flex: 1;
}

/* 数值预测布局 */
.prediction-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.prediction-group {
  display: flex;
  gap: 20px;
}

.prediction-group .textbox {
  flex: 1;
}

.el-button {
  /* 每个按钮右边和下边留间距，根据需求调整数值 */
  margin-right: 10px;
  margin-bottom: 10px;
}

/* 操作按钮样式 */
.action-buttons {
  display: flex;
  justify-content: center;
  gap: 15px;
  margin-top: 20px;
  padding: 10px;
  position: static;
}

.clear-btn {
  background-color: white !important;
  border-color: #dcdfe6 !important;
  color: #606266 !important;
}

.clear-btn:hover {
  background-color: #f5f7fa !important;
  border-color: #c0c4cc !important;
}

/* 响应式调整 */
@media (max-width: 1200px) {
  .input-group,
  .text-content-group,
  .judgment-group,
  .extraction-group,
  .prediction-group,
  .extraction-result-group {
    flex-direction: column;
  }
}</style>