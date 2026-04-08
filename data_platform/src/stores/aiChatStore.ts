import { ref } from 'vue'

export interface AiMessage {
  type: 'user' | 'bot'
  text: string
  time: string
  location?: {
    windField?: string  // 风场名称
    turbine?: string    // 风机编号或名称
  }
}

// 创建全局 AI 聊天状态
function createAiChatStore() {
  // AI 对话消息列表
  const aiMessages = ref<AiMessage[]>([])
  
  // 从 localStorage 加载消息
  function loadMessages() {
    const saved = localStorage.getItem('aiChatMessages')
    if (saved) {
      try {
        aiMessages.value = JSON.parse(saved)
      } catch (e) {
        console.error('Failed to load AI chat messages:', e)
        aiMessages.value = []
      }
    }
  }
  
  // 保存消息到 localStorage
  function saveMessages() {
    try {
      localStorage.setItem('aiChatMessages', JSON.stringify(aiMessages.value))
    } catch (e) {
      console.error('Failed to save AI chat messages:', e)
    }
  }
  
  // 添加消息
  function addMessage(message: AiMessage) {
    aiMessages.value.push(message)
    saveMessages()
  }
  
  // 更新最后一条消息（用于流式输出）
  function updateLastMessage(text: string) {
    if (aiMessages.value.length > 0) {
      const lastMessage = aiMessages.value[aiMessages.value.length - 1]
      if (lastMessage.type === 'bot') {
        lastMessage.text = text
        saveMessages()
      }
    }
  }
  
  // 清空消息
  function clearMessages() {
    aiMessages.value = []
    localStorage.removeItem('aiChatMessages')
  }
  
  // 初始化时加载消息
  loadMessages()
  
  return {
    aiMessages,
    addMessage,
    updateLastMessage,
    clearMessages,
    loadMessages,
    saveMessages
  }
}

// 创建单例
const aiChatStoreInstance = createAiChatStore()

// 导出函数
export function useAiChatStore() {
  return aiChatStoreInstance
}
