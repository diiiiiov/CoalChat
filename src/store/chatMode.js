import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useChatModeStore = defineStore('chatMode', () => {
  const chatMode = ref('llm')
  function setChatMode(mode) {
    chatMode.value = mode
  }
  return { chatMode, setChatMode }
}) 