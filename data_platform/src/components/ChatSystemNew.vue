<template>
  <div class="chat-system-wrapper">
    <!-- 聊天按钮 -->
    <button v-if="!showChat" @click="showChat = true" class="chat-toggle-btn">
      <i class="fa-solid fa-comments"></i>
      <span>聊天</span>
      <span v-if="unreadCount > 0" class="badge">{{ unreadCount }}</span>
    </button>

    <!-- 聊天系统 -->
    <transition name="chat-fade">
      <div v-if="showChat" class="chat-system">
        <!-- 登录/注册界面 -->
        <div v-if="!currentUser" class="auth-container">
          <div class="auth-card">
            <div class="auth-header">
              <i class="fa-solid fa-comments"></i>
              <h2>{{ isLogin ? '登录聊天' : '注册账号' }}</h2>
              <p>{{ isLogin ? '欢迎回来' : '创建您的聊天账号' }}</p>
            </div>
            
            <form @submit.prevent="handleAuth" class="auth-form">
              <div class="form-group">
                <label>
                  <i class="fa-solid fa-user"></i>
                  用户名
                </label>
                <input 
                  v-model="username" 
                  type="text" 
                  placeholder="请输入用户名"
                  required
                />
              </div>
              
              <div class="form-group">
                <label>
                  <i class="fa-solid fa-lock"></i>
                  密码
                </label>
                <input 
                  v-model="password" 
                  type="password" 
                  placeholder="请输入密码"
                  required
                />
              </div>
              
              <div v-if="errorMsg" class="error-message">
                <i class="fa-solid fa-exclamation-circle"></i>
                {{ errorMsg }}
              </div>
              
              <button type="submit" class="auth-btn">
                <i :class="isLogin ? 'fa-solid fa-sign-in-alt' : 'fa-solid fa-user-plus'"></i>
                {{ isLogin ? '登录' : '注册' }}
              </button>
              
              <div class="auth-switch">
                {{ isLogin ? '还没有账号？' : '已有账号？' }}
                <a @click="toggleAuthMode">{{ isLogin ? '立即注册' : '立即登录' }}</a>
              </div>
            </form>
            
            <button @click="showChat = false" class="close-btn">
              <i class="fa-solid fa-times"></i>
            </button>
          </div>
        </div>
        
        <!-- 聊天主界面 -->
        <div v-else class="chat-main">
          <!-- 头部 -->
          <div class="chat-header">
            <div class="current-user">
              <div class="avatar">{{ currentUser.username[0].toUpperCase() }}</div>
              <span>{{ currentUser.username }}</span>
            </div>
            
            <div class="header-actions">
              <button @click="showContactList = !showContactList" class="action-btn" :class="{ active: showContactList }" title="联系人">
                <i class="fa-solid fa-users"></i>
                <span v-if="totalUnreadCount > 0" class="badge">{{ totalUnreadCount }}</span>
              </button>
              <button @click="handleLogout" class="action-btn" title="退出">
                <i class="fa-solid fa-sign-out-alt"></i>
              </button>
              <button @click="showChat = false" class="action-btn" title="关闭">
                <i class="fa-solid fa-times"></i>
              </button>
            </div>
          </div>
          
          <!-- 联系人列表（下拉） -->
          <transition name="slide-down">
            <div v-if="showContactList" class="contact-dropdown">
              <div class="contact-header">选择联系人</div>
              <div 
                v-for="user in onlineUsers" 
                :key="user.id"
                class="contact-item"
                :class="{ active: selectedUser?.id === user.id }"
                @click="selectUserAndClose(user)"
              >
                <div class="contact-avatar" :class="{ 'ai-avatar': user.id === 'ai-assistant' }">
                  <i v-if="user.id === 'ai-assistant'" class="fa-solid fa-brain"></i>
                  <span v-else>{{ user.username[0].toUpperCase() }}</span>
                </div>
                <div class="contact-info">
                  <div class="contact-name">
                    {{ user.username }}
                    <i v-if="user.id === 'ai-assistant'" class="fa-solid fa-sparkles ai-badge"></i>
                  </div>
                  <div class="contact-status">
                    <span v-if="user.id === 'ai-assistant'">AI助手</span>
                    <span v-else>在线</span>
                  </div>
                </div>
                <div v-if="getUserUnread(user.id) > 0" class="unread-badge">
                  {{ getUserUnread(user.id) }}
                </div>
              </div>
            </div>
          </transition>
          
          <!-- 聊天区域 -->
          <div v-if="!selectedUser" class="chat-empty">
            <i class="fa-solid fa-comments"></i>
            <h3>点击右上角选择联系人开始聊天</h3>
          </div>
          
          <template v-else>
            <!-- 消息列表 -->
            <div class="messages-container" ref="messagesRef">
              <div 
                v-for="msg in currentMessages" 
                :key="msg.id"
                class="message"
                :class="{ sent: msg.from === currentUser.id, received: msg.from !== currentUser.id, 'ai-message': msg.from === 'ai-assistant' }"
              >
                <div class="message-avatar" :class="{ 'ai-avatar': msg.from === 'ai-assistant' }">
                  <i v-if="msg.from === 'ai-assistant'" class="fa-solid fa-brain"></i>
                  <span v-else>{{ getUserName(msg.from)[0].toUpperCase() }}</span>
                </div>
                <div class="message-content">
                  <div class="message-bubble">{{ msg.text }}</div>
                  <div class="message-time">{{ formatTime(msg.time) }}</div>
                </div>
              </div>
              
              <!-- AI打字指示器 -->
              <div v-if="isAITyping && selectedUser?.id === 'ai-assistant'" class="message received ai-message typing">
                <div class="message-avatar ai-avatar">
                  <i class="fa-solid fa-brain"></i>
                </div>
                <div class="message-content">
                  <div class="message-bubble typing-bubble">
                    <div class="typing-indicator">
                      <span></span>
                      <span></span>
                      <span></span>
                    </div>
                  </div>
                </div>
              </div>
              
              <div v-if="currentMessages.length === 0 && !isAITyping" class="empty-messages">
                <i class="fa-regular fa-comment-dots"></i>
                <p>还没有消息，发送一条消息开始聊天吧</p>
              </div>
            </div>
            
            <!-- 输入框 -->
            <div class="chat-input">
              <input 
                v-model="messageText"
                type="text" 
                placeholder="输入消息... (Enter发送)"
                @keyup.enter="sendMessage"
                :disabled="isAITyping"
              />
              <button class="send-btn" @click="sendMessage" :disabled="!messageText.trim() || isAITyping">
                <i class="fa-solid fa-paper-plane"></i>
              </button>
            </div>
          </template>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'

interface User {
  id: string
  username: string
}

interface Message {
  id: string
  from: string
  to: string
  text: string
  time: Date
  read: boolean
}

// 简单哈希函数（非加密级别，但比明文好得多）
async function hashPassword(pwd: string): Promise<string> {
  const encoder = new TextEncoder()
  const data = encoder.encode(pwd)
  const hashBuffer = await crypto.subtle.digest('SHA-256', data)
  const hashArray = Array.from(new Uint8Array(hashBuffer))
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('')
}

// 状态
const showChat = ref(false)
const showContactList = ref(false)
const isLogin = ref(true)
const username = ref('')
const password = ref('')
const errorMsg = ref('')
const currentUser = ref<User | null>(null)
const selectedUser = ref<User | null>(null)
const messageText = ref('')
const messagesRef = ref<HTMLElement>()

// AI助手作为特殊用户
const AI_USER: User = {
  id: 'ai-assistant',
  username: 'Cascade Intelligence'
}

// 用户列表（模拟数据）
const allUsers = ref<User[]>([
  { id: '1', username: 'Alice' },
  { id: '2', username: 'Bob' },
  { id: '3', username: 'Charlie' },
  { id: '4', username: 'Diana' }
])

// 消息列表
const messages = ref<Message[]>([])

// 未读消息计数
const unreadCount = ref(0)

// 总未读消息数（所有联系人）
const totalUnreadCount = computed(() => {
  if (!currentUser.value) return 0
  return messages.value.filter(m => 
    m.to === currentUser.value!.id && !m.read
  ).length
})

// 在线用户（AI助手始终在第一位，然后是其他用户）
const onlineUsers = computed(() => {
  if (!currentUser.value) return []
  const otherUsers = allUsers.value.filter(u => u.id !== currentUser.value!.id)
  return [AI_USER, ...otherUsers]
})

// 当前聊天消息
const currentMessages = computed(() => {
  if (!selectedUser.value || !currentUser.value) return []
  return messages.value.filter(m => 
    (m.from === currentUser.value!.id && m.to === selectedUser.value!.id) ||
    (m.from === selectedUser.value!.id && m.to === currentUser.value!.id)
  )
})

// 切换登录/注册
function toggleAuthMode() {
  isLogin.value = !isLogin.value
  errorMsg.value = ''
}

// 处理认证
async function handleAuth() {
  errorMsg.value = ''

  if (!username.value || !password.value) {
    errorMsg.value = '请填写完整信息'
    return
  }

  const hashedPass = await hashPassword(password.value)

  if (isLogin.value) {
    // 登录
    const savedPass = localStorage.getItem(`chat_pass_${username.value}`)
    if (savedPass === hashedPass) {
      let user = allUsers.value.find(u => u.username === username.value)
      if (!user) {
        user = { id: Date.now().toString(), username: username.value }
        allUsers.value.push(user)
      }
      currentUser.value = user
      loadMessages()
      // 默认选择AI助手
      selectedUser.value = AI_USER
    } else {
      errorMsg.value = '用户名或密码错误'
    }
  } else {
    // 注册
    if (allUsers.value.some(u => u.username === username.value)) {
      errorMsg.value = '用户名已存在'
      return
    }

    const newUser: User = {
      id: Date.now().toString(),
      username: username.value
    }
    allUsers.value.push(newUser)
    localStorage.setItem(`chat_pass_${username.value}`, hashedPass)
    localStorage.setItem('chat_users', JSON.stringify(allUsers.value))

    // 自动登录并选择AI助手
    currentUser.value = newUser
    selectedUser.value = AI_USER
  }

  username.value = ''
  password.value = ''
}

// 退出登录
function handleLogout() {
  if (confirm('确定要退出吗？')) {
    saveMessages()
    currentUser.value = null
    selectedUser.value = null
    messageText.value = ''
    showContactList.value = false
  }
}

// 选择用户
function selectUser(user: User) {
  selectedUser.value = user
  markAsRead(user.id)
  nextTick(() => {
    scrollToBottom()
  })
}

// 选择用户并关闭联系人列表
function selectUserAndClose(user: User) {
  selectUser(user)
  showContactList.value = false
}

// AI回复逻辑
const isAITyping = ref(false)

function getAIResponse(userMessage: string): string {
  const responses = [
    '我是Cascade Intelligence，很高兴为您服务！',
    '这是一个很好的问题。让我为您分析一下...',
    '根据您的描述，我建议您可以尝试以下方法...',
    '我理解您的需求，这里有几个解决方案供您参考。',
    '感谢您的提问！我会尽力帮助您解决这个问题。',
    '基于当前的数据分析，我认为...',
    '让我帮您整理一下思路...',
    '这个问题很有意思，我的建议是...'
  ]
  
  // 简单的关键词匹配
  if (userMessage.includes('你好') || userMessage.includes('您好')) {
    return '您好！我是Cascade Intelligence，您的智能助手。有什么我可以帮助您的吗？'
  }
  if (userMessage.includes('谢谢') || userMessage.includes('感谢')) {
    return '不客气！很高兴能帮到您。如果还有其他问题，随时告诉我！'
  }
  if (userMessage.includes('帮助') || userMessage.includes('怎么')) {
    return '我可以帮您解答问题、提供建议、分析数据等。请告诉我您需要什么帮助？'
  }
  
  return responses[Math.floor(Math.random() * responses.length)]
}

// 发送消息
function sendMessage() {
  if (!messageText.value.trim() || !selectedUser.value || !currentUser.value) return
  
  const msg: Message = {
    id: Date.now().toString(),
    from: currentUser.value.id,
    to: selectedUser.value.id,
    text: messageText.value.trim(),
    time: new Date(),
    read: false
  }
  
  messages.value.push(msg)
  const userMsg = messageText.value.trim()
  messageText.value = ''
  
  saveMessages()
  
  nextTick(() => {
    scrollToBottom()
  })
  
  // 如果是发给AI助手，自动回复
  if (selectedUser.value.id === AI_USER.id) {
    isAITyping.value = true
    
    setTimeout(() => {
      const aiReply: Message = {
        id: Date.now().toString(),
        from: AI_USER.id,
        to: currentUser.value!.id,
        text: getAIResponse(userMsg),
        time: new Date(),
        read: false
      }
      
      messages.value.push(aiReply)
      isAITyping.value = false
      saveMessages()
      
      nextTick(() => {
        scrollToBottom()
      })
    }, 800 + Math.random() * 1200)
  }
}

// 获取用户未读消息数
function getUserUnread(userId: string): number {
  if (!currentUser.value) return 0
  return messages.value.filter(m => 
    m.from === userId && m.to === currentUser.value!.id && !m.read
  ).length
}

// 标记为已读
function markAsRead(userId: string) {
  if (!currentUser.value) return
  messages.value.forEach(m => {
    if (m.from === userId && m.to === currentUser.value!.id) {
      m.read = true
    }
  })
  updateUnreadCount()
  saveMessages()
}

// 更新未读总数
function updateUnreadCount() {
  if (!currentUser.value) {
    unreadCount.value = 0
    return
  }
  unreadCount.value = messages.value.filter(m => 
    m.to === currentUser.value!.id && !m.read
  ).length
}

// 获取用户名
function getUserName(userId: string): string {
  if (userId === AI_USER.id) return AI_USER.username
  const user = allUsers.value.find(u => u.id === userId)
  return user?.username || 'Unknown'
}

// 格式化时间
function formatTime(date: Date): string {
  const d = new Date(date)
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
}

// 滚动到底部
function scrollToBottom() {
  if (messagesRef.value) {
    messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  }
}

// 保存消息
function saveMessages() {
  if (!currentUser.value) return
  localStorage.setItem(`chat_messages_${currentUser.value.id}`, JSON.stringify(messages.value))
}

// 加载消息
function loadMessages() {
  if (!currentUser.value) return
  const saved = localStorage.getItem(`chat_messages_${currentUser.value.id}`)
  if (saved) {
    try {
      messages.value = JSON.parse(saved).map((m: Message) => ({
        ...m,
        time: new Date(m.time)
      }))
    } catch {
      messages.value = []
    }
  }
  updateUnreadCount()
}

// 加载用户列表
const savedUsers = localStorage.getItem('chat_users')
if (savedUsers) {
  try {
    allUsers.value = JSON.parse(savedUsers)
  } catch {
    // 忽略损坏的数据
  }
}
</script>

<style lang="scss" scoped>
.chat-system-wrapper {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 1001;
  display: flex;
  align-items: stretch;
  pointer-events: none;
}
.chat-toggle-btn {
  position: absolute;
  top: 0;
  right: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: center;
  justify-content: center;
  width: 64px;
  padding: 24px 0;
  font-size: 13px;
  font-weight: 600;
  color: rgba(148, 163, 184, 80%);
  pointer-events: auto;
  cursor: pointer;
  background: linear-gradient(180deg, rgba(15, 23, 42, 95%) 0%, rgba(30, 41, 59, 95%) 100%);
  border: none;
  border-left: 1px solid rgba(148, 163, 184, 10%);
  border-radius: 16px 0 0 16px;
  box-shadow: -8px 0 32px rgba(0, 0, 0, 50%);
  transition: all 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
  backdrop-filter: blur(20px);
  i {
    font-size: 22px;
    color: rgba(59, 130, 246, 80%);
    transition: all 0.3s ease;
  }
  span {
    letter-spacing: 2px;
    writing-mode: vertical-rl;
  }
  .badge {
    min-width: 20px;
    padding: 4px 6px;
    font-size: 11px;
    font-weight: 600;
    color: #fff;
    background: rgba(239, 68, 68, 95%);
    border-radius: 10px;
    box-shadow: 0 4px 12px rgba(239, 68, 68, 40%);
    writing-mode: horizontal-tb;
    animation: pulse-badge 2s ease-in-out infinite;
  }
  &:hover {
    background: linear-gradient(180deg, rgba(30, 41, 59, 98%) 0%, rgba(51, 65, 85, 98%) 100%);
    box-shadow: -12px 0 48px rgba(59, 130, 246, 30%);
    transform: translateX(-4px);
    i {
      color: rgba(59, 130, 246, 100%);
      transform: scale(1.1);
    }
    span {
      color: rgba(226, 232, 240, 100%);
    }
  }
}

@keyframes pulse-badge {
  0%, 100% {
    box-shadow: 0 4px 12px rgba(239, 68, 68, 40%);
    transform: scale(1);
  }
  50% {
    box-shadow: 0 6px 20px rgba(239, 68, 68, 60%);
    transform: scale(1.05);
  }
}
.chat-fade-enter-active,
.chat-fade-leave-active {
  transition: all 0.5s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.chat-fade-enter-from,
.chat-fade-leave-to {
  opacity: 0;
  transform: translateX(100%);
}
.chat-system {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: 25vw;
  min-width: 320px;
  max-width: 450px;
  pointer-events: auto;
  background: linear-gradient(135deg, rgba(15, 23, 42, 97%) 0%, rgba(30, 41, 59, 97%) 100%);
  border-left: 1px solid rgba(148, 163, 184, 10%);
  box-shadow: -20px 0 60px rgba(0, 0, 0, 60%);
  backdrop-filter: blur(24px) saturate(180%);
  &::before {
    position: absolute;
    top: 0;
    left: 0;
    width: 1px;
    height: 100%;
    content: '';
    background: linear-gradient(180deg, transparent 0%, rgba(59, 130, 246, 30%) 50%, transparent 100%);
  }
}

// 认证界面样式
.auth-container {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  padding: 30px 20px;
}
.auth-card {
  position: relative;
  width: 100%;
  max-width: 360px;
  padding: 32px 24px;
  background: linear-gradient(135deg, rgba(30, 41, 59, 95%) 0%, rgba(51, 65, 85, 90%) 100%);
  border: 1px solid rgba(148, 163, 184, 10%);
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 50%);
  backdrop-filter: blur(20px);
}
.auth-header {
  margin-bottom: 28px;
  text-align: center;
  i {
    margin-bottom: 12px;
    font-size: 42px;
    color: rgba(59, 130, 246, 90%);
  }
  h2 {
    margin: 0 0 6px;
    font-size: 24px;
    font-weight: 600;
    color: rgba(226, 232, 240, 95%);
  }
  p {
    margin: 0;
    font-size: 13px;
    color: rgba(148, 163, 184, 70%);
  }
}
.auth-form {
  .form-group {
    margin-bottom: 18px;
    label {
      display: flex;
      gap: 6px;
      align-items: center;
      margin-bottom: 6px;
      font-size: 12px;
      font-weight: 500;
      color: rgba(226, 232, 240, 80%);
      i {
        font-size: 13px;
        color: rgba(59, 130, 246, 70%);
      }
    }
    input {
      width: 100%;
      padding: 12px 14px;
      font-size: 14px;
      color: rgba(226, 232, 240, 95%);
      background: rgba(51, 65, 85, 50%);
      border: 1px solid rgba(148, 163, 184, 15%);
      border-radius: 10px;
      transition: all 0.3s ease;
      &:focus {
        background: rgba(51, 65, 85, 70%);
        border-color: rgba(59, 130, 246, 50%);
        outline: none;
        box-shadow: 0 0 0 3px rgba(59, 130, 246, 10%);
      }
      &::placeholder {
        color: rgba(148, 163, 184, 50%);
      }
    }
  }
  .error-message {
    display: flex;
    gap: 8px;
    align-items: center;
    padding: 10px 14px;
    margin-bottom: 18px;
    font-size: 12px;
    color: rgba(239, 68, 68, 90%);
    background: rgba(239, 68, 68, 10%);
    border: 1px solid rgba(239, 68, 68, 20%);
    border-radius: 8px;
  }
  .auth-btn {
    display: flex;
    gap: 8px;
    align-items: center;
    justify-content: center;
    width: 100%;
    padding: 12px;
    font-size: 14px;
    font-weight: 600;
    color: #fff;
    cursor: pointer;
    background: linear-gradient(135deg, rgba(59, 130, 246, 90%) 0%, rgba(96, 165, 250, 85%) 100%);
    border: none;
    border-radius: 10px;
    box-shadow: 0 4px 16px rgba(59, 130, 246, 30%);
    transition: all 0.3s ease;
    &:hover {
      background: linear-gradient(135deg, rgba(59, 130, 246, 100%) 0%, rgba(96, 165, 250, 95%) 100%);
      box-shadow: 0 6px 24px rgba(59, 130, 246, 40%);
      transform: translateY(-2px);
    }
  }
  .auth-switch {
    margin-top: 20px;
    font-size: 12px;
    color: rgba(148, 163, 184, 70%);
    text-align: center;
    a {
      color: rgba(59, 130, 246, 90%);
      text-decoration: none;
      cursor: pointer;
      &:hover {
        text-decoration: underline;
      }
    }
  }
}
.close-btn {
  position: absolute;
  top: 16px;
  right: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  color: rgba(148, 163, 184, 70%);
  cursor: pointer;
  background: rgba(51, 65, 85, 40%);
  border: 1px solid rgba(148, 163, 184, 10%);
  border-radius: 8px;
  transition: all 0.3s ease;
  &:hover {
    color: rgba(239, 68, 68, 90%);
    background: rgba(239, 68, 68, 10%);
  }
}

// 聊天主界面
.chat-main {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
}
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  background: linear-gradient(135deg, rgba(30, 41, 59, 60%) 0%, rgba(51, 65, 85, 40%) 100%);
  border-bottom: 1px solid rgba(148, 163, 184, 8%);
  .current-user {
    display: flex;
    gap: 10px;
    align-items: center;
    .avatar {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 36px;
      height: 36px;
      font-size: 15px;
      font-weight: 600;
      color: #fff;
      background: linear-gradient(135deg, rgba(59, 130, 246, 90%) 0%, rgba(96, 165, 250, 85%) 100%);
      border-radius: 50%;
    }
    span {
      font-size: 14px;
      font-weight: 500;
      color: rgba(226, 232, 240, 95%);
    }
  }
  .header-actions {
    display: flex;
    gap: 8px;
  }
  .action-btn {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    color: rgba(148, 163, 184, 70%);
    cursor: pointer;
    background: rgba(51, 65, 85, 40%);
    border: 1px solid rgba(148, 163, 184, 10%);
    border-radius: 8px;
    transition: all 0.3s ease;
    i {
      font-size: 16px;
    }
    .badge {
      position: absolute;
      top: -4px;
      right: -4px;
      min-width: 18px;
      padding: 2px 5px;
      font-size: 10px;
      font-weight: 600;
      color: #fff;
      background: rgba(239, 68, 68, 95%);
      border-radius: 9px;
      box-shadow: 0 2px 8px rgba(239, 68, 68, 40%);
    }
    &:hover {
      color: rgba(59, 130, 246, 90%);
      background: rgba(59, 130, 246, 10%);
      border-color: rgba(59, 130, 246, 20%);
    }
    &.active {
      color: rgba(59, 130, 246, 100%);
      background: rgba(59, 130, 246, 15%);
      border-color: rgba(59, 130, 246, 30%);
    }
  }
}

// 联系人下拉列表
.slide-down-enter-active,
.slide-down-leave-active {
  transition: all 0.3s ease;
}
.slide-down-enter-from,
.slide-down-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}
.contact-dropdown {
  max-height: 300px;
  overflow-y: auto;
  background: linear-gradient(180deg, rgba(30, 41, 59, 95%) 0%, rgba(15, 23, 42, 95%) 100%);
  border-bottom: 1px solid rgba(148, 163, 184, 10%);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 30%);
  &::-webkit-scrollbar {
    width: 4px;
  }
  &::-webkit-scrollbar-thumb {
    background: rgba(59, 130, 246, 30%);
    border-radius: 2px;
  }
  .contact-header {
    padding: 12px 20px;
    font-size: 11px;
    font-weight: 600;
    color: rgba(148, 163, 184, 70%);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    border-bottom: 1px solid rgba(148, 163, 184, 6%);
  }
  .contact-item {
    display: flex;
    gap: 12px;
    align-items: center;
    padding: 12px 20px;
    cursor: pointer;
    transition: all 0.3s ease;
    &:hover {
      background: rgba(51, 65, 85, 40%);
    }
    &.active {
      background: rgba(59, 130, 246, 15%);
      border-left: 3px solid rgba(59, 130, 246, 90%);
    }
    .contact-avatar {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 38px;
      height: 38px;
      font-size: 15px;
      font-weight: 600;
      color: #fff;
      background: linear-gradient(135deg, rgba(51, 65, 85, 80%) 0%, rgba(71, 85, 105, 60%) 100%);
      border-radius: 50%;
      &.ai-avatar {
        background: linear-gradient(135deg, rgba(139, 92, 246, 90%) 0%, rgba(168, 85, 247, 85%) 100%);
        box-shadow: 0 0 16px rgba(139, 92, 246, 40%);
        animation: ai-pulse 2s ease-in-out infinite;
        i {
          font-size: 17px;
        }
      }
    }
    .contact-info {
      flex: 1;
      .contact-name {
        display: flex;
        gap: 6px;
        align-items: center;
        margin-bottom: 2px;
        font-size: 13px;
        font-weight: 500;
        color: rgba(226, 232, 240, 95%);
        .ai-badge {
          font-size: 11px;
          color: rgba(139, 92, 246, 90%);
          animation: sparkle 1.5s ease-in-out infinite;
        }
      }
      .contact-status {
        font-size: 11px;
        color: rgba(148, 163, 184, 60%);
      }
    }
    .unread-badge {
      min-width: 20px;
      padding: 2px 6px;
      font-size: 10px;
      font-weight: 600;
      color: #fff;
      text-align: center;
      background: rgba(59, 130, 246, 90%);
      border-radius: 10px;
    }
  }
}

@keyframes ai-pulse {
  0%, 100% {
    box-shadow: 0 0 16px rgba(139, 92, 246, 40%);
  }
  50% {
    box-shadow: 0 0 24px rgba(139, 92, 246, 60%);
  }
}

@keyframes sparkle {
  0%, 100% {
    opacity: 0.6;
    transform: scale(1);
  }
  50% {
    opacity: 1;
    transform: scale(1.1);
  }
}

// 聊天区域
.chat-empty {
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
  i {
    margin-bottom: 20px;
    font-size: 64px;
    color: rgba(148, 163, 184, 20%);
  }
  h3 {
    margin: 0;
    font-size: 15px;
    font-weight: 500;
    color: rgba(226, 232, 240, 60%);
    text-align: center;
  }
}
.current-chat {
  padding: 14px 20px;
  background: linear-gradient(135deg, rgba(30, 41, 59, 40%) 0%, rgba(51, 65, 85, 30%) 100%);
  border-bottom: 1px solid rgba(148, 163, 184, 6%);
  .chat-user-info {
    display: flex;
    gap: 12px;
    align-items: center;
    .avatar {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 40px;
      height: 40px;
      font-size: 16px;
      font-weight: 600;
      color: #fff;
      background: linear-gradient(135deg, rgba(51, 65, 85, 80%) 0%, rgba(71, 85, 105, 60%) 100%);
      border-radius: 50%;
      &.ai-avatar {
        background: linear-gradient(135deg, rgba(139, 92, 246, 90%) 0%, rgba(168, 85, 247, 85%) 100%);
        box-shadow: 0 0 16px rgba(139, 92, 246, 30%);
        i {
          font-size: 18px;
        }
      }
    }
    .user-info {
      h3 {
        display: flex;
        gap: 6px;
        align-items: center;
        margin: 0 0 4px;
        font-size: 15px;
        font-weight: 600;
        color: rgba(226, 232, 240, 95%);
        .ai-badge {
          font-size: 12px;
          color: rgba(139, 92, 246, 90%);
        }
      }
      .status {
        font-size: 12px;
        color: rgba(148, 163, 184, 70%);
      }
    }
  }
}
.messages-container {
  flex: 1;
  padding: 20px;
  overflow-y: auto;
  &::-webkit-scrollbar {
    width: 5px;
  }
  &::-webkit-scrollbar-thumb {
    background: rgba(59, 130, 246, 30%);
    border-radius: 3px;
  }
  .message {
    display: flex;
    gap: 10px;
    margin-bottom: 16px;
    &.sent {
      flex-direction: row-reverse;
      .message-content {
        align-items: flex-end;
      }
      .message-bubble {
        color: #fff;
        background: linear-gradient(135deg, rgba(59, 130, 246, 90%) 0%, rgba(96, 165, 250, 85%) 100%);
      }
      .message-avatar {
        background: linear-gradient(135deg, rgba(59, 130, 246, 90%) 0%, rgba(96, 165, 250, 85%) 100%);
      }
    }
    .message-avatar {
      display: flex;
      flex-shrink: 0;
      align-items: center;
      justify-content: center;
      width: 32px;
      height: 32px;
      font-size: 13px;
      font-weight: 600;
      color: #fff;
      background: linear-gradient(135deg, rgba(51, 65, 85, 80%) 0%, rgba(71, 85, 105, 60%) 100%);
      border-radius: 50%;
      &.ai-avatar {
        background: linear-gradient(135deg, rgba(139, 92, 246, 90%) 0%, rgba(168, 85, 247, 85%) 100%);
        box-shadow: 0 0 12px rgba(139, 92, 246, 30%);
        i {
          font-size: 15px;
        }
      }
    }
    .message-content {
      display: flex;
      flex-direction: column;
      gap: 4px;
      max-width: 70%;
    }
    .message-bubble {
      padding: 10px 14px;
      font-size: 13px;
      line-height: 1.5;
      color: rgba(226, 232, 240, 95%);
      word-wrap: break-word;
      background: linear-gradient(135deg, rgba(51, 65, 85, 50%) 0%, rgba(71, 85, 105, 30%) 100%);
      border-radius: 12px;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 15%);
      &.typing-bubble {
        padding: 14px 18px;
        background: linear-gradient(135deg, rgba(139, 92, 246, 15%) 0%, rgba(168, 85, 247, 10%) 100%);
        border: 1px solid rgba(139, 92, 246, 20%);
      }
    }
    &.ai-message {
      .message-bubble {
        background: linear-gradient(135deg, rgba(139, 92, 246, 20%) 0%, rgba(168, 85, 247, 15%) 100%);
        border: 1px solid rgba(139, 92, 246, 25%);
        box-shadow: 0 4px 16px rgba(139, 92, 246, 15%);
      }
    }
    .typing-indicator {
      display: flex;
      gap: 5px;
      align-items: center;
      span {
        width: 7px;
        height: 7px;
        background: rgba(139, 92, 246, 80%);
        border-radius: 50%;
        animation: typing-bounce 1.4s ease-in-out infinite;
        &:nth-child(2) {
          animation-delay: 0.2s;
        }
        &:nth-child(3) {
          animation-delay: 0.4s;
        }
      }
    }
    .message-time {
      padding: 0 4px;
      font-size: 10px;
      color: rgba(148, 163, 184, 50%);
    }
  }
  .empty-messages {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    i {
      margin-bottom: 14px;
      font-size: 56px;
      color: rgba(148, 163, 184, 20%);
    }
    p {
      margin: 0;
      font-size: 13px;
      color: rgba(148, 163, 184, 50%);
    }
  }
}

@keyframes typing-bounce {
  0%, 60%, 100% {
    opacity: 0.6;
    transform: translateY(0);
  }
  30% {
    opacity: 1;
    transform: translateY(-8px);
  }
}
.chat-input {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 16px 20px;
  background: linear-gradient(135deg, rgba(15, 23, 42, 80%) 0%, rgba(30, 41, 59, 60%) 100%);
  border-top: 1px solid rgba(148, 163, 184, 8%);
  input {
    flex: 1;
    padding: 11px 14px;
    font-size: 13px;
    color: rgba(226, 232, 240, 95%);
    background: rgba(51, 65, 85, 50%);
    border: 1px solid rgba(148, 163, 184, 12%);
    border-radius: 10px;
    transition: all 0.3s ease;
    &:focus {
      background: rgba(51, 65, 85, 70%);
      border-color: rgba(59, 130, 246, 40%);
      outline: none;
      box-shadow: 0 0 0 3px rgba(59, 130, 246, 8%);
    }
    &::placeholder {
      color: rgba(148, 163, 184, 50%);
    }
    &:disabled {
      cursor: not-allowed;
      opacity: 0.5;
    }
  }
  .send-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 40px;
    height: 40px;
    color: #fff;
    cursor: pointer;
    background: linear-gradient(135deg, rgba(59, 130, 246, 90%) 0%, rgba(96, 165, 250, 85%) 100%);
    border: none;
    border-radius: 10px;
    box-shadow: 0 4px 16px rgba(59, 130, 246, 25%);
    transition: all 0.3s ease;
    i {
      font-size: 16px;
    }
    &:hover:not(:disabled) {
      box-shadow: 0 6px 24px rgba(59, 130, 246, 40%);
      transform: translateY(-2px);
    }
    &:disabled {
      cursor: not-allowed;
      opacity: 0.4;
    }
  }
}
</style>
