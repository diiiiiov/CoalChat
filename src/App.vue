<template>
  <div class="app-container">
    <aside class="sidebar" v-if="sidebarVisible && $route.meta.showSidebar !== false">
      <div class="logo clickable" @click="goHome">CoalChat</div>
      <el-button type="primary" class="new-session-btn" @click="onNewSession">新建会话</el-button>
      <el-button type="primary" class="favorites-btn" @click="openFavorites">
        <el-icon><Star /></el-icon>
        <span>我的收藏</span>
      </el-button>
      <div class="history-header">
        <div class="history-title">历史会话</div>
        <el-button
          type="danger"
          size="small"
          @click="deleteAllSessions"
          :disabled="sessions.length === 0"
          :icon="Delete"
          circle
          style="color: #F56C6C; font-size: 1em; width: 24px; height: 24px;"
        />
      </div>
      <el-menu :default-active="String(currentSessionId)" class="history-list" @select="selectSession">
        <el-menu-item 
          v-for="session in sessions" 
          :key="session.id" 
          :index="String(session.id)"
          class="session-item"
        >
          <span class="session-name">{{ session.name }}</span>
          <el-dropdown trigger="click" @command="handleSessionCommand">
            <span class="el-dropdown-link">
              <el-icon><MoreFilled /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item :command="{ action: 'pin', id: session.id }">
                  <el-icon class="pin-icon">
                    <svg viewBox="0 0 24 24" width="1em" height="1em">
                      <path 
                        fill="none" 
                        stroke="currentColor" 
                        stroke-width="2.5" 
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        d="M12 4v16M5 10l7-7 7 7"
                      />
                    </svg>
                  </el-icon>
                  <span>置顶</span>
                </el-dropdown-item>
                <el-dropdown-item :command="{ action: 'rename', id: session.id }">
                  <el-icon class="rename-icon"><EditPen /></el-icon>
                  <span>重命名</span>
                </el-dropdown-item>
                <el-dropdown-item 
                  :command="{ action: 'delete', id: session.id }" 
                  class="delete-item"
                >
                  <el-icon style="color: #F56C6C"><Delete /></el-icon>
                  <span style="color: #F56C6C">删除</span>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </el-menu-item>
      </el-menu>
      <div class="settings-option">
        <el-button type="text" class="settings-btn" @click="openSettings">
          <el-icon><Setting /></el-icon>
          <span>设置</span>
        </el-button>
      </div>
      <button class="sidebar-hide-btn" @click="toggleSidebar">
        <svg width="24" height="64" viewBox="0 0 24 64" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect x="0.5" y="0.5" width="23" height="63" rx="12" fill="#fff" stroke="#F0F1F2"/>
          <path d="M16 32H8M8 32L12 28M8 32L12 36" stroke="#222831" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </button>
    </aside>
    <div class="main" :class="{ 'fullscreen': $route.meta.fullscreen }">
      <div class="main-function-buttons" v-if="showFunctionButtons">
        <el-button type="primary" class="main-function-btn" @click="openAIChat">
          <el-icon><ChatLineRound /></el-icon>
          <span>大模型问答</span>
        </el-button>
        <el-button type="primary" class="main-function-btn" @click="openMiningNLP">
          <el-icon><DataAnalysis /></el-icon>
          <span>煤矿NLP任务</span>
        </el-button>
      </div>
      <button
        v-if="!sidebarVisible"
        class="sidebar-show-btn"
        @click="toggleSidebar"
      >
        <svg width="24" height="64" viewBox="0 0 24 64" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect x="0.5" y="0.5" width="23" height="63" rx="12" fill="#fff" stroke="#F0F1F2"/>
          <path d="M8 32H16M16 32L12 28M16 32L12 36" stroke="#222831" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </button>
      <section class="content">
        <div
          class="chat-container"
          :class="{ 'centered': !showChat }"
          v-if="!$route.meta.hideChat"
        >
          <div class="welcome-section" v-if="!showChat">
            <h1 class="welcome-message">欢迎使用CoalChat</h1>
            <p class="welcome-subtext">这是专为您设计的煤矿安全规范问答系统，可对话获取相关知识解答。</p>
            <p class="welcome-subtext">请在下方输入框中输入您的问题，系统会尽力为您提供帮助。</p>
          </div>
          <div class="chat-messages">
            <template v-if="showChat">
              <div
                v-for="(msg, idx) in currentMessages"
                :key="idx"
                :class="['chat-message', msg.role]"
              >
                <div class="avatar">
                  <span v-if="msg.role === 'user'">🧑</span>
                  <span v-else>🤖</span>
                </div>
                <div class="bubble">
                  <div class="message-text">
                    <template v-for="(part, partIndex) in splitCitationParts(msg.text)" :key="partIndex">
                      <button
                        v-if="part.citationId"
                        class="inline-citation"
                        type="button"
                        @click="openEvidence(msg, part.citationId)"
                      >{{ part.text }}</button>
                      <span v-else>{{ part.text }}</span>
                    </template>
                  </div>
                  <div v-if="msg.sources?.length" class="source-list">
                    <button
                      v-for="source in msg.sources"
                      :key="source.id"
                      class="source-chip"
                      type="button"
                      @click="openEvidence(msg, source.id)"
                    >{{ source.label }} {{ source.source }}</button>
                  </div>
                  <div class="action-buttons" v-if="msg.role === 'ai'">
                    <el-button type="link" @click="copyMessage(msg.text)" class="action-btn">
                      <div class="action-content">
                        <span class="action-text">复制</span>
                        <el-icon><DocumentCopy /></el-icon>
                      </div>
                    </el-button>
                    <el-button 
                      type="text" 
                      @click="favoriteMessage(msg.text)" 
                      class="action-btn" 
                      style="margin-left: 8px;"
                    >
                      <div class="action-content">
                        <span class="action-text">{{ favoriteStatus[msg.text] ? '取消收藏' : '收藏' }}</span>
                        <el-icon :color="getStarColor(msg.text)">
                          <Star />
                        </el-icon>
                      </div>
                    </el-button>
                    <el-button type="text" @click="likeMessage(msg.text)" class="action-btn" style="margin-left: 8px;">
                      <div class="action-content">
                        <span class="action-text">点赞</span>
                        <el-icon><svg viewBox="0 0 24 24" width="1em" height="1em"><path fill="currentColor" d="M5 9v12H1V9h4m4 12a2 2 0 0 1-2-2V9c0-.55.22-1.05.59-1.41L14.17 1l1.06 1.06c.27.27.44.64.44 1.05l-.03.32L14.69 8H21a2 2 0 0 1 2 2v2c0 .26-.05.5-.14.73l-3.02 7.05C19.54 20.5 18.83 21 18 21H9m0-2h9.03L21 12v-2h-8.69l1.13-5.32L9 9.03V19z"/></svg></el-icon>
                      </div>
                    </el-button>
                    <el-button type="text" @click="dislikeMessage(msg.text)" class="action-btn" style="margin-left: 8px;">
                      <div class="action-content">
                        <span class="action-text">点踩</span>
                        <el-icon><svg viewBox="0 0 24 24" width="1em" height="1em" style="transform: rotate(180deg) scaleX(-1);"><path fill="currentColor" d="M5 9v12H1V9h4m4 12a2 2 0 0 1-2-2V9c0-.55.22-1.05.59-1.41L14.17 1l1.06 1.06c.27.27.44.64.44 1.05l-.03.32L14.69 8H21a2 2 0 0 1 2 2v2c0 .26-.05.5-.14.73l-3.02 7.05C19.54 20.5 18.83 21 18 21H9m0-2h9.03L21 12v-2h-8.69l1.13-5.32L9 9.03V19z"/></svg></el-icon>
                      </div>
                    </el-button>
                    <el-button type="text" @click="regenerateMessage(msg.text)" class="action-btn" style="margin-left: 8px;">
                      <div class="action-content">
                        <span class="action-text">重新生成</span>
                        <el-icon><svg viewBox="0 0 24 24" width="1em" height="1em"><path fill="currentColor" d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z"/></svg></el-icon>
                      </div>
                    </el-button>
                    <el-button type="text" @click="shareMessage(msg.text)" class="action-btn" style="margin-left: 8px;">
                      <div class="action-content">
                        <span class="action-text">分享</span>
                        <el-icon><svg viewBox="0 0 24 24" width="1em" height="1em"><path fill="currentColor" d="M18 16.08c-.76 0-1.44.3-1.96.77L8.91 12.7c.05-.23.09-.46.09-.7s-.04-.47-.09-.7l7.05-4.11c.54.5 1.25.81 2.04.81 1.66 0 3-1.34 3-3s-1.34-3-3-3-3 1.34-3 3c0 .24.04.47.09.7L8.04 9.81C7.5 9.31 6.79 9 6 9c-1.66 0-3 1.34-3 3s1.34 3 3 3c.79 0 1.5-.31 2.04-.81l7.12 4.16c-.05.21-.08.43-.08.65 0 1.61 1.31 2.92 2.92 2.92 1.61 0 2.92-1.31 2.92-2.92s-1.31-2.92-2.92-2.92z"/></svg></el-icon>
                      </div>
                    </el-button>
                  </div>
                </div>
              </div>
            </template>
          </div>
          <div
            class="chat-input-row"
            :class="{ 'fixed-bottom': showChat }"
          >
            <el-input
              v-model="inputMsg"
              type="textarea"
              :autosize="{ minRows: 3, maxRows: 6 }"
              :placeholder="showChat ? '请输入您的煤矿安全问题...' : '请输入对话内容，例如：如何观测新凿立井涌水量？'"
              @keyup.enter="sendMsg"
              class="chat-input"
            />
            <el-button @click="sendMsg" class="send-button">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle cx="12" cy="12" r="10" fill="#409EFF" />
                <path d="M12 8L16 12L12 16" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </el-button>
          </div>
        </div>
      </section>
      <router-view v-if="$route.meta.fullscreen"></router-view>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import 'element-plus/dist/index.css'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Close, MoreFilled, EditPen, Setting, DocumentCopy, Star, ChatLineRound, DataAnalysis } from '@element-plus/icons-vue'
import { ElDropdown, ElDropdownMenu, ElDropdownItem } from 'element-plus'
import { useRouter } from 'vue-router'
import axios from 'axios'
import { useChatModeStore } from './store/chatMode';

const llmApi = axios.create({
  baseURL: import.meta.env.VITE_LLM_API_URL || 'http://localhost:3000/api/llm'
})
const knowledgeApi = axios.create({
  baseURL: import.meta.env.VITE_KNOWLEDGE_API_URL || 'http://localhost:8000/api/knowledge'
})
const knowledgeApiBase = import.meta.env.VITE_KNOWLEDGE_API_URL || 'http://localhost:8000/api/knowledge'

const activeMenu = ref('1')
const sidebarVisible = ref(true)
const showChat = ref(false)
const inputMsg = ref('')
const favoriteStatus = ref({})
const chatModeStore = useChatModeStore();

let sessionId = 1
const sessions = ref([
  { id: sessionId, name: '新对话', messages: [] }
])
const currentSessionId = ref(sessionId)

const currentMessages = computed(() => {
  const session = sessions.value.find(s => s.id === currentSessionId.value)
  return session ? session.messages : []
})

const router = useRouter()

onMounted(() => {
  // 自动同步chatMode，确保与设置页一致
  const saved = localStorage.getItem('coalchatSettings');
  if (saved) {
    const s = JSON.parse(saved);
    if (s.chatMode) chatModeStore.setChatMode(s.chatMode);
  }
  const favorites = JSON.parse(localStorage.getItem('aiFavorites') || '[]');
  favorites.forEach(fav => {
    favoriteStatus.value[fav.text] = true;
  });
});

function toggleSidebar() {
  sidebarVisible.value = !sidebarVisible.value
  console.log('侧边栏状态:', sidebarVisible.value)
}

function onNewSession() {
  sessionId++
  const newSession = { id: sessionId, name: '新对话', messages: [] }
  sessions.value.unshift(newSession)
  currentSessionId.value = newSession.id
  showChat.value = true
  inputMsg.value = ''
}

function selectSession(id) {
  currentSessionId.value = Number(id)
  showChat.value = true
  inputMsg.value = ''
}

async function sendMsg() {
  if (!inputMsg.value.trim()) return
  if (!showChat.value) {
    showChat.value = true
  }
  const session = sessions.value.find(s => s.id === currentSessionId.value)
  if (!session) return

  // 更新会话名称（如果当前名称为"新对话"）
  if (session.name === '新对话') {
    session.name = inputMsg.value.trim().slice(0, 20) + (inputMsg.value.trim().length > 20 ? '...' : '')
  }

  // 先push用户消息
  session.messages.push({ role: 'user', text: inputMsg.value })
  // 记录本次用户消息
  const lastUserMsg = inputMsg.value
  inputMsg.value = ''   // 立刻清空输入框

  console.log('当前chatMode:', chatModeStore.chatMode) // 调试用

  if (chatModeStore.chatMode === 'llm') {
    // LLM对话，向后端发送请求
    try {
      // 构造历史消息
      const history = session.messages
        .filter(m => m.role === 'user' || m.role === 'ai')
        .map(m => ({
          role: m.role === 'user' ? 'user' : 'assistant',
          content: m.text
        }))
      const historyForSend = history.slice(-20)
      let payload = {}
      if (historyForSend.length <= 1) {
        payload.message = lastUserMsg // 用刚才的用户消息
      } else {
        payload.messages = historyForSend
      }
      const res = await llmApi.post('/chat', payload)
      session.messages.push({ role: 'ai', text: res.data.result })
    } catch (e) {
      session.messages.push({ role: 'ai', text: 'AI回复失败，请稍后重试' })
    }
  } else if (chatModeStore.chatMode === 'knowledge') {
    try {
      // 构造历史消息
      const history = session.messages
        .filter(m => m.role === 'user' || m.role === 'ai')
        .map(m => ({
          role: m.role === 'user' ? 'user' : 'assistant',
          content: m.text
        }))
      const historyForSend = history.slice(-20)

      // 构造知识库问答 payload
      const payload = {
        query: lastUserMsg,
        knowledge_base_name: 'samples', // 可根据实际需求调整
        top_k: 3,
        score_threshold: 0.3,
        history: historyForSend,
        temperature: 0.2
      }

      const answerMessage = { role: 'ai', text: '', sources: [], requestId: '' }
      session.messages.push(answerMessage)
      await streamKnowledgeAnswer(payload, (event, data) => {
        if (event === 'sources') {
          answerMessage.sources = data.sources || []
          answerMessage.requestId = data.request_id || ''
        } else if (event === 'token') {
          answerMessage.text += data.text || ''
        } else if (event === 'done') {
          // 后端会在完成事件中校验并规范化引用编号。
          answerMessage.text = data.answer || answerMessage.text
          answerMessage.requestId = data.request_id || answerMessage.requestId
        } else if (event === 'error') {
          throw new Error(data.message || '流式问答失败')
        }
      })
      if (!answerMessage.text) answerMessage.text = '知识库AI未返回答案'
    } catch (e) {
      session.messages.push({ role: 'ai', text: '知识库AI回复失败，请稍后重试' })
    }
  } else {
    // 其他模式（如NLP），原有逻辑
  setTimeout(() => {
      session.messages.push({ role: 'ai', text: 'AI回复: 未接入模型' + lastUserMsg })
  }, 500)
  }
}

async function streamKnowledgeAnswer(payload, onEvent) {
  const response = await fetch(`${knowledgeApiBase}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  if (!response.ok || !response.body) {
    throw new Error(`知识库服务请求失败（${response.status}）`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done }).replace(/\r\n/g, '\n')
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() || ''
    for (const block of blocks) {
      let eventName = 'message'
      const dataLines = []
      for (const line of block.split('\n')) {
        if (line.startsWith('event:')) eventName = line.slice(6).trim()
        if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
      }
      if (dataLines.length) onEvent(eventName, JSON.parse(dataLines.join('\n')))
    }
    if (done) break
  }
}

function splitCitationParts(text = '') {
  const parts = []
  const pattern = /\[#(\d+)\]/g
  let cursor = 0
  let match
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > cursor) parts.push({ text: text.slice(cursor, match.index) })
    parts.push({ text: match[0], citationId: Number(match[1]) })
    cursor = pattern.lastIndex
  }
  if (cursor < text.length) parts.push({ text: text.slice(cursor) })
  return parts
}

async function openEvidence(message, citationId) {
  if (!message.requestId) {
    ElMessage.warning('该引用暂无可回查的证据')
    return
  }
  try {
    const response = await knowledgeApi.get(`/evidence/${message.requestId}/${citationId}`)
    const evidence = response.data
    await ElMessageBox.alert(
      `${evidence.content}\n\n来源：${evidence.source}\n片段编号：${evidence.chunk_id}`,
      `证据 ${evidence.label}`,
      { confirmButtonText: '关闭' }
    )
  } catch (error) {
    ElMessage.error('证据不存在或已过期')
  }
}

function goHome() {
  showChat.value = false
}

function deleteAllSessions() {
  ElMessageBox.confirm(
    '所有会话将被永久删除，不可恢复及撤销',
    '删除全部确认',
    {
      confirmButtonText: '确认删除',
      cancelButtonText: '取消',
      type: 'warning',
      confirmButtonClass: 'confirm-delete-btn',
      cancelButtonClass: 'cancel-delete-btn'
    }
  ).then(() => {
    sessions.value = []
    currentSessionId.value = null
    showChat.value = false
    inputMsg.value = ''
    ElMessage.success('所有会话已删除')
  }).catch(() => {})
}

function deleteSession(id) {
  sessions.value = sessions.value.filter(s => s.id !== id)
  if (currentSessionId.value === id) {
    currentSessionId.value = sessions.value[0]?.id || null
    showChat.value = !!sessions.value.length
  }
  ElMessage.success('会话已删除')
}

function handleSessionCommand(command) {
  const { action, id } = command;
  switch (action) {
    case 'pin':
      pinSession(id);
      break;
    case 'rename':
      renameSession(id);
      break;
    case 'delete':
      ElMessageBox.confirm(
        '这条会话将被永久删除，不可恢复及撤销',
        '删除确认',
        {
          confirmButtonText: '删除',
          cancelButtonText: '取消',
          type: 'warning',
          confirmButtonClass: 'confirm-delete-btn',
          cancelButtonClass: 'cancel-delete-btn'
        }
      ).then(() => {
        deleteSession(id);
      }).catch(() => {});
      break;
  }
}

function pinSession(id) {
  const session = sessions.value.find(s => s.id === id)
  if (session) {
    sessions.value = sessions.value.filter(s => s.id !== id)
    sessions.value.unshift(session)
    ElMessage.success('会话已置顶')
  }
}

function renameSession(id) {
  const session = sessions.value.find(s => s.id === id)
  if (session) {
    const newName = prompt('请输入新的会话名称', session.name)
    if (newName && newName.trim()) {
      session.name = newName.trim()
      ElMessage.success('会话名称已更新')
    }
  }
}

function openSettings() {
  router.push('/settings')
}

function copyMessage(text) {
  navigator.clipboard.writeText(text)
    .then(() => {
      ElMessage.success('已复制到剪贴板');
    })
    .catch(() => {
      ElMessage.error('复制失败');
    });
}

function favoriteMessage(text) {
  const favorites = JSON.parse(localStorage.getItem('aiFavorites') || '[]');
  const isFavorited = favorites.some(fav => fav.text === text);
  favoriteStatus.value[text] = !isFavorited;

  if (isFavorited) {
    const updatedFavorites = favorites.filter(fav => fav.text !== text);
    localStorage.setItem('aiFavorites', JSON.stringify(updatedFavorites));
    ElMessage.success('已取消收藏');
  } else {
    favorites.push({ text, timestamp: new Date().getTime() });
    localStorage.setItem('aiFavorites', JSON.stringify(favorites));
    ElMessage.success('已收藏消息');
  }
}

function likeMessage(text) {
  ElMessage.success('已点赞消息');
  // 这里可以添加实际的点赞逻辑
}

function dislikeMessage(text) {
  ElMessage.success('已点踩消息');
  // 这里可以添加实际的点踩逻辑
}

function regenerateMessage(text) {
  // 这里可以添加实际的重新生成逻辑
}

function shareMessage(text) {
  // 这里可以添加实际的分享逻辑
}

function openFavorites() {
  router.push('/favorites');
}

function openAIChat() {
  router.push('/');
}

function openMiningNLP() {
  router.push('/mining-nlp');
}

const getStarColor = (text) => {
  return favoriteStatus.value[text] ? '#FFD700' : '#606266';
};

const showFunctionButtons = computed(() => {
  return !showChat.value && router.currentRoute.value.path !== '/settings';
});
</script>

<style scoped>
.app-container {
  display: flex;
  height: 100vh;
  background: #f5f6fa;
  position: relative;
}
.sidebar {
  width: 15%;
  background: #F3F3F3;
  color: #222831;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding-top: 24px;
  position: relative;
  border-right: 1px solid #e0e0e0;
  box-shadow: 2px 0 8px rgba(0, 0, 0, 0.05);
  overflow: visible;
  z-index: 1000;
  flex-shrink: 0;
}
.logo {
  font-size: 28px;
  font-weight: bold;
  margin-bottom: 32px;
  letter-spacing: 2px;
}
.main {
  flex: 1;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: visible;
}
.content {
  flex: 1;
  padding: 0 !important;
  margin: 0 !important;
  background: #fcfcfc;
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}
.sidebar .new-session-btn.el-button {
  width: 80%;
  margin: 0 auto 16px;
  flex-shrink: 0;
  background-color: #ffffff !important;
  border-color: #ffffff !important;
  color: #000000 !important;
  height: 40px !important;
  line-height: 40px !important;
}
.sidebar .favorites-btn.el-button {
  width: 90%;
  margin: 0 auto 16px;
  flex-shrink: 0;
  background-color: #e9e9e9 !important;
  border-color: #e9e9e9 !important;
  color: #000000 !important;
  height: 40px !important;
  line-height: 40px !important;
}
.chat-container {
  display: flex;
  flex-direction: column;
  width: 80%;
  max-width: 900px;
  min-width: 320px;
  margin: 0 auto;
  background: transparent;
  position: relative;
  justify-content: center;
  align-items: center;
  height: 100%;
}
.chat-messages {
  flex: 1 1 auto;
  overflow-y: auto;
  margin-bottom: 0;
  max-height: none;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding-bottom: 88px;
  width: 100%;
  max-width: 900px;
  margin: 0 auto;
}
.chat-message {
  display: flex;
  align-items: flex-start;
}
.chat-message.user {
  flex-direction: row-reverse;
}
.chat-message .avatar {
  width: 36px;
  height: 36px;
  border-radius: 95%;
  background: #f0f1f2;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  margin: 0 8px;
}
.chat-message .bubble {
  position: relative;
  padding-bottom: 30px;
  max-width: 80%;
  padding: 12px 16px;
  border-radius: 16px;
  box-shadow: 0 2px 8px #e0e0e0;
  font-size: 15px;
  line-height: 1.6;
  word-break: break-word;
}
.chat-message.user .bubble {
  background: #e6f0ff;
  color: #222;
  border-bottom-right-radius: 4px;
  border-bottom-left-radius: 16px;
  border-top-right-radius: 16px;
  border-top-left-radius: 16px;
}
.chat-message.ai .bubble {
  background: #fff;
  color: #222;
  border-bottom-left-radius: 4px;
  border-bottom-right-radius: 16px;
  border-top-right-radius: 16px;
  border-top-left-radius: 16px;
}
.message-text {
  white-space: pre-wrap;
}
.inline-citation {
  margin: 0 2px;
  padding: 0;
  border: 0;
  background: transparent;
  color: #1677ff;
  cursor: pointer;
  font: inherit;
  font-weight: 600;
}
.inline-citation:hover {
  text-decoration: underline;
}
.source-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid #ebeef5;
}
.source-chip {
  max-width: 260px;
  overflow: hidden;
  padding: 4px 8px;
  border: 1px solid #d9ecff;
  border-radius: 12px;
  background: #ecf5ff;
  color: #337ecc;
  cursor: pointer;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.source-chip:hover {
  border-color: #409eff;
}
.chat-input-row {
  margin: 0 auto;
  width: 100%;
  max-width: 900px;
  display: flex;
  align-items: flex-end;
  background: #fff;
  border-radius: 24px;
  box-shadow: 0 4px 24px 0 rgba(0,0,0,0.06);
  padding: 12px 16px;
  z-index: 2;
  position: static;
}
.chat-input-row.fixed-bottom {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
}
.chat-input :deep(.el-textarea__inner) {
  border: none !important;
  box-shadow: none !important;
  background: transparent !important;
  border-radius: 20px !important;
  padding: 8px 0 8px 8px !important;
  font-size: 16px;
  resize: none !important;
  min-height: 32px;
  line-height: 1.6;
  color: #222;
}
.chat-input :deep(.el-textarea) {
  background: transparent !important;
}
.chat-input {
  flex: 1;
  margin-right: 8px;
  text-align: left;
}
.chat-input :deep(input) {
  background: transparent;
  border: none;
  outline: none;
  font-size: 16px;
}
.el-button {
  background-color: transparent !important;
  border: none !important;
  color: inherit !important;
  box-shadow: none !important;
}
.history-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  padding: 0 20px 0 0;
  margin: 8px 0 16px 0;
}
.history-title {
  color: #aaa;
  font-size: 14px;
  margin: 0;
  padding-left: 16px;
}
.history-list {
  width: 100%;
  flex: 1;
  overflow-y: auto;
  margin-bottom: 16px;
  background: transparent;
  border-right: none;
  max-height: calc(100vh - 200px);
}
.content-header {
  display: flex;
  align-items: center;
  margin-bottom: 24px;
}
.content-logo {
  font-size: 20px;
  font-weight: bold;
  color: #222831;
}
.sidebar-hide-btn {
  position: absolute;
  right: -12px;
  top: 50%;
  transform: translateY(-50%);
  background: #fff;
  border: none;
  padding: 0;
  cursor: pointer;
  z-index: 20;
  box-shadow: none;
  border-radius: 12px;
  outline: none;
  width: 24px;
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.sidebar-hide-btn svg {
  display: block;
  width: 24px;
  height: 64px;
}
.sidebar-show-btn {
  position: fixed;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  z-index: 20;
  box-shadow: 0 2px 8px #f0f1f2;
  border-radius: 12px;
  outline: none;
}
.sidebar-show-btn svg {
  display: block;
}
.content {
  flex: 1;
  padding: 32px;
  background: #f8f9fa;
  display: flex;
  align-items: center;
  justify-content: center;
}
.chat-container.centered {
  margin: 0;
  height: auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  position: static;
}
.logo.clickable {
  cursor: pointer;
  transition: color 0.2s;
}
.logo.clickable:hover {
  color: #409eff; /* Element Plus 主色调高亮 */
}
.send-button {
  background: none !important;
  border: none !important;
  padding: 0 !important;
  min-width: 64px !important;
  height: 64px !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  cursor: pointer !important;
  margin-left: auto;
  margin-bottom: 0 !important;
}
.send-button svg {
  width: 40px !important;
  height: 40px !important;
  transition: transform 0.2s;
}
.send-button:hover svg {
  transform: scale(1.1);
}
.session-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-right: 8px !important;
}
.session-name {
  flex: 1;
}
.el-dropdown-link {
  cursor: pointer;
  padding: 5px;
  opacity: 0;
  transition: opacity 0.2s;
}
.session-item:hover .el-dropdown-link {
  opacity: 1;
}
.el-dropdown-menu__item .el-icon {
  margin-right: 8px;
}
.rename-icon {
  transform: rotate(-15deg);
  margin-right: 8px;
  color: #606266 !important;
  transition: transform 0.2s;
}
.el-dropdown-menu__item:hover .rename-icon {
  transform: rotate(-15deg) scale(1.1);
}
.pin-icon {
  margin-right: 8px;
  color: #606266;
  width: 1em;
  height: 1em;
}
.pin-icon svg {
  display: block;
}
.delete-item {
  color: #F56C6C !important;
}
.delete-item:hover {
  background-color: #FEF0F0 !important;
}
/* 删除确认弹窗按钮样式 */
.confirm-delete-btn {
  background-color: #F56C6C !important;
  border-color: #F56C6C !important;
}
.cancel-delete-btn {
  color: #606266 !important;
}
:deep(.el-button--danger) {
  color: #F56C6C !important;
}
.settings-option {
  width: calc(100% - 32px);
  padding: 12px 16px;
  margin: 0 auto;
  border-top: 1px solid #e0e0e0;
}
.settings-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #606266;
}
.settings-btn:hover {
  color: #409EFF;
}
.settings-btn .el-icon {
  margin-right: 8px;
}
.settings-content {
  padding: 20px;
}
.main.fullscreen {
  width: 100vw;
  height: 100vh;
  margin: 0;
  padding: 0;
  overflow: hidden;
}

/* 隐藏侧边栏时调整主内容区宽度 */
.main:not(.fullscreen) {
  width: 100%;
  margin-left: 0;
}
.welcome-section {
  text-align: center;
  margin-bottom: 40px;
}
.welcome-message {
  font-size: 2em;
  color: #222831;
  margin: 20px 0 16px 0;
  font-weight: bold;
}
.welcome-subtext {
  font-size: 1em;
  color: #606266;
  margin: 8px 0;
  line-height: 1.6;
}
.action-buttons {
  position: absolute;
  bottom: -30px;
  left: 0;
  display: flex !important;
  margin-top: 5px;
}
.action-btn {
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  padding: 4px;
  width: 24px;
  height: 24px;
  font-size: 14px;
  color: #606266;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  opacity: 1 !important;
}
.action-btn:hover {
  background: #c9cbce !important;
  color: #409EFF;
  border-color: #c0c4cc;
}
.action-btn .el-icon {
  font-size: 16px;
  width: 16px;
  height: 16px;
  margin: 0 auto;
}
.action-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  position: relative;
}

.action-text {
  position: absolute;
  top: -18px;
  font-size: 11px;
  background: rgba(0, 0, 0, 0.7);
  color: white;
  padding: 2px 6px;
  border-radius: 4px;
  white-space: nowrap;
  display: none;
}

.action-btn:hover .action-text {
  display: block;
}

.el-icon {
  color: #606266; /* 默认颜色 */
  font-size: 16px; /* 确保尺寸合理 */
}

.main-function-buttons {
  position: absolute;
  top: 16px;
  left: 16px;
  display: flex;
  gap: 8px;
  z-index: 10;
}

.main-function-btn {
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: #ffffff;
  border-color: #e0e0e0;
  color: #222831;
}

.main-function-btn:hover {
  background-color: #f5f7fa;
}

.main-function-btn .el-icon {
  margin-right: 6px;
}
</style>

<style>
html, body {
  margin: 0;
  height: 100%;
  font-family: 'Helvetica Neue', Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  background: #f5f6fa;
}
</style>
