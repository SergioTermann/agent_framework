<template>
  <div class="map-container">
    <!-- 顶部标题栏 -->
    <div class="map-header">
      <div class="header-left">
        <div class="header-icon">
          <img src="/images/icon-logo.jpg" alt="公司标志" />
        </div>
        <div class="header-title">
          <div class="cn">智能值守系统</div>
          <div class="en">CAUSYRA AI Fault Location System</div>
        </div>
      </div>
      <div class="header-right">
        <div class="stats-card clickable" @click.stop="handleCardClick('all')">
          <i class="fa-solid fa-tower-broadcast"></i>
          <div class="stats-info">
            <div class="stats-value">25</div>
            <div class="stats-label">风机总数</div>
          </div>
        </div>
        <div class="stats-card clickable" @click.stop="handleCardClick('all')">
          <i class="fa-solid fa-bolt"></i>
          <div class="stats-info">
            <div class="stats-value">62.5MW</div>
            <div class="stats-label">装机容量</div>
          </div>
        </div>
        <div class="stats-card warning clickable" @click.stop="handleCardClick('warning')">
          <i class="fa-solid fa-triangle-exclamation"></i>
          <div class="stats-info">
            <div class="stats-value">2</div>
            <div class="stats-label">告警设备</div>
          </div>
        </div>
        <div class="stats-card clickable video-detection-btn" @click.stop="goToVideoAnalysis">
          <i class="fa-solid fa-brain"></i>
          <div class="stats-info">
            <div class="stats-value">AI分析</div>
            <div class="stats-label">视频检测</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 地图主体 -->
    <div class="map-content">
      <!-- 左侧风场列表 -->
      <div class="wind-field-list">
        <div class="list-header">
          <i class="fa-solid fa-list-ul"></i>
          <span class="list-title">风场列表</span>
        </div>
        <div
          v-for="field in windFields"
          :key="field.id"
          class="field-item"
          :class="{ active: selectedField === field.id }"
          @click="selectField(field.id)"
        >
          <div class="field-icon">
            <i class="fa-solid fa-location-dot"></i>
          </div>
          <div class="field-content">
            <div class="field-name">{{ field.name }}</div>
            <div class="field-info">
              <span class="turbine-count">
                <i class="fa-solid fa-wind"></i>
                {{ field.turbineCount }}台
              </span>
              <span class="status" :class="field.status">
                <i :class="field.status === 'normal' ? 'fa-solid fa-circle-check' : 'fa-solid fa-circle-exclamation'"></i>
                {{ field.status === 'normal' ? '正常' : '告警' }}
              </span>
            </div>
          </div>
          <div class="field-arrow">
            <i class="fa-solid fa-chevron-right"></i>
          </div>
        </div>
      </div>

      <!-- 中间地图区域 -->
      <div class="map-area" @click.stop>
        <div id="leaflet-map" ref="mapContainer"></div>
      </div>

      <!-- 右侧聊天面板 -->
      <div class="chat-panel">
        <!-- 登录/注册界面 -->
        <div v-if="!currentUser" class="auth-panel">
          <div class="auth-card">
            <div class="auth-header">
              <i class="fa-solid fa-user-circle"></i>
              <h3>{{ isLogin ? '登录账号' : '注册账号' }}</h3>
              <p>{{ isLogin ? '欢迎回来' : '创建您的聊天账号' }}</p>
            </div>
            
            <form @submit.prevent="handleAuth" class="auth-form">
              <div class="form-group">
                <label>
                  <i class="fa-solid fa-user"></i>
                  用户名
                </label>
                <input 
                  v-model="authForm.username" 
                  type="text" 
                  placeholder="请输入用户名"
                  required
                  minlength="3"
                />
              </div>
              
              <div class="form-group">
                <label>
                  <i class="fa-solid fa-lock"></i>
                  密码
                </label>
                <input 
                  v-model="authForm.password" 
                  type="password" 
                  placeholder="请输入密码"
                  required
                  minlength="6"
                />
              </div>
              
              <div v-if="!isLogin" class="form-group">
                <label>
                  <i class="fa-solid fa-lock"></i>
                  确认密码
                </label>
                <input 
                  v-model="authForm.confirmPassword" 
                  type="password" 
                  placeholder="请再次输入密码"
                  required
                  minlength="6"
                />
              </div>
              
              <div v-if="authError" class="error-message">
                <i class="fa-solid fa-exclamation-circle"></i>
                {{ authError }}
              </div>
              
              <button type="submit" class="auth-button">
                {{ isLogin ? '登录' : '注册' }}
              </button>
              
              <div class="auth-switch">
                <span v-if="isLogin">
                  还没有账号？
                  <a @click="isLogin = false">立即注册</a>
                </span>
                <span v-else>
                  已有账号？
                  <a @click="isLogin = true">立即登录</a>
                </span>
              </div>
            </form>
          </div>
        </div>

        <!-- 聊天主界面（登录后显示） -->
        <template v-else>
          <!-- 左侧联系人列表 -->
          <div class="contact-list">
            <div class="contact-header">
              <div class="user-info">
                <div class="user-avatar-wrapper" @click="showAvatarSelector = true" title="点击修改头像">
                  <img v-if="currentUser.avatar" :src="currentUser.avatar" alt="头像" class="user-avatar-img" />
                  <i v-else class="fa-solid fa-user-circle"></i>
                  <div class="avatar-edit-icon">
                    <i class="fa-solid fa-camera"></i>
                  </div>
                </div>
                <span>{{ currentUser.username }}</span>
              </div>
              <button @click="logout" class="logout-btn" title="退出登录">
                <i class="fa-solid fa-right-from-bracket"></i>
              </button>
            </div>
            <div class="contact-items">
            <div 
              v-for="contact in contacts" 
              :key="contact.id"
              class="contact-item"
              :class="{ active: currentContact?.id === contact.id }"
              @click="selectContact(contact)"
            >
              <div class="contact-avatar">
                <i :class="contact.icon"></i>
                <span v-if="contact.unread > 0" class="unread-badge">{{ contact.unread }}</span>
              </div>
              <div class="contact-info">
                <div class="contact-name">{{ contact.name }}</div>
                <div class="contact-status">{{ contact.status }}</div>
              </div>
            </div>
          </div>
        </div>

        <!-- 右侧聊天窗口 -->
        <div class="chat-window">
          <div class="chat-header">
            <div class="chat-title">
              <i :class="currentContact?.icon"></i>
              <span>{{ currentContact?.name || '请选择联系人' }}</span>
            </div>
            <div class="chat-status">{{ currentContact?.status }}</div>
          </div>
          
          <div class="chat-messages" ref="chatMessages">
            <div v-if="!currentContact" class="empty-chat">
              <i class="fa-solid fa-comments"></i>
              <p>选择一个联系人开始聊天</p>
            </div>
            <div v-else v-for="(msg, index) in currentMessages" :key="index" class="message" :class="msg.type">
              <div class="message-avatar">
                <i :class="msg.type === 'user' ? 'fa-solid fa-user' : currentContact.icon"></i>
              </div>
              <div class="message-content">
                <div v-if="msg.location && (msg.location.windField || msg.location.turbine)" class="message-location">
                  <i class="fa-solid fa-location-dot"></i>
                  <span v-if="msg.location.windField">{{ msg.location.windField }}</span>
                  <span v-if="msg.location.turbine"> - {{ msg.location.turbine }}</span>
                </div>
                <div class="message-text">{{ msg.text }}</div>
                <div class="message-time">{{ msg.time }}</div>
              </div>
            </div>
          </div>
          
          <div class="chat-input" v-if="currentContact">
            <input 
              v-model="inputMessage" 
              @keyup.enter="sendMessage"
              type="text" 
              :placeholder="`给 ${currentContact.name} 发消息...`" 
            />
            <button @click="sendMessage" :disabled="!inputMessage.trim()">
              <i class="fa-solid fa-paper-plane"></i>
            </button>
          </div>
        </div>
        </template>
        
        <!-- 头像选择器弹窗 -->
        <div v-if="showAvatarSelector" class="avatar-selector-overlay" @click="showAvatarSelector = false">
          <div class="avatar-selector-modal" @click.stop>
            <div class="modal-header">
              <h3>选择头像</h3>
              <button @click="showAvatarSelector = false" class="close-btn">
                <i class="fa-solid fa-times"></i>
              </button>
            </div>
            
            <div class="modal-content">
              <div class="avatar-grid">
                <div 
                  v-for="(avatar, index) in avatarOptions" 
                  :key="index"
                  class="avatar-option"
                  :class="{ active: currentUser?.avatar === avatar }"
                  @click="selectAvatar(avatar)"
                >
                  <img :src="avatar" :alt="`头像 ${index + 1}`" />
                </div>
              </div>
              
              <div class="upload-section">
                <label for="avatar-upload" class="upload-btn">
                  <i class="fa-solid fa-upload"></i>
                  上传自定义头像
                </label>
                <input 
                  id="avatar-upload" 
                  type="file" 
                  accept="image/*" 
                  @change="uploadAvatar"
                  style="display: none;"
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAiChatStore } from '@/stores/aiChatStore'
import { difyService } from '@/services/difyService'

const router = useRouter()
const mapContainer = ref<HTMLElement | null>(null)
const chatMessages = ref<HTMLElement | null>(null)
let map: any = null
let markers: any[] = []

// 声明 Leaflet 类型
declare const L: any

// 使用全局 AI 聊天 store
const aiChatStore = useAiChatStore()

// 用户认证相关
const currentUser = ref<any>(null)
const isLogin = ref(true)
const authForm = ref({
  username: '',
  password: '',
  confirmPassword: ''
})
const authError = ref('')

// 头像选择器
const showAvatarSelector = ref(false)
const avatarOptions = [
  'https://api.dicebear.com/7.x/adventurer/svg?seed=Midnight&backgroundColor=b6e3f4',
  'https://api.dicebear.com/7.x/adventurer/svg?seed=Jasper&backgroundColor=c0aede',
  'https://api.dicebear.com/7.x/adventurer/svg?seed=Luna&backgroundColor=ffd5dc',
  'https://api.dicebear.com/7.x/adventurer-neutral/svg?seed=Oliver&backgroundColor=d1d4f9',
  'https://api.dicebear.com/7.x/adventurer-neutral/svg?seed=Sophie&backgroundColor=ffdfbf',
  'https://api.dicebear.com/7.x/adventurer-neutral/svg?seed=Max&backgroundColor=c0f0dd',
  'https://api.dicebear.com/7.x/lorelei/svg?seed=Emma&backgroundColor=b6e3f4',
  'https://api.dicebear.com/7.x/lorelei/svg?seed=Jack&backgroundColor=ffd5dc',
  'https://api.dicebear.com/7.x/lorelei/svg?seed=Mia&backgroundColor=ffdfbf',
  'https://api.dicebear.com/7.x/micah/svg?seed=Alex&backgroundColor=d1d4f9',
  'https://api.dicebear.com/7.x/micah/svg?seed=Sam&backgroundColor=c0aede',
  'https://api.dicebear.com/7.x/micah/svg?seed=Riley&backgroundColor=c0f0dd'
]

// 初始化管理员账号并自动登录
const initAdminAccount = () => {
  // 确保管理员账号存在
  const users = JSON.parse(localStorage.getItem('chatUsers') || '[]')
  const adminExists = users.find((u: any) => u.username === 'admin')
  
  if (!adminExists) {
    users.push({
      username: 'admin',
      password: 'admin123',
      isAdmin: true
    })
    localStorage.setItem('chatUsers', JSON.stringify(users))
  }
  
  // 自动登录管理员账号
  const savedUser = localStorage.getItem('chatUser')
  if (!savedUser) {
    // 如果没有保存的用户，自动登录管理员
    currentUser.value = { 
      username: 'admin',
      isAdmin: true,
      avatar: '/images/touxiang.png'
    }
    localStorage.setItem('chatUser', JSON.stringify(currentUser.value))
  } else {
    currentUser.value = JSON.parse(savedUser)
    // 如果是admin用户，更新头像为新头像
    if (currentUser.value.username === 'admin') {
      currentUser.value.avatar = '/images/touxiang.png'
      localStorage.setItem('chatUser', JSON.stringify(currentUser.value))
    }
  }
}

// 从 localStorage 加载用户（已合并到下方的 onMounted 钩子中）

// 处理登录/注册
const handleAuth = () => {
  authError.value = ''
  
  if (!authForm.value.username || !authForm.value.password) {
    authError.value = '请填写完整信息'
    return
  }
  
  if (authForm.value.username.length < 3) {
    authError.value = '用户名至少3个字符'
    return
  }
  
  if (authForm.value.password.length < 6) {
    authError.value = '密码至少6个字符'
    return
  }
  
  if (isLogin.value) {
    // 登录逻辑
    const users = JSON.parse(localStorage.getItem('chatUsers') || '[]')
    const user = users.find((u: any) => u.username === authForm.value.username)
    
    if (!user) {
      authError.value = '用户不存在'
      return
    }
    
    if (user.password !== authForm.value.password) {
      authError.value = '密码错误'
      return
    }
    
    currentUser.value = { 
      username: user.username,
      isAdmin: user.isAdmin || false,
      avatar: user.avatar
    }
    localStorage.setItem('chatUser', JSON.stringify(currentUser.value))
    authForm.value = { username: '', password: '', confirmPassword: '' }
  } else {
    // 注册逻辑
    if (authForm.value.password !== authForm.value.confirmPassword) {
      authError.value = '两次密码不一致'
      return
    }
    
    const users = JSON.parse(localStorage.getItem('chatUsers') || '[]')
    
    if (users.find((u: any) => u.username === authForm.value.username)) {
      authError.value = '用户名已存在'
      return
    }
    
    const newUser = {
      username: authForm.value.username,
      password: authForm.value.password,
      isAdmin: false
    }
    
    users.push(newUser)
    localStorage.setItem('chatUsers', JSON.stringify(users))
    
    currentUser.value = { 
      username: newUser.username,
      isAdmin: false
    }
    localStorage.setItem('chatUser', JSON.stringify(currentUser.value))
    authForm.value = { username: '', password: '', confirmPassword: '' }
  }
}

// 退出登录
const logout = () => {
  currentUser.value = null
  localStorage.removeItem('chatUser')
  currentContact.value = null
  currentMessages.value = []
}

// 选择头像
const selectAvatar = (avatarUrl: string) => {
  if (currentUser.value) {
    currentUser.value.avatar = avatarUrl
    localStorage.setItem('chatUser', JSON.stringify(currentUser.value))
    showAvatarSelector.value = false
  }
}

// 上传自定义头像
const uploadAvatar = (event: Event) => {
  const input = event.target as HTMLInputElement
  if (input.files && input.files[0]) {
    const file = input.files[0]
    const reader = new FileReader()
    reader.onload = (e) => {
      if (currentUser.value && e.target?.result) {
        currentUser.value.avatar = e.target.result as string
        localStorage.setItem('chatUser', JSON.stringify(currentUser.value))
        showAvatarSelector.value = false
      }
    }
    reader.readAsDataURL(file)
  }
}

// 联系人数据
const contacts = ref([
  {
    id: 1,
    name: 'AI助手',
    icon: 'fa-solid fa-robot',
    status: '在线',
    unread: 0
  },
  {
    id: 2,
    name: '张工程师',
    icon: 'fa-solid fa-user',
    status: '在线',
    unread: 2
  },
  {
    id: 3,
    name: '李主管',
    icon: 'fa-solid fa-user-tie',
    status: '离线',
    unread: 0
  },
  {
    id: 4,
    name: '运维团队',
    icon: 'fa-solid fa-users',
    status: '在线',
    unread: 1
  },
  {
    id: 5,
    name: '技术支持',
    icon: 'fa-solid fa-headset',
    status: '在线',
    unread: 0
  }
])

// 当前选中的联系人
const currentContact = ref<any>(null)

// 每个联系人的聊天记录
const chatHistory = ref<Record<number, any[]>>({
  1: [
    {
      type: 'bot',
      text: '您好！我是AI助手，有什么可以帮您的吗？',
      time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    }
  ],
  2: [
    {
      type: 'contact',
      text: '你好，白城风场有设备告警，需要查看一下。',
      time: '14:20'
    },
    {
      type: 'contact',
      text: '请尽快处理。',
      time: '14:21'
    }
  ],
  3: [],
  4: [
    {
      type: 'contact',
      text: '今天的巡检报告已经提交了。',
      time: '10:30'
    }
  ],
  5: []
})

// 当前聊天记录
const currentMessages = ref<any[]>([])
const inputMessage = ref('')

// 滚动到底部的函数
const scrollToBottom = () => {
  // 使用多重延迟确保 DOM 完全渲染
  nextTick(() => {
    setTimeout(() => {
      if (chatMessages.value) {
        // 使用 requestAnimationFrame 确保在浏览器重绘后滚动
        requestAnimationFrame(() => {
          if (chatMessages.value) {
            chatMessages.value.scrollTop = chatMessages.value.scrollHeight
            // 再次确保滚动到底部
            setTimeout(() => {
              if (chatMessages.value) {
                chatMessages.value.scrollTop = chatMessages.value.scrollHeight
              }
            }, 100)
          }
        })
      }
    }, 100)
  })
}

// 选择联系人
const selectContact = (contact: any) => {
  currentContact.value = contact
  
  // 如果是 AI 助手，使用全局 store 的消息
  if (contact.id === 1) {
    currentMessages.value = aiChatStore.aiMessages.value
  } else {
    currentMessages.value = chatHistory.value[contact.id] || []
  }
  
  // 清除未读消息
  contact.unread = 0
  
  // 滚动到底部 - 延迟执行确保 DOM 渲染完成
  scrollToBottom()
}

// 监听联系人变化，切换联系人时滚动到底部
watch(() => currentContact.value, () => {
  if (currentContact.value) {
    scrollToBottom()
  }
})

// 监听 AI 消息变化，当选择AI助手时自动同步
watch(() => aiChatStore.aiMessages.value, (newMessages) => {
  if (currentContact.value?.id === 1) {
    currentMessages.value = newMessages
    scrollToBottom()
  }
}, { deep: true })

// 监听当前消息变化，自动滚动到底部
watch(currentMessages, () => {
  if (currentContact.value) {
    scrollToBottom()
  }
}, { deep: true })

// AI 正在输入状态
const isAiTyping = ref(false)

// 发送消息
const sendMessage = async () => {
  if (!inputMessage.value.trim() || !currentContact.value) return
  
  const newMessage = {
    type: 'user' as const,
    text: inputMessage.value,
    time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  
  const userMsg = inputMessage.value
  inputMessage.value = ''
  
  // 如果是 AI 助手，使用全局 store 和 Dify API
  if (currentContact.value.id === 1) {
    aiChatStore.addMessage(newMessage)
    
    // 滚动到底部
    nextTick(() => {
      if (chatMessages.value) {
        chatMessages.value.scrollTop = chatMessages.value.scrollHeight
      }
    })
    
    // 显示 AI 正在输入
    isAiTyping.value = true
    
    // 创建初始的 AI 回复消息（空内容，用于流式更新）
    const replyMessage = {
      type: 'bot' as const,
      text: '',
      time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    }
    
    aiChatStore.addMessage(replyMessage)
    
    // 滚动到底部
    nextTick(() => {
      if (chatMessages.value) {
        chatMessages.value.scrollTop = chatMessages.value.scrollHeight
      }
    })
    
    try {
      // 使用流式 API
      let accumulatedText = ''
      
      await difyService.sendMessageStream(
        userMsg,
        currentUser.value?.username || 'guest',
        (chunk: string) => {
          // 累积文本片段
          accumulatedText += chunk
          // 更新最后一条消息
          aiChatStore.updateLastMessage(accumulatedText)
          
          // 自动滚动到底部
          nextTick(() => {
            if (chatMessages.value) {
              chatMessages.value.scrollTop = chatMessages.value.scrollHeight
            }
          })
        }
      )
      
      // 流式输出完成
      isAiTyping.value = false
      
      // 最终滚动到底部
      nextTick(() => {
        if (chatMessages.value) {
          chatMessages.value.scrollTop = chatMessages.value.scrollHeight
        }
      })
    } catch (error) {
      console.error('AI 回复失败:', error)
      
      // 如果 API 调用失败，更新最后一条消息为错误提示
      aiChatStore.updateLastMessage('抱歉，我暂时无法回答您的问题。请稍后再试。')
      
      nextTick(() => {
        if (chatMessages.value) {
          chatMessages.value.scrollTop = chatMessages.value.scrollHeight
        }
      })
      
      isAiTyping.value = false
    }
  } else {
    // 其他联系人，使用本地聊天历史
    if (!chatHistory.value[currentContact.value.id]) {
      chatHistory.value[currentContact.value.id] = []
      currentMessages.value = chatHistory.value[currentContact.value.id]
    }
    
    chatHistory.value[currentContact.value.id].push(newMessage)
    
    // 滚动到底部
    nextTick(() => {
      if (chatMessages.value) {
        chatMessages.value.scrollTop = chatMessages.value.scrollHeight
      }
    })
  }
}

// 风场数据（吉林省西部郊区坐标）
const windFields = ref([
  { 
    id: 1, 
    name: '长岭风场', 
    turbineCount: 8, 
    status: 'normal', 
    center: [124.150, 44.150],
    zoom: 11
  },
  { 
    id: 2, 
    name: '白城风场', 
    turbineCount: 6, 
    status: 'warning', 
    center: [122.650, 45.750],
    zoom: 11
  },
  { 
    id: 3, 
    name: '通榆风场', 
    turbineCount: 5, 
    status: 'normal', 
    center: [123.250, 44.650],
    zoom: 11
  },
  { 
    id: 4, 
    name: '洮南风场', 
    turbineCount: 4, 
    status: 'normal', 
    center: [122.600, 45.500],
    zoom: 11
  },
  { 
    id: 5, 
    name: '镇赉风场', 
    turbineCount: 2, 
    status: 'normal', 
    center: [123.350, 46.000],
    zoom: 11
  },
])

// 风机数据（根据风场生成周边坐标）
const turbines = ref([
  // 长岭风场（郊区）
  { id: 1, name: '长岭-01', fieldId: 1, position: [124.140, 44.160], power: 2.5, status: 'normal' },
  { id: 2, name: '长岭-02', fieldId: 1, position: [124.150, 44.157], power: 2.5, status: 'normal' },
  { id: 3, name: '长岭-03', fieldId: 1, position: [124.160, 44.154], power: 2.5, status: 'normal' },
  { id: 4, name: '长岭-04', fieldId: 1, position: [124.145, 44.147], power: 2.5, status: 'normal' },
  { id: 5, name: '长岭-05', fieldId: 1, position: [124.155, 44.144], power: 2.5, status: 'normal' },
  { id: 6, name: '长岭-06', fieldId: 1, position: [124.135, 44.142], power: 2.5, status: 'normal' },
  { id: 7, name: '长岭-07', fieldId: 1, position: [124.150, 44.137], power: 2.5, status: 'normal' },
  { id: 8, name: '长岭-08', fieldId: 1, position: [124.165, 44.140], power: 2.5, status: 'normal' },
  
  // 白城风场（郊区）
  { id: 9, name: '白城-01', fieldId: 2, position: [122.640, 45.760], power: 2.5, status: 'warning' },
  { id: 10, name: '白城-02', fieldId: 2, position: [122.650, 45.757], power: 2.5, status: 'normal' },
  { id: 11, name: '白城-03', fieldId: 2, position: [122.660, 45.754], power: 2.5, status: 'normal' },
  { id: 12, name: '白城-04', fieldId: 2, position: [122.645, 45.747], power: 2.5, status: 'warning' },
  { id: 13, name: '白城-05', fieldId: 2, position: [122.655, 45.744], power: 2.5, status: 'normal' },
  { id: 14, name: '白城-06', fieldId: 2, position: [122.650, 45.740], power: 2.5, status: 'normal' },
  
  // 通榆风场（郊区）
  { id: 15, name: '通榆-01', fieldId: 3, position: [123.240, 44.660], power: 2.5, status: 'normal' },
  { id: 16, name: '通榆-02', fieldId: 3, position: [123.250, 44.657], power: 2.5, status: 'normal' },
  { id: 17, name: '通榆-03', fieldId: 3, position: [123.260, 44.654], power: 2.5, status: 'normal' },
  { id: 18, name: '通榆-04', fieldId: 3, position: [123.247, 44.647], power: 2.5, status: 'normal' },
  { id: 19, name: '通榆-05', fieldId: 3, position: [123.257, 44.644], power: 2.5, status: 'normal' },
  
  // 洮南风场（郊区）
  { id: 20, name: '洮南-01', fieldId: 4, position: [122.590, 45.510], power: 2.5, status: 'normal' },
  { id: 21, name: '洮南-02', fieldId: 4, position: [122.600, 45.507], power: 2.5, status: 'normal' },
  { id: 22, name: '洮南-03', fieldId: 4, position: [122.610, 45.504], power: 2.5, status: 'normal' },
  { id: 23, name: '洮南-04', fieldId: 4, position: [122.597, 45.497], power: 2.5, status: 'normal' },
  
  // 镇赉风场（郊区）
  { id: 24, name: '镇赉-01', fieldId: 5, position: [123.340, 46.010], power: 2.5, status: 'normal' },
  { id: 25, name: '镇赉-02', fieldId: 5, position: [123.350, 46.007], power: 2.5, status: 'normal' },
])

const selectedField = ref<number | null>(null)

// 跳转到视频分析页面
const goToVideoAnalysis = () => {
  router.push('/video-analysis')
}

// 初始化离线地图
const initMap = () => {
  if (!L || !mapContainer.value) {
    console.error('Leaflet地图库未加载或容器未找到')
    return
  }

  // 创建地图实例 - 以吉林省西部为中心
  map = L.map('leaflet-map', {
    center: [45.0, 123.5],
    zoom: 8,
    zoomControl: false,
    doubleClickZoom: true,
    boxZoom: false,
    keyboard: true,
    scrollWheelZoom: true,
    dragging: true,
    touchZoom: true
  })

  // 使用高德地图瓦片（国内访问稳定）
  L.tileLayer('https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}', {
    attribution: '高德地图',
    subdomains: ['1', '2', '3', '4'],
    maxZoom: 18
  }).addTo(map)

  // 禁用地图容器的全屏相关事件
  const mapElement = document.getElementById('leaflet-map')
  if (mapElement) {
    mapElement.addEventListener('dblclick', (e) => {
      e.preventDefault()
      e.stopPropagation()
    }, true)
    
    // 阻止可能触发全屏的按键
    mapElement.addEventListener('keydown', (e) => {
      if (e.key === 'f' || e.key === 'F' || e.key === 'F11') {
        e.preventDefault()
        e.stopPropagation()
      }
    }, true)
  }

  // 添加所有风机标记
  addTurbineMarkers()
}

// 添加风机标记
const addTurbineMarkers = () => {
  turbines.value.forEach(turbine => {
    // 提取风机编号（如 "长岭-01" -> "01"）
    const turbineNumber = turbine.name.split('-')[1] || turbine.id.toString().padStart(2, '0')
    
    // 创建自定义图标，包含编号
    const iconHtml = turbine.status === 'warning' 
      ? `<div style="position: relative; width: 40px; height: 50px;">
           <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32" style="position: absolute; top: 0; left: 4px;">
             <circle cx="16" cy="16" r="14" fill="#ff4444" stroke="#ff8888" stroke-width="2"/>
             <text x="16" y="20" text-anchor="middle" fill="white" font-size="16" font-weight="bold">⚠</text>
           </svg>
           <div style="position: absolute; bottom: 0; left: 50%; transform: translateX(-50%); 
                       background: rgba(255, 68, 68, 0.9); color: white; padding: 2px 6px; 
                       border-radius: 4px; font-size: 11px; font-weight: bold; white-space: nowrap;
                       border: 1px solid #ff8888;">${turbineNumber}</div>
         </div>`
      : `<div style="position: relative; width: 40px; height: 50px;">
           <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32" style="position: absolute; top: 0; left: 4px;">
             <circle cx="16" cy="16" r="14" fill="#14b8a6" stroke="#2dd4bf" stroke-width="2"/>
             <path d="M 16 8 L 16 20 M 12 10 L 16 8 L 20 10" stroke="white" stroke-width="2" fill="none"/>
           </svg>
           <div style="position: absolute; bottom: 0; left: 50%; transform: translateX(-50%); 
                       background: rgba(20, 184, 166, 0.9); color: white; padding: 2px 6px; 
                       border-radius: 4px; font-size: 11px; font-weight: bold; white-space: nowrap;
                       border: 1px solid #2dd4bf;">${turbineNumber}</div>
         </div>`

    const customIcon = L.divIcon({
      html: iconHtml,
      className: 'turbine-marker-icon',
      iconSize: [40, 50],
      iconAnchor: [20, 25]
    })

    // 创建标记
    const marker = L.marker([turbine.position[1], turbine.position[0]], { 
      icon: customIcon,
      title: turbine.name
    }).addTo(map)

    // 点击标记进入详情
    marker.on('click', () => {
      enterTurbine(turbine)
    })

    // 绑定弹出框
    const popupContent = `
      <div style="padding: 10px; background: rgba(0, 20, 40, 0.95); border-radius: 8px; color: #fff; min-width: 180px;">
        <h3 style="color: #14b8a6; margin: 0 0 8px 0; font-size: 16px;">${turbine.name}</h3>
        <p style="margin: 4px 0; font-size: 14px;">功率: ${turbine.power}MW</p>
        <p style="margin: 4px 0; font-size: 14px;">状态: ${turbine.status === 'normal' ? '正常运行' : '设备告警'}</p>
        <p style="margin: 8px 0 0 0; color: #5eead4; font-size: 12px;">点击标记查看详情</p>
      </div>
    `
    marker.bindPopup(popupContent)

    markers.push(marker)
  })
}

// 选择风场
const selectField = (fieldId: number) => {
  const field = windFields.value.find(f => f.id === fieldId)
  if (field && map) {
    map.setView([field.center[1], field.center[0]], field.zoom, {
      animate: true,
      duration: 1
    })
    selectedField.value = fieldId
  }
}

// 地图控制
const zoomIn = () => {
  if (map) {
    map.zoomIn()
  }
}

const zoomOut = () => {
  if (map) {
    map.zoomOut()
  }
}

const resetView = () => {
  if (map) {
    map.setView([45.0, 123.5], 8, {
      animate: true,
      duration: 1
    })
    selectedField.value = null
  }
}

// 进入风机详情
const enterTurbine = (turbine: any) => {
  // 获取当前选中的风场信息
  const currentField = windFields.value.find(f => f.id === selectedField.value)
  router.push({
    path: '/monitor',
    query: {
      windField: currentField?.name || '未知风场',
      turbine: turbine.name
    }
  })
}

// 处理卡片点击
const handleCardClick = (type: 'all' | 'warning') => {
  showRandomTurbine(type)
}

// 显示随机风机
const showRandomTurbine = (type: 'all' | 'warning') => {
  
  let targetTurbines = turbines.value
  
  // 如果是告警设备，只选择告警状态的风机
  if (type === 'warning') {
    targetTurbines = turbines.value.filter(t => t.status === 'warning')
  }
  
  
  if (targetTurbines.length === 0) {
    return
  }
  
  // 随机选择一个风机
  const randomIndex = Math.floor(Math.random() * targetTurbines.length)
  const randomTurbine = targetTurbines[randomIndex]
  
  // 找到对应的风场
  const field = windFields.value.find(f => f.id === randomTurbine.fieldId)
  
  
  if (!map) {
    console.error('地图未初始化')
    return
  }
  
  if (map && randomTurbine) {
    // 定位到该风机
    map.setView([randomTurbine.position[1], randomTurbine.position[0]], 13, {
      animate: true,
      duration: 1
    })
    
    // 更新选中的风场
    selectedField.value = randomTurbine.fieldId
    
    // 找到对应的标记并打开弹出框
    const markerIndex = turbines.value.findIndex(t => t.id === randomTurbine.id)
    
    if (markerIndex !== -1 && markers[markerIndex]) {
      setTimeout(() => {
        markers[markerIndex].openPopup()
      }, 1000)
    }
    
    // 在控制台显示信息
  }
}

// 窗口大小改变时调整地图
const handleResize = () => {
  if (map) {
    setTimeout(() => {
      map.invalidateSize()
    }, 100)
  }
}

// 生命周期
onMounted(() => {
  // 初始化管理员账号并自动登录
  initAdminAccount()
  
  // 阻止页面全屏
  document.addEventListener('fullscreenchange', () => {
    if (document.fullscreenElement) {
      document.exitFullscreen()
    }
  })
  
  document.addEventListener('webkitfullscreenchange', () => {
    if ((document as any).webkitFullscreenElement) {
      (document as any).webkitExitFullscreen()
    }
  })

  // 等待Leaflet库加载
  const checkLeaflet = setInterval(() => {
    if (L) {
      clearInterval(checkLeaflet)
      initMap()
    }
  }, 100)

  // 超时处理
  setTimeout(() => {
    clearInterval(checkLeaflet)
    if (!L) {
      console.error('Leaflet地图库加载超时')
    }
  }, 10000)

  // 监听窗口大小变化
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  // 移除窗口监听器
  window.removeEventListener('resize', handleResize)
  
  // 清理标记
  markers.forEach(marker => {
    if (map && marker) {
      map.removeLayer(marker)
    }
  })
  markers = []
  
  // 销毁地图
  if (map) {
    map.remove()
    map = null
  }
})
</script>

<style lang="scss" scoped>
.map-container {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  left: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: linear-gradient(135deg, #0a1628 0%, #1a2642 100%);
}
.map-controls {
  position: fixed;
  top: 120px;
  right: 20px;
  z-index: 1000;
  display: flex;
  flex-direction: column;
  gap: 12px;
  .control-btn {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 52px;
    height: 52px;
    overflow: hidden;
    font-size: 20px;
    color: #fff;
    cursor: pointer;
    background: linear-gradient(135deg, rgba(13, 148, 136, 25%) 0%, rgba(20, 184, 166, 15%) 100%);
    border: 2px solid rgba(94, 234, 212, 50%);
    border-radius: 12px;
    box-shadow: 0 4px 15px rgba(13, 148, 136, 20%), inset 0 1px 0 rgba(255, 255, 255, 10%);
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    backdrop-filter: blur(10px);
    &::before {
      position: absolute;
      top: 50%;
      left: 50%;
      width: 0;
      height: 0;
      content: '';
      background: radial-gradient(circle, rgba(20, 184, 166, 40%) 0%, transparent 70%);
      border-radius: 50%;
      transition: width 0.6s ease, height 0.6s ease;
      transform: translate(-50%, -50%);
    }
    i {
      position: relative;
      z-index: 1;
      transition: transform 0.3s ease;
    }
    &:hover {
      background: linear-gradient(135deg, rgba(13, 148, 136, 40%) 0%, rgba(20, 184, 166, 25%) 100%);
      border-color: #14b8a6;
      box-shadow: 0 6px 25px rgba(20, 184, 166, 40%), inset 0 1px 0 rgba(255, 255, 255, 20%);
      transform: translateX(-8px) scale(1.05);
      &::before {
        width: 100px;
        height: 100px;
      }
      i {
        transform: scale(1.2) rotate(5deg);
      }
    }
    &:active {
      box-shadow: 0 2px 10px rgba(20, 184, 166, 30%);
      transform: translateX(-5px) scale(0.98);
    }
  }
}
.map-header {
  position: relative;
  z-index: 9998;
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: space-between;
  padding: 20px 40px;
  background: linear-gradient(135deg, rgba(13, 148, 136, 15%) 0%, rgba(20, 184, 166, 8%) 50%, rgba(13, 148, 136, 15%) 100%);
  border-bottom: 2px solid rgba(94, 234, 212, 40%);
  box-shadow: 0 4px 20px rgba(13, 148, 136, 15%);
  backdrop-filter: blur(10px);
  .header-left {
    display: flex;
    gap: 20px;
    align-items: center;
    .header-icon {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 60px;
      height: 60px;
      img {
        width: 100%;
        height: 100%;
        object-fit: contain;
      }
      i {
        font-size: 28px;
        color: #14b8a6;
        animation: icon-rotate 20s linear infinite;
      }
    }
    .header-title {
      .cn {
        margin-bottom: 5px;
        font-size: 26px;
        font-weight: bold;
        text-shadow: 0 0 30px rgba(20, 184, 166, 50%);
        background: linear-gradient(135deg, #fff 0%, #14b8a6 50%, #fff 100%);
        background-clip: text;
        -webkit-text-fill-color: transparent;
      }
      .en {
        font-size: 13px;
        font-weight: 500;
        color: #8fb9f5;
        letter-spacing: 1px;
      }
    }
  }
  .header-right {
    display: flex;
    gap: 15px;
    .stats-card {
      position: relative;
      z-index: 10;
      display: flex;
      gap: 12px;
      align-items: center;
      padding: 12px 20px;
      background: linear-gradient(135deg, rgba(13, 148, 136, 15%) 0%, rgba(20, 184, 166, 8%) 100%);
      border: 1px solid rgba(94, 234, 212, 30%);
      border-radius: 10px;
      box-shadow: 0 4px 15px rgba(13, 148, 136, 10%);
      transition: all 0.3s ease;
      &.clickable {
        cursor: pointer;
        user-select: none;
      }
      i {
        font-size: 24px;
        color: #14b8a6;
      }
      .stats-info {
        .stats-value {
          font-size: 20px;
          font-weight: bold;
          line-height: 1.2;
          color: #fff;
        }
        .stats-label {
          margin-top: 2px;
          font-size: 11px;
          color: #8fb9f5;
        }
      }
      &.warning {
        background: linear-gradient(135deg, rgba(255, 68, 68, 15%) 0%, rgba(255, 100, 100, 8%) 100%);
        border-color: rgba(255, 68, 68, 40%);
        i {
          color: #f44;
          animation: warning-pulse 2s ease-in-out infinite;
        }
        .stats-value {
          color: #f66;
        }
      }
      &.video-detection-btn {
        &.active {
          background: linear-gradient(135deg, rgba(20, 184, 166, 25%) 0%, rgba(13, 148, 136, 15%) 100%);
          border-color: #14b8a6;
          box-shadow: 0 4px 20px rgba(20, 184, 166, 30%), inset 0 1px 0 rgba(255, 255, 255, 10%);
          i {
            color: #14b8a6;
            animation: icon-pulse 2s ease-in-out infinite;
          }
        }
      }
      &:hover {
        border-color: rgba(94, 234, 212, 60%);
        box-shadow: 0 6px 20px rgba(13, 148, 136, 20%);
        transform: translateY(-2px);
      }
    }
  }
}

@keyframes icon-pulse {
  0%, 100% {
    box-shadow: 0 4px 15px rgba(20, 184, 166, 30%), inset 0 1px 0 rgba(255, 255, 255, 10%);
  }
  50% {
    box-shadow: 0 4px 25px rgba(20, 184, 166, 60%), inset 0 1px 0 rgba(255, 255, 255, 20%);
  }
}

@keyframes icon-rotate {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

@keyframes warning-pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.6;
  }
}
.map-content {
  display: flex;
  flex: 1;
  gap: 1.5%;
  padding: 1.5%;
  overflow: hidden;
}
.wind-field-list {
  flex: 0 0 18%;
  min-width: 250px;
  padding: 20px;
  overflow-y: auto;
  background: linear-gradient(135deg, rgba(13, 148, 136, 8%) 0%, rgba(20, 184, 166, 3%) 100%);
  border: 1px solid rgba(94, 234, 212, 30%);
  border-radius: 15px;
  box-shadow: 0 4px 20px rgba(13, 148, 136, 10%);
  backdrop-filter: blur(10px);
  &::-webkit-scrollbar {
    width: 6px;
  }
  &::-webkit-scrollbar-track {
    background: rgba(0, 0, 0, 20%);
    border-radius: 3px;
  }
  &::-webkit-scrollbar-thumb {
    background: rgba(20, 184, 166, 40%);
    border-radius: 3px;
    &:hover {
      background: rgba(20, 184, 166, 60%);
    }
  }
  .list-header {
    display: flex;
    gap: 10px;
    align-items: center;
    padding-bottom: 15px;
    margin-bottom: 20px;
    border-bottom: 2px solid rgba(94, 234, 212, 30%);
    i {
      font-size: 18px;
      color: #14b8a6;
    }
    .list-title {
      font-size: 18px;
      font-weight: bold;
      color: #fff;
      background: linear-gradient(135deg, #fff 0%, #14b8a6 100%);
      background-clip: text;
      -webkit-text-fill-color: transparent;
    }
  }
  .field-item {
    position: relative;
    display: flex;
    gap: 12px;
    align-items: center;
    padding: 16px;
    margin-bottom: 12px;
    overflow: hidden;
    cursor: pointer;
    background: linear-gradient(135deg, rgba(13, 148, 136, 10%) 0%, rgba(20, 184, 166, 5%) 100%);
    border: 1px solid rgba(94, 234, 212, 25%);
    border-radius: 10px;
    box-shadow: 0 2px 10px rgba(13, 148, 136, 5%);
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    &::before {
      position: absolute;
      top: 0;
      bottom: 0;
      left: 0;
      width: 3px;
      content: '';
      background: linear-gradient(180deg, #14b8a6 0%, #0d9488 100%);
      transition: transform 0.3s ease;
      transform: scaleY(0);
    }
    .field-icon {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 40px;
      height: 40px;
      font-size: 18px;
      color: #14b8a6;
      background: linear-gradient(135deg, rgba(13, 148, 136, 20%) 0%, rgba(20, 184, 166, 10%) 100%);
      border: 1px solid rgba(20, 184, 166, 30%);
      border-radius: 8px;
      transition: all 0.3s ease;
    }
    .field-content {
      flex: 1;
      .field-name {
        margin-bottom: 6px;
        font-size: 16px;
        font-weight: bold;
        color: #fff;
      }
      .field-info {
        display: flex;
        gap: 15px;
        align-items: center;
        font-size: 12px;
        .turbine-count {
          display: flex;
          gap: 5px;
          align-items: center;
          color: #8fb9f5;
          i {
            font-size: 11px;
          }
        }
        .status {
          display: flex;
          gap: 4px;
          align-items: center;
          padding: 3px 10px;
          font-size: 11px;
          font-weight: 500;
          border-radius: 12px;
          i {
            font-size: 10px;
          }
          &.normal {
            color: #0f8;
            background: rgba(0, 255, 136, 15%);
            border: 1px solid rgba(0, 255, 136, 30%);
          }
          &.warning {
            color: #f66;
            background: rgba(255, 68, 68, 15%);
            border: 1px solid rgba(255, 68, 68, 30%);
            animation: status-blink 2s ease-in-out infinite;
          }
        }
      }
    }
    .field-arrow {
      font-size: 14px;
      color: rgba(255, 255, 255, 30%);
      transition: all 0.3s ease;
    }
    &:hover {
      background: linear-gradient(135deg, rgba(13, 148, 136, 20%) 0%, rgba(20, 184, 166, 10%) 100%);
      border-color: rgba(94, 234, 212, 50%);
      box-shadow: 0 4px 20px rgba(13, 148, 136, 15%);
      transform: translateX(8px);
      &::before {
        transform: scaleY(1);
      }
      .field-icon {
        background: linear-gradient(135deg, rgba(13, 148, 136, 40%) 0%, rgba(20, 184, 166, 20%) 100%);
        border-color: rgba(20, 184, 166, 60%);
        transform: scale(1.1);
      }
      .field-arrow {
        color: #14b8a6;
        transform: translateX(3px);
      }
    }
    &.active {
      background: linear-gradient(135deg, rgba(20, 184, 166, 25%) 0%, rgba(13, 148, 136, 15%) 100%);
      border-color: #14b8a6;
      box-shadow: 0 4px 20px rgba(20, 184, 166, 30%), inset 0 1px 0 rgba(255, 255, 255, 10%);
      &::before {
        transform: scaleY(1);
      }
      .field-icon {
        color: #fff;
        background: linear-gradient(135deg, rgba(20, 184, 166, 50%) 0%, rgba(13, 148, 136, 30%) 100%);
        border-color: #14b8a6;
      }
      .field-arrow {
        color: #14b8a6;
      }
    }
  }
}

@keyframes status-blink {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.6;
  }
}
.map-area {
  position: relative;
  flex: 1;
  overflow: hidden;
  background: rgba(0, 20, 40, 50%);
  border: 2px solid rgba(94, 234, 212, 40%);
  border-radius: 15px;
  box-shadow: 0 4px 30px rgba(13, 148, 136, 15%), inset 0 1px 0 rgba(255, 255, 255, 5%);
  #leaflet-map {
    width: 100%;
    height: 100%;
    border-radius: 13px;
    
    // 防止地图点击时影响页面布局
    &:focus {
      outline: none;
    }
  }
}

// Leaflet 标记图标样式
:deep(.turbine-marker-icon) {
  background: transparent !important;
  border: none !important;
}

// Leaflet 弹出框样式
:deep(.leaflet-popup-content-wrapper) {
  padding: 0;
  background: rgba(0, 20, 40, 95%) !important;
  border: 1px solid rgba(94, 234, 212, 30%);
  border-radius: 8px;
}
:deep(.leaflet-popup-tip) {
  background: rgba(0, 20, 40, 95%) !important;
}
:deep(.leaflet-popup-content) {
  margin: 0;
}

// 响应式设计 - 适应不同窗口大小和缩放级别
@media (max-width: 1600px) {
  .map-header {
    padding: 15px 30px;
    .header-left {
      .header-icon {
        width: 50px;
        height: 50px;
        font-size: 24px;
      }
      .header-title {
        .cn {
          font-size: 22px;
        }
        .en {
          font-size: 12px;
        }
      }
    }
    .header-right {
      gap: 12px;
      .stats-card {
        padding: 10px 16px;
        i {
          font-size: 20px;
        }
        .stats-info {
          .stats-value {
            font-size: 18px;
          }
          .stats-label {
            font-size: 10px;
          }
        }
      }
    }
  }
  .wind-field-list {
    flex: 0 0 20%;
    min-width: 220px;
    padding: 15px;
    .list-header {
      i {
        font-size: 16px;
      }
      .list-title {
        font-size: 16px;
      }
    }
    .field-item {
      padding: 14px;
      .field-icon {
        width: 40px;
        height: 40px;
        font-size: 18px;
      }
      .field-info {
        .field-name {
          font-size: 15px;
        }
        .field-stats {
          font-size: 11px;
        }
      }
    }
  }
}

@media (max-width: 1366px) {
  .map-header {
    padding: 12px 20px;
    .header-left {
      gap: 15px;
      .header-icon {
        width: 45px;
        height: 45px;
        font-size: 20px;
      }
      .header-title {
        .cn {
          font-size: 20px;
        }
        .en {
          font-size: 11px;
        }
      }
    }
    .header-right {
      gap: 10px;
      .stats-card {
        padding: 8px 14px;
        i {
          font-size: 18px;
        }
        .stats-info {
          .stats-value {
            font-size: 16px;
          }
          .stats-label {
            font-size: 9px;
          }
        }
      }
    }
  }
  .map-content {
    gap: 1%;
    padding: 1%;
  }
  .wind-field-list {
    flex: 0 0 22%;
    min-width: 200px;
    padding: 12px;
    .list-header {
      padding-bottom: 12px;
      margin-bottom: 15px;
      i {
        font-size: 15px;
      }
      .list-title {
        font-size: 15px;
      }
    }
    .field-item {
      padding: 12px;
      margin-bottom: 10px;
      .field-icon {
        width: 36px;
        height: 36px;
        font-size: 16px;
      }
      .field-info {
        .field-name {
          font-size: 14px;
        }
        .field-stats {
          font-size: 10px;
        }
      }
    }
  }
}

@media (max-width: 1024px) {
  .map-header {
    flex-wrap: wrap;
    padding: 10px 15px;
    .header-left {
      gap: 12px;
      .header-icon {
        width: 40px;
        height: 40px;
        font-size: 18px;
      }
      .header-title {
        .cn {
          font-size: 18px;
        }
        .en {
          font-size: 10px;
        }
      }
    }
    .header-right {
      gap: 8px;
      .stats-card {
        padding: 6px 12px;
        i {
          font-size: 16px;
        }
        .stats-info {
          .stats-value {
            font-size: 14px;
          }
          .stats-label {
            font-size: 8px;
          }
        }
      }
    }
  }
  .wind-field-list {
    flex: 0 0 25%;
    min-width: 180px;
    padding: 10px;
    .list-header {
      padding-bottom: 10px;
      margin-bottom: 12px;
      i {
        font-size: 14px;
      }
      .list-title {
        font-size: 14px;
      }
    }
    .field-item {
      gap: 10px;
      padding: 10px;
      margin-bottom: 8px;
      .field-icon {
        width: 32px;
        height: 32px;
        font-size: 14px;
      }
      .field-info {
        .field-name {
          font-size: 13px;
        }
        .field-stats {
          font-size: 9px;
        }
      }
    }
  }
}

@media (max-width: 768px) {
  .map-header {
    padding: 8px 12px;
    .header-left {
      gap: 10px;
      .header-icon {
        width: 35px;
        height: 35px;
        font-size: 16px;
      }
      .header-title {
        .cn {
          font-size: 16px;
        }
        .en {
          font-size: 9px;
        }
      }
    }
    .header-right {
      gap: 6px;
      .stats-card {
        padding: 5px 10px;
        i {
          font-size: 14px;
        }
        .stats-info {
          .stats-value {
            font-size: 12px;
          }
          .stats-label {
            font-size: 8px;
          }
        }
      }
    }
  }
  .map-content {
    flex-direction: column;
    gap: 10px;
    padding: 10px;
  }
  .wind-field-list {
    flex: 0 0 auto;
    width: 100%;
    min-width: auto;
    max-height: 200px;
    padding: 10px;
  }
}

// 聊天面板样式 - QQ 风格
.chat-panel {
  display: flex;
  flex: 0 0 420px;
  overflow: hidden;
  background: linear-gradient(135deg, rgba(13, 148, 136, 8%) 0%, rgba(20, 184, 166, 3%) 100%);
  border: 1px solid rgba(94, 234, 212, 30%);
  border-radius: 15px;
  box-shadow: 0 4px 20px rgba(13, 148, 136, 10%);
  backdrop-filter: blur(10px);

  // 登录/注册界面
  .auth-panel {
    display: flex;
    flex: 1;
    align-items: center;
    justify-content: center;
    padding: 30px;
    .auth-card {
      width: 100%;
      max-width: 350px;
      padding: 30px;
      background: linear-gradient(135deg, rgba(13, 148, 136, 12%) 0%, rgba(20, 184, 166, 6%) 100%);
      border: 1px solid rgba(94, 234, 212, 30%);
      border-radius: 15px;
      box-shadow: 0 4px 20px rgba(13, 148, 136, 15%);
      .auth-header {
        display: flex;
        flex-direction: column;
        gap: 10px;
        align-items: center;
        margin-bottom: 25px;
        text-align: center;
        i {
          font-size: 48px;
          color: #14b8a6;
        }
        h3 {
          margin: 0;
          font-size: 24px;
          font-weight: bold;
          color: #fff;
        }
        p {
          margin: 0;
          font-size: 14px;
          color: rgba(255, 255, 255, 60%);
        }
      }
      .auth-form {
        display: flex;
        flex-direction: column;
        gap: 18px;
        .form-group {
          display: flex;
          flex-direction: column;
          gap: 8px;
          label {
            display: flex;
            gap: 8px;
            align-items: center;
            font-size: 14px;
            font-weight: 500;
            color: #fff;
            i {
              font-size: 14px;
              color: #14b8a6;
            }
          }
          input {
            padding: 12px 14px;
            font-size: 14px;
            color: #fff;
            background: rgba(0, 20, 40, 40%);
            border: 1px solid rgba(94, 234, 212, 30%);
            border-radius: 8px;
            outline: none;
            transition: all 0.3s ease;
            &::placeholder {
              color: rgba(255, 255, 255, 40%);
            }
            &:focus {
              background: rgba(0, 20, 40, 60%);
              border-color: #14b8a6;
              box-shadow: 0 0 10px rgba(20, 184, 166, 20%);
            }
          }
        }
        .error-message {
          display: flex;
          gap: 8px;
          align-items: center;
          padding: 10px 14px;
          font-size: 13px;
          color: #ff6b6b;
          background: rgba(255, 107, 107, 10%);
          border: 1px solid rgba(255, 107, 107, 30%);
          border-radius: 8px;
          i {
            font-size: 14px;
          }
        }
        .auth-button {
          padding: 12px;
          font-size: 16px;
          font-weight: bold;
          color: #fff;
          cursor: pointer;
          background: linear-gradient(135deg, rgba(13, 148, 136, 40%) 0%, rgba(20, 184, 166, 30%) 100%);
          border: 1px solid rgba(20, 184, 166, 60%);
          border-radius: 8px;
          transition: all 0.3s ease;
          &:hover {
            background: linear-gradient(135deg, rgba(13, 148, 136, 60%) 0%, rgba(20, 184, 166, 40%) 100%);
            border-color: #14b8a6;
            box-shadow: 0 4px 15px rgba(20, 184, 166, 30%);
            transform: translateY(-2px);
          }
          &:active {
            transform: translateY(0);
          }
        }
        .auth-switch {
          padding-top: 10px;
          font-size: 13px;
          color: rgba(255, 255, 255, 70%);
          text-align: center;
          a {
            color: #14b8a6;
            text-decoration: none;
            cursor: pointer;
            transition: all 0.3s ease;
            &:hover {
              color: #5eead4;
              text-decoration: underline;
            }
          }
        }
      }
    }
  }

  // 左侧联系人列表
  .contact-list {
    display: flex;
    flex: 0 0 140px;
    flex-direction: column;
    background: linear-gradient(135deg, rgba(13, 148, 136, 12%) 0%, rgba(20, 184, 166, 6%) 100%);
    border-right: 1px solid rgba(94, 234, 212, 30%);
    .contact-header {
      display: flex;
      gap: 8px;
      align-items: center;
      justify-content: space-between;
      padding: 15px 12px;
      background: linear-gradient(135deg, rgba(13, 148, 136, 20%) 0%, rgba(20, 184, 166, 10%) 100%);
      border-bottom: 1px solid rgba(94, 234, 212, 30%);
      .user-info {
        display: flex;
        flex: 1;
        flex-direction: column;
        gap: 4px;
        align-items: center;
        .user-avatar-wrapper {
          position: relative;
          cursor: pointer;
          transition: transform 0.3s ease;
          &:hover {
            transform: scale(1.1);
            .avatar-edit-icon {
              opacity: 1;
            }
          }
          i {
            font-size: 40px;
            color: #14b8a6;
          }
          .user-avatar-img {
            width: 40px;
            height: 40px;
            border: 2px solid #14b8a6;
            border-radius: 50%;
            object-fit: cover;
          }
          .avatar-edit-icon {
            position: absolute;
            right: -2px;
            bottom: -2px;
            display: flex;
            align-items: center;
            justify-content: center;
            width: 16px;
            height: 16px;
            font-size: 10px;
            color: #fff;
            background: #14b8a6;
            border: 1px solid rgba(0, 20, 40, 80%);
            border-radius: 50%;
            opacity: 0;
            transition: opacity 0.3s ease;
          }
        }
        span {
          font-size: 12px;
          font-weight: 500;
          color: #fff;
          text-align: center;
          word-break: break-all;
        }
      }
      .logout-btn {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 32px;
        height: 32px;
        padding: 0;
        font-size: 14px;
        color: #fff;
        cursor: pointer;
        background: linear-gradient(135deg, rgba(255, 107, 107, 30%) 0%, rgba(255, 107, 107, 20%) 100%);
        border: 1px solid rgba(255, 107, 107, 40%);
        border-radius: 8px;
        transition: all 0.3s ease;
        &:hover {
          background: linear-gradient(135deg, rgba(255, 107, 107, 50%) 0%, rgba(255, 107, 107, 30%) 100%);
          border-color: #ff6b6b;
          box-shadow: 0 4px 15px rgba(255, 107, 107, 30%);
          transform: translateY(-2px);
        }
        &:active {
          transform: translateY(0);
        }
      }
      i {
        font-size: 16px;
        color: #14b8a6;
      }
      span {
        font-size: 14px;
        font-weight: bold;
        color: #fff;
      }
    }
    .contact-items {
      flex: 1;
      padding: 8px 0;
      overflow-y: auto;
      &::-webkit-scrollbar {
        width: 4px;
      }
      &::-webkit-scrollbar-track {
        background: rgba(0, 0, 0, 20%);
      }
      &::-webkit-scrollbar-thumb {
        background: rgba(20, 184, 166, 40%);
        border-radius: 2px;
        &:hover {
          background: rgba(20, 184, 166, 60%);
        }
      }
      .contact-item {
        display: flex;
        flex-direction: column;
        gap: 6px;
        align-items: center;
        padding: 12px 8px;
        margin: 4px 8px;
        cursor: pointer;
        background: linear-gradient(135deg, rgba(13, 148, 136, 8%) 0%, rgba(20, 184, 166, 4%) 100%);
        border: 1px solid rgba(94, 234, 212, 20%);
        border-radius: 10px;
        transition: all 0.3s ease;
        .contact-avatar {
          position: relative;
          display: flex;
          align-items: center;
          justify-content: center;
          width: 48px;
          height: 48px;
          background: linear-gradient(135deg, rgba(13, 148, 136, 20%) 0%, rgba(20, 184, 166, 10%) 100%);
          border: 2px solid rgba(94, 234, 212, 30%);
          border-radius: 50%;
          i {
            font-size: 20px;
            color: #14b8a6;
          }
          .unread-badge {
            position: absolute;
            top: -4px;
            right: -4px;
            display: flex;
            align-items: center;
            justify-content: center;
            min-width: 18px;
            height: 18px;
            padding: 0 4px;
            font-size: 11px;
            font-weight: bold;
            color: #fff;
            background: linear-gradient(135deg, #f44 0%, #f66 100%);
            border: 2px solid rgba(10, 22, 40, 90%);
            border-radius: 9px;
          }
        }
        .contact-info {
          display: flex;
          flex-direction: column;
          gap: 2px;
          align-items: center;
          width: 100%;
          .contact-name {
            font-size: 12px;
            font-weight: 500;
            color: #fff;
            text-align: center;
          }
          .contact-status {
            font-size: 10px;
            color: rgba(255, 255, 255, 60%);
          }
        }
        &:hover {
          background: linear-gradient(135deg, rgba(13, 148, 136, 15%) 0%, rgba(20, 184, 166, 8%) 100%);
          border-color: rgba(94, 234, 212, 40%);
          transform: translateY(-2px);
        }
        &.active {
          background: linear-gradient(135deg, rgba(20, 184, 166, 25%) 0%, rgba(13, 148, 136, 15%) 100%);
          border-color: #14b8a6;
          box-shadow: 0 4px 15px rgba(20, 184, 166, 30%);
          .contact-avatar {
            background: linear-gradient(135deg, rgba(20, 184, 166, 40%) 0%, rgba(13, 148, 136, 25%) 100%);
            border-color: #14b8a6;
          }
        }
      }
    }
  }

  // 右侧聊天窗口
  .chat-window {
    display: flex;
    flex: 1;
    flex-direction: column;
    .chat-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 15px 20px;
      background: linear-gradient(135deg, rgba(13, 148, 136, 15%) 0%, rgba(20, 184, 166, 8%) 100%);
      border-bottom: 1px solid rgba(94, 234, 212, 30%);
      .chat-title {
        display: flex;
        gap: 10px;
        align-items: center;
        i {
          font-size: 20px;
          color: #14b8a6;
        }
        span {
          font-size: 16px;
          font-weight: bold;
          color: #fff;
        }
      }
      .chat-status {
        font-size: 12px;
        color: rgba(255, 255, 255, 60%);
      }
    }
    .chat-messages {
      display: flex;
      flex: 1;
      flex-direction: column;
      gap: 12px;
      padding: 15px;
      overflow-y: auto;
      &::-webkit-scrollbar {
        width: 6px;
      }
      &::-webkit-scrollbar-track {
        background: rgba(0, 0, 0, 20%);
        border-radius: 3px;
      }
      &::-webkit-scrollbar-thumb {
        background: rgba(20, 184, 166, 40%);
        border-radius: 3px;
        &:hover {
          background: rgba(20, 184, 166, 60%);
        }
      }
      .empty-chat {
        display: flex;
        flex: 1;
        flex-direction: column;
        gap: 15px;
        align-items: center;
        justify-content: center;
        color: rgba(255, 255, 255, 40%);
        i {
          font-size: 48px;
          color: rgba(20, 184, 166, 30%);
        }
        p {
          font-size: 14px;
        }
      }
      .message {
      display: flex;
      gap: 10px;
      animation: message-slide 0.3s ease;
      &.user {
        flex-direction: row-reverse;
        .message-avatar {
          background: linear-gradient(135deg, rgba(20, 184, 166, 30%) 0%, rgba(13, 148, 136, 20%) 100%);
        }
        .message-content {
          align-items: flex-end;
          .message-text {
            background: linear-gradient(135deg, rgba(20, 184, 166, 20%) 0%, rgba(13, 148, 136, 15%) 100%);
            border-color: rgba(20, 184, 166, 40%);
          }
        }
      }
      &.bot {
        .message-avatar {
          background: linear-gradient(135deg, rgba(94, 234, 212, 30%) 0%, rgba(13, 148, 136, 20%) 100%);
        }
      }
      .message-avatar {
        display: flex;
        flex-shrink: 0;
        align-items: center;
        justify-content: center;
        width: 36px;
        height: 36px;
        border: 1px solid rgba(94, 234, 212, 30%);
        border-radius: 50%;
        i {
          font-size: 16px;
          color: #fff;
        }
      }
      .message-content {
        display: flex;
        flex: 1;
        flex-direction: column;
        gap: 4px;
        max-width: 70%;
        .message-location {
          display: flex;
          gap: 4px;
          align-items: center;
          padding: 0 4px;
          font-size: 11px;
          color: rgba(20, 184, 166, 80%);
          i {
            font-size: 10px;
          }
        }
        .message-text {
          padding: 10px 14px;
          font-size: 14px;
          line-height: 1.5;
          color: #fff;
          word-wrap: break-word;
          background: linear-gradient(135deg, rgba(13, 148, 136, 10%) 0%, rgba(20, 184, 166, 5%) 100%);
          border: 1px solid rgba(94, 234, 212, 25%);
          border-radius: 10px;
        }
        .message-time {
          padding: 0 4px;
          font-size: 11px;
          color: rgba(255, 255, 255, 50%);
        }
      }
    }
    }
    .chat-input {
      display: flex;
      gap: 10px;
      padding: 15px;
      background: linear-gradient(135deg, rgba(13, 148, 136, 8%) 0%, rgba(20, 184, 166, 3%) 100%);
      border-top: 1px solid rgba(94, 234, 212, 30%);
      input {
      flex: 1;
      padding: 10px 14px;
      font-size: 14px;
      color: #fff;
      background: rgba(0, 20, 40, 40%);
      border: 1px solid rgba(94, 234, 212, 30%);
      border-radius: 8px;
      outline: none;
      transition: all 0.3s ease;
      &::placeholder {
        color: rgba(255, 255, 255, 40%);
      }
      &:focus {
        background: rgba(0, 20, 40, 60%);
        border-color: #14b8a6;
        box-shadow: 0 0 10px rgba(20, 184, 166, 20%);
      }
    }
    button {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 40px;
      height: 40px;
      font-size: 16px;
      color: #fff;
      cursor: pointer;
      background: linear-gradient(135deg, rgba(13, 148, 136, 30%) 0%, rgba(20, 184, 166, 20%) 100%);
      border: 1px solid rgba(20, 184, 166, 50%);
      border-radius: 8px;
      transition: all 0.3s ease;
      &:hover:not(:disabled) {
        background: linear-gradient(135deg, rgba(13, 148, 136, 50%) 0%, rgba(20, 184, 166, 30%) 100%);
        border-color: #14b8a6;
        box-shadow: 0 4px 15px rgba(20, 184, 166, 30%);
        transform: translateY(-2px);
      }
      &:active:not(:disabled) {
        transform: translateY(0);
      }
      &:disabled {
        cursor: not-allowed;
        opacity: 0.5;
      }
    }
    }
  }
}

@keyframes message-slide {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

// 头像选择器弹窗样式
.avatar-selector-overlay {
  position: fixed;
  top: 0;
  left: 0;
  z-index: 10000;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 60%);
  backdrop-filter: blur(5px);
  .avatar-selector-modal {
    width: 500px;
    max-width: 90%;
    max-height: 80vh;
    overflow: hidden;
    background: linear-gradient(135deg, rgba(0, 20, 40, 95%) 0%, rgba(0, 30, 50, 95%) 100%);
    border: 1px solid rgba(94, 234, 212, 40%);
    border-radius: 15px;
    box-shadow: 0 10px 40px rgba(13, 148, 136, 30%);
    .modal-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 20px;
      background: linear-gradient(135deg, rgba(13, 148, 136, 20%) 0%, rgba(20, 184, 166, 10%) 100%);
      border-bottom: 1px solid rgba(94, 234, 212, 30%);
      h3 {
        margin: 0;
        font-size: 18px;
        font-weight: 600;
        color: #fff;
      }
      .close-btn {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 32px;
        height: 32px;
        padding: 0;
        font-size: 16px;
        color: #fff;
        cursor: pointer;
        background: rgba(255, 255, 255, 10%);
        border: 1px solid rgba(255, 255, 255, 20%);
        border-radius: 8px;
        transition: all 0.3s ease;
        &:hover {
          background: rgba(255, 107, 107, 30%);
          border-color: rgba(255, 107, 107, 50%);
        }
      }
    }
    .modal-content {
      max-height: calc(80vh - 140px);
      padding: 20px;
      overflow-y: auto;
      .avatar-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(80px, 1fr));
        gap: 15px;
        margin-bottom: 20px;
        .avatar-option {
          position: relative;
          cursor: pointer;
          transition: all 0.3s ease;
          img {
            width: 100%;
            height: 80px;
            border: 2px solid rgba(94, 234, 212, 30%);
            border-radius: 50%;
            object-fit: cover;
            transition: all 0.3s ease;
          }
          &:hover img {
            border-color: rgba(20, 184, 166, 60%);
            box-shadow: 0 4px 15px rgba(20, 184, 166, 40%);
            transform: scale(1.1);
          }
          &.active img {
            border-color: #14b8a6;
            border-width: 3px;
            box-shadow: 0 0 20px rgba(20, 184, 166, 60%);
          }
          &.active::after {
            position: absolute;
            top: 0;
            right: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            width: 24px;
            height: 24px;
            font-family: 'Font Awesome 6 Free';
            font-size: 12px;
            font-weight: 900;
            color: #fff;
            content: '\f00c';
            background: #14b8a6;
            border: 2px solid rgba(0, 20, 40, 80%);
            border-radius: 50%;
          }
        }
      }
      .upload-section {
        padding-top: 20px;
        border-top: 1px solid rgba(94, 234, 212, 20%);
        .upload-btn {
          display: flex;
          gap: 10px;
          align-items: center;
          justify-content: center;
          width: 100%;
          padding: 12px 20px;
          font-size: 14px;
          font-weight: 500;
          color: #fff;
          cursor: pointer;
          background: linear-gradient(135deg, rgba(13, 148, 136, 20%) 0%, rgba(20, 184, 166, 15%) 100%);
          border: 1px solid rgba(20, 184, 166, 40%);
          border-radius: 8px;
          transition: all 0.3s ease;
          &:hover {
            background: linear-gradient(135deg, rgba(13, 148, 136, 35%) 0%, rgba(20, 184, 166, 25%) 100%);
            border-color: rgba(20, 184, 166, 60%);
            box-shadow: 0 4px 15px rgba(20, 184, 166, 30%);
            transform: translateY(-2px);
          }
          i {
            font-size: 16px;
          }
        }
      }
    }
  }
}
</style>
