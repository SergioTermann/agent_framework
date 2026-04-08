import { ref, computed, reactive } from 'vue'

export interface User {
  id: string
  username: string
  avatar: string
  status: 'online' | 'offline' | 'away'
  lastSeen?: Date
}

export interface ChatMessage {
  id: string
  senderId: string
  receiverId: string
  content: string
  timestamp: Date
  read: boolean
  type: 'text' | 'image' | 'file'
}

export interface Conversation {
  userId: string
  messages: ChatMessage[]
  unreadCount: number
  lastMessage?: ChatMessage
}

// 简单哈希函数
async function hashPassword(pwd: string): Promise<string> {
  const encoder = new TextEncoder()
  const data = encoder.encode(pwd)
  const hashBuffer = await crypto.subtle.digest('SHA-256', data)
  const hashArray = Array.from(new Uint8Array(hashBuffer))
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('')
}

// 创建全局状态
function createChatStore() {
  // 当前登录用户
  const currentUser = ref<User | null>(null)
  
  // 所有注册用户
  const users = ref<User[]>([
    {
      id: '1',
      username: 'Alice',
      avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=Alice',
      status: 'online'
    },
    {
      id: '2',
      username: 'Bob',
      avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=Bob',
      status: 'online'
    },
    {
      id: '3',
      username: 'Charlie',
      avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=Charlie',
      status: 'away'
    },
    {
      id: '4',
      username: 'Diana',
      avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=Diana',
      status: 'offline',
      lastSeen: new Date(Date.now() - 3600000)
    }
  ])
  
  // 会话列表
  const conversations = ref<Map<string, Conversation>>(new Map())
  
  // 当前聊天对象
  const currentChatUser = ref<User | null>(null)
  
  // 注册新用户
  async function register(username: string, password: string): Promise<boolean> {
    if (users.value.some(u => u.username === username)) {
      return false
    }

    const newUser: User = {
      id: Date.now().toString(),
      username,
      avatar: `https://api.dicebear.com/7.x/avataaars/svg?seed=${username}`,
      status: 'online'
    }

    users.value.push(newUser)

    // 保存到 localStorage
    const hashedPass = await hashPassword(password)
    localStorage.setItem('chatUsers', JSON.stringify(users.value))
    localStorage.setItem(`chatPassword_${username}`, hashedPass)

    return true
  }

  // 用户登录
  async function login(username: string, password: string): Promise<boolean> {
    const user = users.value.find(u => u.username === username)
    if (!user) return false

    const savedPassword = localStorage.getItem(`chatPassword_${username}`)
    const hashedPass = await hashPassword(password)
    if (savedPassword !== hashedPass) return false

    currentUser.value = { ...user, status: 'online' }
    user.status = 'online'

    // 加载会话历史
    loadConversations()

    return true
  }
  
  // 用户登出
  function logout() {
    if (currentUser.value) {
      const user = users.value.find(u => u.id === currentUser.value!.id)
      if (user) {
        user.status = 'offline'
        user.lastSeen = new Date()
      }
    }
    currentUser.value = null
    currentChatUser.value = null
    conversations.value.clear()
  }
  
  // 发送消息
  function sendMessage(receiverId: string, content: string, type: 'text' | 'image' | 'file' = 'text') {
    if (!currentUser.value) return
    
    const message: ChatMessage = {
      id: Date.now().toString(),
      senderId: currentUser.value.id,
      receiverId,
      content,
      timestamp: new Date(),
      read: false,
      type
    }
    
    // 添加到发送者的会话
    addMessageToConversation(receiverId, message)
    
    // 模拟接收者收到消息（实际应用中应该通过 WebSocket）
    setTimeout(() => {
      // 添加到接收者的会话（如果接收者在线）
      const receiver = users.value.find(u => u.id === receiverId)
      if (receiver && receiver.status === 'online') {
        // 这里可以触发通知
      }
    }, 100)
    
    // 保存到 localStorage
    saveConversations()
  }
  
  // 添加消息到会话
  function addMessageToConversation(userId: string, message: ChatMessage) {
    let conversation = conversations.value.get(userId)
    
    if (!conversation) {
      conversation = {
        userId,
        messages: [],
        unreadCount: 0
      }
      conversations.value.set(userId, conversation)
    }
    
    conversation.messages.push(message)
    conversation.lastMessage = message
    
    // 如果是接收的消息且不是当前聊天对象，增加未读数
    if (message.receiverId === currentUser.value?.id && userId !== currentChatUser.value?.id) {
      conversation.unreadCount++
    }
  }
  
  // 标记消息为已读
  function markAsRead(userId: string) {
    const conversation = conversations.value.get(userId)
    if (conversation) {
      conversation.messages.forEach(msg => {
        if (msg.receiverId === currentUser.value?.id) {
          msg.read = true
        }
      })
      conversation.unreadCount = 0
      saveConversations()
    }
  }
  
  // 选择聊天对象
  function selectChatUser(user: User) {
    currentChatUser.value = user
    markAsRead(user.id)
  }
  
  // 获取当前会话的消息
  const currentMessages = computed(() => {
    if (!currentChatUser.value) return []
    const conversation = conversations.value.get(currentChatUser.value.id)
    return conversation?.messages || []
  })
  
  // 获取在线用户列表
  const onlineUsers = computed(() => {
    return users.value.filter(u => 
      u.id !== currentUser.value?.id && u.status === 'online'
    )
  })
  
  // 获取所有其他用户
  const otherUsers = computed(() => {
    return users.value.filter(u => u.id !== currentUser.value?.id)
  })
  
  // 获取未读消息总数
  const totalUnreadCount = computed(() => {
    let count = 0
    conversations.value.forEach(conv => {
      count += conv.unreadCount
    })
    return count
  })
  
  // 保存会话到 localStorage
  function saveConversations() {
    if (!currentUser.value) return

    const data: Record<string, { userId: string; messages: ChatMessage[]; unreadCount: number; lastMessage?: ChatMessage }> = {}
    conversations.value.forEach((conv, userId) => {
      data[userId] = {
        userId: conv.userId,
        messages: conv.messages,
        unreadCount: conv.unreadCount,
        lastMessage: conv.lastMessage
      }
    })

    localStorage.setItem(`chatConversations_${currentUser.value.id}`, JSON.stringify(data))
  }

  // 加载会话从 localStorage
  function loadConversations() {
    if (!currentUser.value) return

    const saved = localStorage.getItem(`chatConversations_${currentUser.value.id}`)
    if (saved) {
      try {
        const data = JSON.parse(saved)
        conversations.value.clear()

        Object.keys(data).forEach(userId => {
          const conv = data[userId]
          conversations.value.set(userId, {
            userId: conv.userId,
            messages: conv.messages.map((m: ChatMessage) => ({
              ...m,
              timestamp: new Date(m.timestamp)
            })),
            unreadCount: conv.unreadCount,
            lastMessage: conv.lastMessage ? {
              ...conv.lastMessage,
              timestamp: new Date(conv.lastMessage.timestamp)
            } : undefined
          })
        })
      } catch {
        conversations.value.clear()
      }
    }

    // 加载用户列表
    const savedUsers = localStorage.getItem('chatUsers')
    if (savedUsers) {
      try {
        users.value = JSON.parse(savedUsers)
      } catch {
        // 忽略损坏的数据
      }
    }
  }
  
  return {
    currentUser,
    users,
    conversations,
    currentChatUser,
    currentMessages,
    onlineUsers,
    otherUsers,
    totalUnreadCount,
    register,
    login,
    logout,
    sendMessage,
    selectChatUser,
    markAsRead
  }
}

// 导出工厂函数
export function useChatStore() {
  return chatStoreInstance
}

// 创建单例
const chatStoreInstance = createChatStore()
