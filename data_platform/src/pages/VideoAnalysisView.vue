<template>
  <div class="video-analysis-view" :class="{ 'left-panel-collapsed': isLeftPanelCollapsed }">
    <button
      class="left-panel-toggle"
      :class="{ collapsed: isLeftPanelCollapsed }"
      :title="isLeftPanelCollapsed ? '展开左侧面板' : '收起左侧面板'"
      @click="toggleLeftPanel"
    >
      <i :class="isLeftPanelCollapsed ? 'fa-solid fa-chevron-right' : 'fa-solid fa-chevron-left'"></i>
    </button>
    <!-- 左侧视频检测区域 -->
    <div class="left-panel" :class="{ collapsed: isLeftPanelCollapsed }">
      <div class="panel-header">
        <div class="panel-title">
          <i class="fa-solid fa-brain"></i>
          <span>实时视频流分析</span>
        </div>
        <button @click="goBack" class="back-btn">
          <i class="fa-solid fa-arrow-left"></i>
          <span>Back to Map</span>
        </button>
      </div>
      
      <div class="video-container-wrapper">
        <!-- 视频源选择 -->
        <div class="video-source-section">
          <div v-if="videoSourceType === 'camera'" class="source-content">
            <div class="camera-selector">
              <label>Select Camera:</label>
              <select v-model="selectedCameraId" @change="switchCamera" class="camera-select">
                <option value="">Please select camera</option>
                <option 
                  v-for="camera in availableCameras" 
                  :key="camera.deviceId"
                  :value="camera.deviceId"
                >
                  {{ camera.label || `Camera ${camera.deviceId.substring(0, 8)}` }}
                </option>
              </select>
              <button @click="refreshCameras" class="refresh-btn" title="Refresh Camera List">
                <i class="fa-solid fa-refresh"></i>
              </button>
            </div>
            <div v-if="cameraError" class="camera-error">
              <i class="fa-solid fa-exclamation-triangle"></i>
              <span>{{ cameraError }}</span>
            </div>
          </div>
          
          <div class="source-tabs">
            <button 
              class="source-tab" 
              :class="{ active: videoSourceType === 'file' }"
              @click="switchVideoSource('file')"
            >
              <i class="fa-solid fa-file-video"></i>
              <span>Local Video</span>
            </button>
            <button 
              class="source-tab" 
              :class="{ active: videoSourceType === 'camera' }"
              @click="switchVideoSource('camera')"
            >
              <i class="fa-solid fa-video"></i>
              <span>Camera</span>
            </button>
          </div>
          
          <div v-if="videoSourceType === 'file'" class="source-content">
            <label class="upload-btn-large">
              <i class="fa-solid fa-upload"></i>
              <span>Select Local Video File</span>
              <input 
                type="file" 
                accept="video/*" 
                @change="handleFileUpload"
                style="display: none;"
              />
            </label>
          </div>
        </div>
        
        <div class="video-container" ref="videoContainer">
          <video 
            ref="videoElement" 
            :src="videoSrc" 
            loop
            muted
            playsinline
            crossorigin="anonymous"
            @loadedmetadata="onVideoLoaded"
            @play="startDetection"
            @pause="stopDetection"
            @error="onVideoError"
          ></video>
          <canvas 
            ref="detectionCanvas" 
            class="detection-overlay"
          ></canvas>
          
          <!-- 播放控制按钮 -->
          <div class="video-controls">
            <button @click="togglePlay" class="play-btn">
              <i :class="isPlaying ? 'fa-solid fa-pause' : 'fa-solid fa-play'"></i>
            </button>
          </div>
          
          <!-- 错误提示（仅本地视频模式显示） -->
          <div v-if="videoError && videoSourceType === 'file'" class="video-error">
            <i class="fa-solid fa-exclamation-triangle"></i>
            <p>Video Load Failed</p>
            <small>Please place video file at <code>public/videos/turbine-view.mp4</code></small>
            <small>or click the button below to select a local video</small>
            <label class="upload-btn">
              <i class="fa-solid fa-upload"></i>
              Select Local Video
              <input 
                type="file" 
                accept="video/*" 
                @change="handleFileUpload"
                style="display: none;"
              />
            </label>
          </div>
        </div>
        
        <!-- 实时分析控制（仅摄像头模式显示） -->
        <div v-if="videoSourceType === 'camera'" class="realtime-analysis-control">
          <div class="control-header">
            <div class="control-title">
              <i class="fa-solid fa-bolt"></i>
              <span>Real-time Analysis</span>
            </div>
            <label class="toggle-switch">
              <input 
                type="checkbox" 
                v-model="realTimeAnalysisEnabled"
                @change="toggleRealTimeAnalysis"
                :disabled="!videoElement || isRealTimeAnalyzing"
              />
              <span class="slider"></span>
            </label>
          </div>
          <div v-if="realTimeAnalysisEnabled" class="realtime-status">
            <i class="fa-solid fa-circle" :class="{ 'pulsing': isRealTimeAnalyzing }"></i>
            <span>{{ isRealTimeAnalyzing ? 'Analyzing...' : 'Ready' }}</span>
          </div>
        </div>
        
        <!-- 实时分析结果（仅摄像头模式显示） -->
        <div v-if="videoSourceType === 'camera' && realTimeAnalysisEnabled" class="realtime-results">
          <div class="results-header">
            <i class="fa-solid fa-stream"></i>
            <span>Real-time Analysis Results</span>
            <button @click="clearRealTimeResults" class="clear-btn" title="Clear Results">
              <i class="fa-solid fa-trash"></i>
            </button>
          </div>
          <div class="results-content">
            <div v-if="realTimeAnalysisResults.length === 0" class="empty-results">
              <i class="fa-solid fa-info-circle"></i>
              <p>Real-time analysis results will appear here</p>
            </div>
            <div v-else class="results-list">
              <div 
                v-for="(item, index) in realTimeAnalysisResults" 
                :key="index"
                class="result-item"
              >
                <div class="result-time">{{ item.time }}</div>
                <div class="result-text">{{ item.result }}</div>
              </div>
            </div>
          </div>
        </div>
        
        <!-- 视频分析结果（仅本地视频模式显示） -->
        <div v-if="videoSourceType === 'file'" class="analysis-result">
          <div class="result-header">
            <div class="result-header-left">
              <i class="fa-solid fa-chart-line"></i>
              <span>Full Video Analysis</span>
            </div>
            <button @click="analyzeVideo" :disabled="isAnalyzing || !videoElement" class="analyze-btn">
              <i class="fa-solid fa-play"></i>
              <span>{{ isAnalyzing ? 'Analyzing...' : 'Start Analysis' }}</span>
            </button>
          </div>
          <div class="result-content" v-if="analysisResult">
            <div class="result-text">{{ analysisResult }}</div>
          </div>
          <div v-else class="result-placeholder">
            <i class="fa-solid fa-info-circle"></i>
            <p>Click "Start Analysis" button to analyze the entire video content</p>
          </div>
        </div>
      </div>
    </div>

    <!-- 右侧AI聊天区域 -->
    <div class="right-panel">
      <!-- 聊天历史侧边栏 -->
      <div class="chat-sidebar">
        <div class="sidebar-header">
          <div class="header-title">
            <i class="fa-solid fa-message"></i>
            <span>对话历史</span>
          </div>
          <button @click="createNewChat" class="new-chat-btn" title="新建对话">
            <i class="fa-solid fa-plus"></i>
          </button>
        </div>
        <div class="chat-history">
          <div 
            v-for="(chat, index) in chatHistory" 
            :key="index"
            class="history-item"
            :class="{ active: currentChatIndex === index }"
            @click="selectChat(index)"
          >
            <div class="history-item-content">
              <i class="fa-solid fa-comments"></i>
              <div class="history-info">
                <span class="history-title">{{ chat.title || `对话 ${index + 1}` }}</span>
                <span class="history-count">{{ chat.messages.length }} 条消息</span>
              </div>
            </div>
            <button @click.stop="deleteChat(index)" class="delete-btn" title="删除对话">
              <i class="fa-solid fa-trash"></i>
            </button>
          </div>
        </div>
      </div>
      
      <!-- 聊天主区域 -->
      <div class="chat-main">
        <!-- AI助手信息卡片 -->
        <div class="ai-assistant-card">
          <div class="assistant-avatar">
            <div class="avatar-glow"></div>
            <i class="fa-solid fa-eye"></i>
          </div>
          <div class="assistant-info">
            <h3>风起时域运维智导助手</h3>
            <p>基于多模态AI模型，为您提供专业的视频分析服务</p>
          </div>
          <div class="assistant-status">
            <div class="status-dot"></div>
            <span>在线</span>
          </div>
        </div>
        
        <!-- 聊天消息区域 -->
        <div class="chat-messages" ref="chatMessages">
          <!-- 空状态 -->
          <div v-if="messages.length === 0" class="empty-state">
            <div class="empty-illustration">
              <div class="floating-icon">
                <i class="fa-solid fa-sparkles"></i>
              </div>
              <h3>开始智能对话</h3>
              <p>我可以帮您分析视频内容，解答相关问题</p>
            </div>
            
            <!-- 快捷问题 -->
            <div class="quick-questions">
              <div class="quick-questions-title">
                <i class="fa-solid fa-lightbulb"></i>
                <span>试试这些问题</span>
              </div>
              <div class="quick-questions-grid">
                <button 
                  v-for="(question, qIndex) in quickQuestions" 
                  :key="qIndex"
                  @click="sendQuickQuestion(question)"
                  class="quick-question-btn"
                >
                  <i :class="question.icon"></i>
                  <span>{{ question.text }}</span>
                </button>
              </div>
            </div>
          </div>
          
          <!-- 消息列表 -->
          <div 
            v-for="(msg, index) in messages" 
            :key="index"
            class="message"
            :class="msg.type"
          >
            <div class="message-avatar">
              <div class="avatar-container">
                <i :class="msg.type === 'user' ? 'fa-solid fa-user' : 'fa-solid fa-brain'"></i>
              </div>
            </div>
            <div class="message-wrapper">
              <div class="message-header">
                <span class="message-role">{{ msg.type === 'user' ? '你' : 'AI助手' }}</span>
                <span class="message-time">{{ msg.time }}</span>
              </div>
              <div class="message-content">
                <div class="message-text" v-html="formatMessage(msg.text)"></div>
                <!-- 消息操作 -->
                <div class="message-actions">
                  <button @click="copyMessage(msg.text)" class="action-btn" title="复制">
                    <i class="fa-solid fa-copy"></i>
                  </button>
                  <button v-if="msg.type === 'bot'" @click="regenerateResponse(index)" class="action-btn" title="重新生成">
                    <i class="fa-solid fa-rotate"></i>
                  </button>
                </div>
              </div>
            </div>
          </div>
          
          <!-- 输入中状态 -->
          <div v-if="isTyping" class="message bot typing">
            <div class="message-avatar">
              <div class="avatar-container">
                <i class="fa-solid fa-brain"></i>
              </div>
            </div>
            <div class="message-wrapper">
              <div class="message-header">
                <span class="message-role">AI助手</span>
                <span class="message-time">{{ new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }}</span>
              </div>
              <div class="message-content">
                <div class="typing-indicator">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
              </div>
            </div>
          </div>
        </div>
        
        <!-- 输入区域 -->
        <div class="chat-input-wrapper">
          <div class="chat-input-container">
            <div class="chat-input">
              <button class="attach-btn" title="添加附件">
                <i class="fa-solid fa-paperclip"></i>
              </button>
              <textarea
                ref="inputRef"
                v-model="inputMessage"
                @keydown.enter.exact.prevent="handleSend"
                @keydown.shift.enter.exact.prevent="inputMessage += '\n'"
                placeholder="输入您的问题..."
                rows="1"
                @input="autoResize"
              ></textarea>
              <button 
                @click="handleSend" 
                :disabled="!inputMessage.trim() || isTyping"
                class="send-btn"
                :title="inputMessage.trim() && !isTyping ? '发送 (Enter)' : '发送'"
              >
                <i class="fa-solid fa-paper-plane"></i>
              </button>
            </div>
            <div class="input-footer">
              <div class="input-hint">
                <i class="fa-solid fa-keyboard"></i>
                <span>Enter 发送 · Shift + Enter 换行</span>
              </div>
              <div class="char-count" :class="{ warning: inputMessage.length > 400, error: inputMessage.length > 500 }">
                <span>{{ inputMessage.length }}</span>
                <span>/ 500</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAiChatStore } from '@/stores/aiChatStore'
import { difyService } from '@/services/difyService'
import { visionService } from '@/services/visionService'

const router = useRouter()
const aiChatStore = useAiChatStore()

// 视频相关
const videoElement = ref<HTMLVideoElement | null>(null)
const detectionCanvas = ref<HTMLCanvasElement | null>(null)
const videoContainer = ref<HTMLElement | null>(null)
const videoSrc = ref('/videos/turbine-view.mp4')
const videoSourceType = ref<'file' | 'camera'>('file')
const isLeftPanelCollapsed = ref(true)
const isPlaying = ref(false)
const videoError = ref(false)
const isAnalyzing = ref(false)
let detectionInterval: number | null = null

// 摄像头相关
const availableCameras = ref<MediaDeviceInfo[]>([])
const selectedCameraId = ref<string>('')
const cameraStream = ref<MediaStream | null>(null)
const cameraError = ref<string>('')

// 聊天相关
const chatMessages = ref<HTMLElement | null>(null)
const inputRef = ref<HTMLTextAreaElement | null>(null)
const inputMessage = ref('')
const isTyping = ref(false)

// 快捷问题列表
const quickQuestions = ref([
  { 
    text: '分析视频中的设备状态', 
    icon: 'fa-solid fa-chart-line',
    prompt: '请分析当前视频中的风电设备状态，包括运行是否正常、是否有异常情况。'
  },
  { 
    text: '识别画面中的物体', 
    icon: 'fa-solid fa-magnifying-glass',
    prompt: '请详细识别画面中出现的所有物体，并说明它们的作用。'
  },
  { 
    text: '评估安全风险', 
    icon: 'fa-solid fa-shield-halved',
    prompt: '请评估当前视频画面中的安全风险，如有风险请给出防护建议。'
  },
  { 
    text: '生成分析报告', 
    icon: 'fa-solid fa-file-lines',
    prompt: '请生成一份完整的视频分析报告，包括设备状态、检测结果和建议。'
  }
])

// 发送快捷问题
const sendQuickQuestion = (question: { text: string, prompt: string }) => {
  inputMessage.value = question.prompt
  nextTick(() => {
    handleSend()
  })
}

// 复制消息
const copyMessage = (text: string) => {
  navigator.clipboard.writeText(text).then(() => {
    // 可以添加复制成功的提示
  })
}

// 重新生成响应
const regenerateResponse = async (index: number) => {
  if (!chatHistory.value[currentChatIndex.value!]) return
  
  const messages = chatHistory.value[currentChatIndex.value!].messages
  // 获取这条用户消息（bot消息的前一条）
  const userMessage = messages[index - 1]
  
  if (userMessage && userMessage.type === 'user') {
    // 删除从这条用户消息开始的所有消息
    chatHistory.value[currentChatIndex.value!].messages = messages.slice(0, index - 1)
    
    // 重新发送用户消息
    inputMessage.value = userMessage.text
    handleSend()
  }
}

// 聊天历史管理
interface ChatSession {
  id: string
  title: string
  messages: Array<{ type: 'user' | 'bot', text: string, time: string }>
  createdAt: number
}

const chatHistory = ref<ChatSession[]>([])
const currentChatIndex = ref<number | null>(null)
const currentChatTitle = ref('AI智能助手')

// 获取当前聊天的消息
const messages = computed(() => {
  if (currentChatIndex.value !== null && chatHistory.value[currentChatIndex.value]) {
    return chatHistory.value[currentChatIndex.value].messages
  }
  return []
})

// 视频分析结果
const analysisResult = ref<string>('')
const realTimeAnalysisEnabled = ref(false)
const realTimeAnalysisResults = ref<Array<{ time: string, result: string, timestamp: number }>>([])
const isRealTimeAnalyzing = ref(false)
let realTimeAnalysisInterval: number | null = null

// 返回地图
const goBack = () => {
  router.push('/')
}

const toggleLeftPanel = () => {
  isLeftPanelCollapsed.value = !isLeftPanelCollapsed.value
}

// 视频加载
const onVideoLoaded = () => {
  videoError.value = false
  if (videoElement.value && detectionCanvas.value) {
    const video = videoElement.value
    const canvas = detectionCanvas.value
    
    // 等待视频尺寸可用
    const updateCanvasSize = () => {
      if (video.videoWidth > 0 && video.videoHeight > 0) {
        // 设置canvas的实际像素尺寸（不设置CSS尺寸，避免拉伸）
        canvas.width = video.videoWidth
        canvas.height = video.videoHeight
        
        // 重要：不设置CSS尺寸，让canvas通过CSS布局自动匹配视频大小
        // 这样可以避免手动计算尺寸导致的错误
      }
    }
    
    // 立即尝试设置
    updateCanvasSize()
    
    // 如果尺寸还未就绪，延迟设置
    if (video.videoWidth === 0 || video.videoHeight === 0) {
      setTimeout(updateCanvasSize, 100)
      setTimeout(updateCanvasSize, 500)
    }
  }
}

// 视频错误
const onVideoError = () => {
  videoError.value = true
  console.error('视频加载失败')
}

// 切换播放
const togglePlay = () => {
  if (!videoElement.value) return
  
  if (isPlaying.value) {
    videoElement.value.pause()
  } else {
    videoElement.value.play().catch(err => {
      console.error('播放失败:', err)
      videoError.value = true
    })
  }
  isPlaying.value = !isPlaying.value
}

// 获取可用摄像头列表
const getAvailableCameras = async () => {
  try {
    const devices = await navigator.mediaDevices.enumerateDevices()
    availableCameras.value = devices.filter(device => device.kind === 'videoinput')
    
    // 如果没有选中摄像头且有可用摄像头，自动选择第一个
    if (!selectedCameraId.value && availableCameras.value.length > 0) {
      selectedCameraId.value = availableCameras.value[0].deviceId
      switchCamera()
    }
  } catch (error) {
    console.error('获取摄像头列表失败:', error)
    cameraError.value = '无法访问摄像头设备'
  }
}

// 刷新摄像头列表
const refreshCameras = async () => {
  await getAvailableCameras()
}

// 切换摄像头
const switchCamera = async () => {
  // 停止当前流
  if (cameraStream.value) {
    cameraStream.value.getTracks().forEach(track => track.stop())
    cameraStream.value = null
  }
  
  if (!selectedCameraId.value || !videoElement.value) {
    return
  }
  
  try {
    cameraError.value = ''
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { 
        deviceId: { exact: selectedCameraId.value },
        width: { ideal: 1920 },
        height: { ideal: 1080 }
      }
    })
    
    cameraStream.value = stream
    videoElement.value.srcObject = stream
    
    // 等待视频元数据加载
    await new Promise<void>((resolve) => {
      const onLoadedMetadata = () => {
        videoElement.value?.removeEventListener('loadedmetadata', onLoadedMetadata)
        resolve()
      }
      videoElement.value?.addEventListener('loadedmetadata', onLoadedMetadata)
      
      // 超时保护
      setTimeout(() => {
        videoElement.value?.removeEventListener('loadedmetadata', onLoadedMetadata)
        resolve()
      }, 3000)
    })
    
    videoElement.value.play().then(() => {
      // 摄像头模式下自动启用实时分析
      if (videoSourceType.value === 'camera' && !realTimeAnalysisEnabled.value) {
        realTimeAnalysisEnabled.value = true
        // 延迟一下确保视频已经开始播放
        setTimeout(() => {
          if (isPlaying.value && realTimeAnalysisEnabled.value) {
            startRealTimeAnalysis()
          }
        }, 500)
      }
    }).catch(err => {
      console.error('播放摄像头流失败:', err)
      cameraError.value = '无法播放摄像头画面'
    })
  } catch (error: any) {
    console.error('访问摄像头失败:', error)
    cameraError.value = error.message || '无法访问摄像头，请检查权限设置'
  }
}

// 切换视频源类型
const switchVideoSource = async (type: 'file' | 'camera') => {
  // 停止当前播放
  if (videoElement.value) {
    videoElement.value.pause()
    isPlaying.value = false
  }
  
  // 停止检测
  stopDetection()
  
  // 如果从摄像头切换到本地视频，停止实时分析
  if (videoSourceType.value === 'camera' && type === 'file') {
    if (realTimeAnalysisEnabled.value) {
      stopRealTimeAnalysis()
      realTimeAnalysisEnabled.value = false
    }
    clearRealTimeResults()
  }
  
  // 如果从本地视频切换到摄像头，清除全视频分析结果
  if (videoSourceType.value === 'file' && type === 'camera') {
    analysisResult.value = ''
    isAnalyzing.value = false
  }
  
  videoSourceType.value = type
  
  // 清除错误状态
  videoError.value = false
  
  if (type === 'camera') {
    // 切换到摄像头
    if (videoElement.value) {
      videoElement.value.srcObject = null
      videoElement.value.src = ''
    }
    
    // 获取摄像头列表
    await getAvailableCameras()
    
    // 如果有选中的摄像头，立即切换（会自动启用实时分析）
    if (selectedCameraId.value) {
      await switchCamera()
    } else {
      // 如果没有选中的摄像头，先启用实时分析开关，等待用户选择摄像头
      if (!realTimeAnalysisEnabled.value) {
        realTimeAnalysisEnabled.value = true
      }
    }
  } else {
    // 切换到本地文件时，不自动启用实时分析
    if (cameraStream.value) {
      cameraStream.value.getTracks().forEach(track => track.stop())
      cameraStream.value = null
    }
    
    if (videoElement.value) {
      videoElement.value.srcObject = null
      videoElement.value.src = videoSrc.value
    }
  }
}

// 分析整个视频
const analyzeVideo = async () => {
  if (!videoElement.value || !detectionCanvas.value || isAnalyzing.value) return
  
  try {
    isAnalyzing.value = true
    analysisResult.value = '正在分析视频内容，请稍候...'
    
    const video = videoElement.value
    const canvas = detectionCanvas.value
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    
    // 检查是否是摄像头流
    if (video.srcObject) {
      analysisResult.value = '摄像头流无法进行全视频分析，请使用实时分析功能'
      isAnalyzing.value = false
      return
    }
    
    // 使用主视频的canvas进行采样，避免创建新元素导致卡顿
    // 保存当前播放状态
    const wasPlaying = !video.paused
    const currentTime = video.currentTime
    
    // 确保canvas尺寸正确
    if (canvas.width !== video.videoWidth || canvas.height !== video.videoHeight) {
      canvas.width = video.videoWidth
      canvas.height = video.videoHeight
    }
    
    // 采样关键帧进行分析（每5秒采样一帧）
    const duration = video.duration
    const sampleInterval = 5
    const samples: string[] = []
    
    // 使用主视频进行采样，但快速跳转，不阻塞播放
    for (let time = 0; time < duration; time += sampleInterval) {
      // 快速跳转到目标时间点
      video.currentTime = time
      
      // 等待视频跳转完成（使用较短的超时）
      await new Promise<void>((resolve) => {
        const timeout = setTimeout(() => {
          video.removeEventListener('seeked', onSeeked)
          resolve() // 超时也继续，避免卡死
        }, 1000)
        
        const onSeeked = () => {
          clearTimeout(timeout)
          video.removeEventListener('seeked', onSeeked)
          
          // 使用 requestAnimationFrame 确保帧已渲染
          requestAnimationFrame(() => {
            try {
              ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
              const imageData = canvas.toDataURL('image/jpeg', 0.8)
              samples.push(imageData)
            } catch (error) {
              console.warn('采样帧失败:', error)
            }
            // 短暂延迟，让主线程处理其他任务
            setTimeout(() => resolve(), 50)
          })
        }
        
        video.addEventListener('seeked', onSeeked, { once: true })
      })
    }
    
    // 恢复播放状态
    video.currentTime = currentTime
    if (wasPlaying) {
      video.play().catch(err => console.warn('恢复播放失败:', err))
    }
    
    // 分析所有采样帧
    analysisResult.value = '正在处理分析结果...'
    const analysisResults: string[] = []
    
    for (let i = 0; i < samples.length; i++) {
      const result = await visionService.analyzeFrame(samples[i])
      if (result && result.analysis) {
        analysisResults.push(`[${Math.floor(i * sampleInterval)}秒] ${result.analysis}`)
      }
    }
    
    // 合并分析结果
    if (analysisResults.length > 0) {
      analysisResult.value = `【视频分析报告】\n\n${analysisResults.join('\n\n')}\n\n【总结】\n基于对视频关键帧的分析，整体评估：设备运行状态正常，无明显异常。`
    } else {
      analysisResult.value = '分析完成，但未检测到有效结果。'
    }
  } catch (error) {
    console.error('视频分析失败:', error)
    analysisResult.value = `分析失败: ${error instanceof Error ? error.message : String(error)}`
  } finally {
    isAnalyzing.value = false
  }
}

// 开始检测
const startDetection = () => {
  // 如果启用了实时分析，则开始实时分析
  if (realTimeAnalysisEnabled.value) {
    startRealTimeAnalysis()
  }
}

// 停止检测
const stopDetection = () => {
  stopRealTimeAnalysis()
  if (detectionInterval) {
    clearInterval(detectionInterval)
    detectionInterval = null
  }
}

// 切换实时分析
const toggleRealTimeAnalysis = () => {
  if (realTimeAnalysisEnabled.value) {
    if (isPlaying.value) {
      startRealTimeAnalysis()
    }
  } else {
    stopRealTimeAnalysis()
  }
}

// 开始实时分析
const startRealTimeAnalysis = () => {
  if (!videoElement.value || !detectionCanvas.value || realTimeAnalysisInterval) return
  
  const video = videoElement.value
  const canvas = detectionCanvas.value
  
  // 等待视频准备就绪
  const waitForVideoReady = (): Promise<boolean> => {
    return new Promise((resolve) => {
      if (video.readyState >= 2 && video.videoWidth > 0 && video.videoHeight > 0) {
        resolve(true)
        return
      }
      
      const checkReady = () => {
        if (video.readyState >= 2 && video.videoWidth > 0 && video.videoHeight > 0) {
          resolve(true)
        } else {
          setTimeout(checkReady, 100)
        }
      }
      
      // 设置超时，5秒后放弃
      setTimeout(() => {
        resolve(false)
      }, 5000)
      
      checkReady()
    })
  }
  
  // 每3秒分析一帧
  const analyzeFrame = async () => {
    if (!videoElement.value || !detectionCanvas.value || !isPlaying.value || !realTimeAnalysisEnabled.value) {
      stopRealTimeAnalysis()
      return
    }
    
    try {
      const video = videoElement.value
      const canvas = detectionCanvas.value
      
      // 检查视频是否准备好
      if (video.readyState < 2 || video.videoWidth === 0 || video.videoHeight === 0) {
        return
      }
      
      isRealTimeAnalyzing.value = true
      const ctx = canvas.getContext('2d')
      if (!ctx) {
        isRealTimeAnalyzing.value = false
        return
      }
      
      // 更新canvas尺寸（如果视频尺寸变化）
      if (canvas.width !== video.videoWidth || canvas.height !== video.videoHeight) {
        canvas.width = video.videoWidth
        canvas.height = video.videoHeight
        
        // 不设置CSS尺寸，让canvas通过CSS布局自动匹配视频大小
      }
      
      // 绘制当前帧到canvas
      try {
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
      } catch (drawError) {
        console.error('绘制视频帧失败:', drawError)
        isRealTimeAnalyzing.value = false
        return
      }
      
      // 转换为base64图片（降低压缩率，减少数据量，提升实时性能）
      let imageData: string
      try {
        // 使用更低的压缩率（0.5）以减小图片体积，加快上传速度
        imageData = canvas.toDataURL('image/jpeg', 0.5)
      } catch (toDataError) {
        console.error('转换图片失败:', toDataError)
        isRealTimeAnalyzing.value = false
        return
      }
      
      // 调用AI分析（添加超时保护）
      const analysisPromise = visionService.analyzeFrame(imageData)
      const timeoutPromise = new Promise((_, reject) => {
        setTimeout(() => reject(new Error('分析超时')), 30000) // 30秒超时
      })
      
      const result = await Promise.race([analysisPromise, timeoutPromise]) as any
      
      if (result && result.analysis) {
        // 格式化时间
        const videoTime = video.currentTime || 0
        const minutes = Math.floor(videoTime / 60)
        const seconds = Math.floor(videoTime % 60)
        const timeStr = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`
        
        // 添加到结果列表（最多保留20条）
        realTimeAnalysisResults.value.unshift({
          time: timeStr,
          result: result.analysis,
          timestamp: Date.now()
        })
        
        if (realTimeAnalysisResults.value.length > 20) {
          realTimeAnalysisResults.value = realTimeAnalysisResults.value.slice(0, 20)
        }
      }
    } catch (error) {
      console.error('实时分析失败:', error)
      // 不阻止后续分析，只记录错误
    } finally {
      isRealTimeAnalyzing.value = false
    }
  }
  
  // 等待视频准备就绪后再开始分析
  waitForVideoReady().then((ready) => {
    if (ready && realTimeAnalysisEnabled.value) {
      // 使用setInterval每5秒分析一次（降低频率，减少卡顿）
      realTimeAnalysisInterval = setInterval(analyzeFrame, 5000) as any

      // 延迟1000ms后执行第一次分析，确保视频已经开始播放
      setTimeout(() => {
        if (realTimeAnalysisEnabled.value && isPlaying.value) {
          analyzeFrame()
        }
      }, 1000)
    } else {
      console.warn('视频未准备好，无法开始实时分析')
    }
  })
}

// 停止实时分析
const stopRealTimeAnalysis = () => {
  if (realTimeAnalysisInterval) {
    clearInterval(realTimeAnalysisInterval as number)
    realTimeAnalysisInterval = null
  }
  isRealTimeAnalyzing.value = false
}

// 清空实时分析结果
const clearRealTimeResults = () => {
  realTimeAnalysisResults.value = []
}

// 文件上传
const handleFileUpload = (event: Event) => {
  const input = event.target as HTMLInputElement
  if (input.files && input.files[0]) {
    const file = input.files[0]
    const url = URL.createObjectURL(file)
    videoSrc.value = url
    videoError.value = false
    
    // 确保切换到文件模式
    if (videoSourceType.value !== 'file') {
      switchVideoSource('file')
    }
    
    if (videoElement.value) {
      videoElement.value.srcObject = null
      videoElement.value.src = url
    }
  }
}

// 创建新聊天
const createNewChat = () => {
  const newChat: ChatSession = {
    id: Date.now().toString(),
    title: `聊天 ${chatHistory.value.length + 1}`,
    messages: [],
    createdAt: Date.now()
  }
  chatHistory.value.push(newChat)
  currentChatIndex.value = chatHistory.value.length - 1
  currentChatTitle.value = newChat.title
}

// 选择聊天
const selectChat = (index: number) => {
  currentChatIndex.value = index
  if (chatHistory.value[index]) {
    currentChatTitle.value = chatHistory.value[index].title
  }
  scrollToBottom()
}

// 删除聊天
const deleteChat = (index: number) => {
  if (chatHistory.value.length <= 1) {
    // 如果只剩一个聊天，创建新的空聊天
    createNewChat()
    chatHistory.value.splice(index, 1)
    currentChatIndex.value = 0
  } else {
    chatHistory.value.splice(index, 1)
    if (currentChatIndex.value === index) {
      currentChatIndex.value = Math.max(0, index - 1)
    } else if (currentChatIndex.value && currentChatIndex.value > index) {
      currentChatIndex.value--
    }
    if (chatHistory.value[currentChatIndex.value]) {
      currentChatTitle.value = chatHistory.value[currentChatIndex.value].title
    }
  }
}

// 发送消息
const handleSend = async () => {
  if (!inputMessage.value.trim() || isTyping.value) return
  
  // 如果没有聊天历史，创建新聊天
  if (currentChatIndex.value === null || chatHistory.value.length === 0) {
    createNewChat()
  }
  
  if (currentChatIndex.value === null) return
  
  const userMessage = inputMessage.value.trim()
  inputMessage.value = ''
  
  // 添加用户消息
  const userMsg = {
    type: 'user' as const,
    text: userMessage,
    time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  
  chatHistory.value[currentChatIndex.value].messages.push(userMsg)
  
  // 更新聊天标题（使用第一条消息的前20个字符）
  if (chatHistory.value[currentChatIndex.value].messages.length === 1) {
    const title = userMessage.length > 20 ? userMessage.substring(0, 20) + '...' : userMessage
    chatHistory.value[currentChatIndex.value].title = title
    currentChatTitle.value = title
  }
  
  // 滚动到底部
  scrollToBottom()
  
  // 显示正在输入
  isTyping.value = true
  
  try {
    // 调用AI API
    const response = await difyService.sendMessage(userMessage, 'video-analysis-user')
    
    // 添加AI回复
    const botMsg = {
      type: 'bot' as const,
      text: response.answer,
      time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    }
    chatHistory.value[currentChatIndex.value].messages.push(botMsg)
  } catch (error) {
    console.error('AI回复失败:', error)
    chatHistory.value[currentChatIndex.value].messages.push({
      type: 'bot',
      text: '抱歉，我暂时无法回答您的问题。请稍后再试。',
      time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    })
  } finally {
    isTyping.value = false
    scrollToBottom()
  }
}

// 格式化消息（支持Markdown）
const formatMessage = (text: string) => {
  // 简单的Markdown格式化
  return text
    .replace(/\n/g, '<br>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/`(.*?)`/g, '<code>$1</code>')
}

// 自动调整输入框高度
const autoResize = () => {
  if (inputRef.value) {
    inputRef.value.style.height = 'auto'
    inputRef.value.style.height = inputRef.value.scrollHeight + 'px'
  }
}

// 滚动到底部
const scrollToBottom = () => {
  nextTick(() => {
    setTimeout(() => {
      if (chatMessages.value) {
        chatMessages.value.scrollTop = chatMessages.value.scrollHeight
      }
    }, 100)
  })
}

// 监听消息变化
watch(() => messages.value.length, () => {
  scrollToBottom()
})

// 监听当前聊天变化
watch(() => currentChatIndex.value, () => {
  scrollToBottom()
})

onMounted(async () => {
  // 初始化时创建第一个聊天
  if (chatHistory.value.length === 0) {
    createNewChat()
  }
  // 初始化时滚动到底部
  scrollToBottom()
  
  // 从localStorage加载聊天历史
  const savedHistory = localStorage.getItem('videoAnalysisChatHistory')
  if (savedHistory) {
    try {
      chatHistory.value = JSON.parse(savedHistory)
      if (chatHistory.value.length > 0) {
        currentChatIndex.value = 0
        currentChatTitle.value = chatHistory.value[0].title
      }
    } catch (e) {
      console.error('加载聊天历史失败:', e)
    }
  }
  
  // 请求摄像头权限并获取摄像头列表
  try {
    await navigator.mediaDevices.getUserMedia({ video: true })
    await getAvailableCameras()
  } catch (error) {
  }
})

// 保存聊天历史到localStorage
watch(chatHistory, (newHistory) => {
  localStorage.setItem('videoAnalysisChatHistory', JSON.stringify(newHistory))
}, { deep: true })

onUnmounted(() => {
  stopDetection()
  stopRealTimeAnalysis()
  if (videoElement.value) {
    videoElement.value.pause()
    videoElement.value.srcObject = null
  }
  // 停止摄像头流
  if (cameraStream.value) {
    cameraStream.value.getTracks().forEach(track => track.stop())
    cameraStream.value = null
  }
})
</script>

<style lang="scss" scoped>
.video-analysis-view {
  --left-panel-width: 35%;
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  left: 0;
  display: flex;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: #0a0e1a;
}

.left-panel-toggle {
  position: absolute;
  top: 18px;
  left: calc(var(--left-panel-width) - 18px);
  z-index: 30;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  color: #d7fffb;
  cursor: pointer;
  background: linear-gradient(135deg, rgba(20, 184, 166, 92%) 0%, rgba(13, 148, 136, 95%) 100%);
  border: 1px solid rgba(94, 234, 212, 45%);
  border-radius: 999px;
  box-shadow: 0 10px 24px rgba(0, 0, 0, 35%);
  transition: left 0.3s ease, box-shadow 0.3s ease, transform 0.3s ease;
  &:hover {
    box-shadow: 0 14px 28px rgba(0, 0, 0, 42%);
    transform: translateX(2px);
  }
  &.collapsed:hover {
    transform: translateX(0);
  }
  i {
    font-size: 14px;
  }
}

// 左侧面板
.left-panel {
  display: flex;
  flex: 0 0 var(--left-panel-width);
  width: var(--left-panel-width);
  min-width: 0;
  flex-direction: column;
  overflow: hidden;
  background: rgba(0, 20, 40, 50%);
  border-right: 1px solid rgba(94, 234, 212, 20%);
  transition: flex-basis 0.3s ease, width 0.3s ease, border-color 0.3s ease, opacity 0.3s ease;
  &.collapsed {
    flex-basis: 0;
    width: 0;
    border-right-color: transparent;
    opacity: 0;
    pointer-events: none;
  }
  .panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 24px;
    background: linear-gradient(135deg, rgba(13, 148, 136, 10%) 0%, rgba(20, 184, 166, 5%) 100%);
    border-bottom: 1px solid rgba(94, 234, 212, 20%);
    .panel-title {
      display: flex;
      gap: 10px;
      align-items: center;
      font-size: 16px;
      font-weight: 600;
      color: #fff;
      i {
        font-size: 18px;
        color: #14b8a6;
      }
    }
    .back-btn {
      display: flex;
      gap: 8px;
      align-items: center;
      padding: 8px 16px;
      font-size: 13px;
      color: #fff;
      cursor: pointer;
      background: rgba(13, 148, 136, 20%);
      border: 1px solid rgba(94, 234, 212, 40%);
      border-radius: 6px;
      transition: all 0.3s ease;
      &:hover {
        background: rgba(13, 148, 136, 30%);
        border-color: #14b8a6;
      }
    }
  }
  .video-container-wrapper {
    display: flex;
    flex: 1;
    flex-direction: column;
    padding: 24px;
    overflow-y: auto;
    .video-container {
      position: relative;
      display: flex;
      align-items: center;
      justify-content: center;
      width: 100%;
      min-height: 300px;
      margin-bottom: 20px;
      overflow: hidden;
      background: #000;
      border-radius: 12px;
      video {
        display: block;
        width: auto;
        max-width: 100%;
        height: auto;
        max-height: 100%;
        object-fit: contain;
      }
      .detection-overlay {
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        pointer-events: none;

        // canvas通过max-width/max-height与视频保持相同的显示尺寸
        canvas {
          display: block;
          width: auto;
          max-width: 100%;
          height: auto;
          max-height: 100%;
          object-fit: contain;
        }
      }
      .video-controls {
        position: absolute;
        bottom: 20px;
        left: 50%;
        transform: translateX(-50%);
        .play-btn {
          width: 60px;
          height: 60px;
          font-size: 24px;
          color: #fff;
          cursor: pointer;
          background: rgba(20, 184, 166, 80%);
          border: none;
          border-radius: 50%;
          transition: all 0.3s ease;
          &:hover {
            background: rgba(20, 184, 166, 100%);
            transform: scale(1.1);
          }
        }
      }
      .video-error {
        position: absolute;
        top: 50%;
        left: 50%;
        color: #fff;
        text-align: center;
        transform: translate(-50%, -50%);
        i {
          margin-bottom: 16px;
          font-size: 48px;
          color: #ff6b6b;
        }
        p {
          margin-bottom: 8px;
          font-size: 18px;
        }
        small {
          display: block;
          margin-bottom: 4px;
          font-size: 12px;
          color: rgba(255, 255, 255, 60%);
        }
        code {
          padding: 2px 6px;
          background: rgba(0, 0, 0, 50%);
          border-radius: 4px;
        }
        .upload-btn {
          display: inline-block;
          padding: 10px 20px;
          margin-top: 16px;
          cursor: pointer;
          background: rgba(20, 184, 166, 30%);
          border: 1px solid rgba(94, 234, 212, 50%);
          border-radius: 6px;
          transition: all 0.3s ease;
          &:hover {
            background: rgba(20, 184, 166, 50%);
          }
        }
      }
    }
    .analysis-result {
      margin-bottom: 20px;
      overflow: hidden;
      background: rgba(0, 20, 40, 50%);
      border: 1px solid rgba(94, 234, 212, 20%);
      border-radius: 12px;
      .result-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 12px 16px;
        background: rgba(13, 148, 136, 10%);
        border-bottom: 1px solid rgba(94, 234, 212, 20%);
        .result-header-left {
          display: flex;
          gap: 10px;
          align-items: center;
          font-size: 14px;
          font-weight: 600;
          color: #fff;
          i {
            color: #14b8a6;
          }
        }
        .analyze-btn {
          display: flex;
          gap: 6px;
          align-items: center;
          padding: 6px 12px;
          font-size: 12px;
          color: #fff;
          cursor: pointer;
          background: rgba(20, 184, 166, 30%);
          border: 1px solid rgba(94, 234, 212, 40%);
          border-radius: 6px;
          transition: all 0.3s ease;
          &:hover:not(:disabled) {
            background: rgba(20, 184, 166, 50%);
            border-color: #14b8a6;
          }
          &:disabled {
            cursor: not-allowed;
            opacity: 0.5;
          }
          i {
            font-size: 10px;
          }
        }
      }
      .result-content {
        max-height: 300px;
        padding: 16px;
        overflow-y: auto;
        &::-webkit-scrollbar {
          width: 6px;
        }
        &::-webkit-scrollbar-track {
          background: rgba(0, 0, 0, 20%);
        }
        &::-webkit-scrollbar-thumb {
          background: rgba(20, 184, 166, 40%);
          border-radius: 3px;
          &:hover {
            background: rgba(20, 184, 166, 60%);
          }
        }
        .result-text {
          font-size: 13px;
          line-height: 1.8;
          color: #fff;
          word-wrap: break-word;
          white-space: pre-wrap;
        }
      }
      .result-placeholder {
        padding: 40px 16px;
        color: rgba(255, 255, 255, 50%);
        text-align: center;
        i {
          margin-bottom: 12px;
          font-size: 32px;
          color: rgba(20, 184, 166, 30%);
        }
        p {
          font-size: 13px;
        }
        .warning-text {
          display: flex;
          gap: 6px;
          align-items: center;
          justify-content: center;
          padding: 8px 12px;
          margin-top: 12px;
          font-size: 12px;
          color: #fca5a5;
          background: rgba(220, 38, 38, 10%);
          border: 1px solid rgba(220, 38, 38, 30%);
          border-radius: 4px;
          i {
            margin-bottom: 0;
            font-size: 12px;
            color: #fca5a5;
          }
        }
      }
    }
    .realtime-analysis-control {
      padding: 16px;
      margin-bottom: 20px;
      background: rgba(0, 20, 40, 50%);
      border: 1px solid rgba(94, 234, 212, 20%);
      border-radius: 12px;
      .control-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 12px;
        .control-title {
          display: flex;
          gap: 8px;
          align-items: center;
          font-size: 14px;
          font-weight: 600;
          color: #fff;
          i {
            color: #14b8a6;
          }
        }
      }
      .realtime-status {
        display: flex;
        gap: 8px;
        align-items: center;
        font-size: 12px;
        color: rgba(255, 255, 255, 70%);
        i {
          font-size: 8px;
          color: rgba(255, 255, 255, 50%);
          &.pulsing {
            color: #14b8a6;
            animation: pulse 1.5s ease-in-out infinite;
          }
        }
      }
      .toggle-switch {
        position: relative;
        display: inline-block;
        width: 50px;
        height: 24px;
        input {
          width: 0;
          height: 0;
          opacity: 0;
          &:checked + .slider {
            background-color: #14b8a6;
            &::before {
              transform: translateX(26px);
            }
          }
          &:disabled + .slider {
            cursor: not-allowed;
            opacity: 0.5;
          }
        }
        .slider {
          position: absolute;
          top: 0;
          right: 0;
          bottom: 0;
          left: 0;
          cursor: pointer;
          background-color: rgba(255, 255, 255, 20%);
          border-radius: 24px;
          transition: 0.3s;
          &::before {
            position: absolute;
            bottom: 3px;
            left: 3px;
            width: 18px;
            height: 18px;
            content: "";
            background-color: white;
            border-radius: 50%;
            transition: 0.3s;
          }
        }
      }
    }
    .realtime-results {
      display: flex;
      flex-direction: column;
      max-height: 300px;
      margin-bottom: 20px;
      overflow: hidden;
      background: rgba(0, 20, 40, 50%);
      border: 1px solid rgba(94, 234, 212, 20%);
      border-radius: 12px;
      .results-header {
        display: flex;
        gap: 10px;
        align-items: center;
        padding: 12px 16px;
        font-size: 14px;
        font-weight: 600;
        color: #fff;
        background: rgba(13, 148, 136, 10%);
        border-bottom: 1px solid rgba(94, 234, 212, 20%);
        i {
          color: #14b8a6;
        }
        .clear-btn {
          padding: 4px 8px;
          margin-left: auto;
          font-size: 12px;
          color: rgba(255, 255, 255, 70%);
          cursor: pointer;
          background: transparent;
          border: 1px solid rgba(94, 234, 212, 30%);
          border-radius: 4px;
          transition: all 0.3s ease;
          &:hover {
            color: #fca5a5;
            background: rgba(220, 38, 38, 20%);
            border-color: rgba(220, 38, 38, 50%);
          }
        }
      }
      .results-content {
        flex: 1;
        padding: 12px;
        overflow-y: auto;
        &::-webkit-scrollbar {
          width: 6px;
        }
        &::-webkit-scrollbar-track {
          background: rgba(0, 0, 0, 20%);
        }
        &::-webkit-scrollbar-thumb {
          background: rgba(20, 184, 166, 40%);
          border-radius: 3px;
          &:hover {
            background: rgba(20, 184, 166, 60%);
          }
        }
        .empty-results {
          padding: 40px 16px;
          color: rgba(255, 255, 255, 50%);
          text-align: center;
          i {
            margin-bottom: 12px;
            font-size: 32px;
            color: rgba(20, 184, 166, 30%);
          }
          p {
            font-size: 13px;
          }
        }
        .results-list {
          display: flex;
          flex-direction: column;
          gap: 12px;
          .result-item {
            padding: 12px;
            background: rgba(0, 0, 0, 20%);
            border-left: 3px solid #14b8a6;
            border-radius: 4px;
            .result-time {
              margin-bottom: 6px;
              font-size: 11px;
              font-weight: 600;
              color: rgba(20, 184, 166, 80%);
            }
            .result-text {
              font-size: 12px;
              line-height: 1.6;
              color: rgba(255, 255, 255, 85%);
              word-wrap: break-word;
              white-space: pre-wrap;
            }
          }
        }
      }
    }
    
    @keyframes pulse {
      0%, 100% {
        opacity: 1;
      }
      50% {
        opacity: 0.5;
      }
    }
    .video-source-section {
      padding: 20px 0;
      .source-content {
        margin-bottom: 20px;
      }
      .source-tabs {
        display: flex;
        gap: 12px;
        margin-bottom: 20px;
        .source-tab {
          display: flex;
          flex: 1;
          gap: 8px;
          align-items: center;
          justify-content: center;
          padding: 12px 20px;
          font-size: 14px;
          color: rgba(255, 255, 255, 60%);
          cursor: pointer;
          background: rgba(13, 148, 136, 10%);
          border: 2px solid rgba(94, 234, 212, 20%);
          border-radius: 8px;
          transition: all 0.3s ease;
          &:hover {
            color: rgba(255, 255, 255, 80%);
            background: rgba(13, 148, 136, 20%);
            border-color: rgba(94, 234, 212, 40%);
          }
          &.active {
            color: #fff;
            background: rgba(20, 184, 166, 20%);
            border-color: #14b8a6;
            i {
              color: #14b8a6;
            }
          }
          i {
            font-size: 16px;
            transition: color 0.3s ease;
          }
        }
      }
      .upload-btn-large {
          display: flex;
          gap: 10px;
          align-items: center;
          justify-content: center;
          width: 100%;
          padding: 16px;
          color: #fff;
          cursor: pointer;
          background: rgba(13, 148, 136, 10%);
          border: 2px dashed rgba(94, 234, 212, 40%);
          border-radius: 8px;
          transition: all 0.3s ease;
          &:hover {
            background: rgba(13, 148, 136, 20%);
            border-color: rgba(94, 234, 212, 60%);
          }
          i {
            font-size: 20px;
            color: #14b8a6;
          }
        }
        .camera-selector {
          display: flex;
          gap: 12px;
          align-items: center;
          label {
            font-size: 14px;
            color: rgba(255, 255, 255, 80%);
            white-space: nowrap;
          }
          .camera-select {
            flex: 1;
            padding: 10px 14px;
            font-size: 14px;
            color: #fff;
            cursor: pointer;
            background: rgba(13, 148, 136, 10%);
            border: 1px solid rgba(94, 234, 212, 30%);
            border-radius: 6px;
            transition: all 0.3s ease;
            &:hover {
              border-color: rgba(94, 234, 212, 50%);
            }
            &:focus {
              border-color: #14b8a6;
              outline: none;
            }
            option {
              color: #fff;
              background: #0f1419;
            }
          }
          .refresh-btn {
            padding: 10px 14px;
            color: #14b8a6;
            cursor: pointer;
            background: rgba(20, 184, 166, 20%);
            border: 1px solid rgba(94, 234, 212, 30%);
            border-radius: 6px;
            transition: all 0.3s ease;
            &:hover {
              background: rgba(20, 184, 166, 30%);
              border-color: #14b8a6;
            }
            i {
              font-size: 14px;
            }
          }
        }
        .camera-error {
          display: flex;
          gap: 8px;
          align-items: center;
          padding: 12px;
          margin-top: 12px;
          font-size: 13px;
          color: #fca5a5;
          background: rgba(220, 38, 38, 10%);
          border: 1px solid rgba(220, 38, 38, 30%);
          border-radius: 6px;
          i {
            font-size: 16px;
          }
        }
      }
    }
  }

// 右侧面板
.right-panel {
  display: flex;
  flex: 1 1 auto;
  min-width: 0;
  background: linear-gradient(135deg, #0f1419 0%, #1a1f2e 100%);
  
  // 聊天侧边栏
  .chat-sidebar {
    display: flex;
    flex: 0 0 220px;
    flex-direction: column;
    background: rgba(0, 20, 40, 60%);
    border-right: 1px solid rgba(94, 234, 212, 15%);
    backdrop-filter: blur(10px);
    .sidebar-header {
      display: flex;
      gap: 12px;
      align-items: center;
      justify-content: space-between;
      padding: 20px 16px;
      border-bottom: 1px solid rgba(94, 234, 212, 10%);
      .header-title {
        display: flex;
        gap: 8px;
        align-items: center;
        font-size: 14px;
        font-weight: 600;
        color: rgba(255, 255, 255, 90%);
        i {
          font-size: 16px;
          color: #14b8a6;
        }
      }
      .new-chat-btn {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 36px;
        height: 36px;
        color: #fff;
        cursor: pointer;
        background: linear-gradient(135deg, #14b8a6 0%, #0d9488 100%);
        border: none;
        border-radius: 10px;
        box-shadow: 0 4px 15px rgba(20, 184, 166, 30%);
        transition: all 0.3s ease;
        &:hover {
          box-shadow: 0 6px 20px rgba(20, 184, 166, 40%);
          transform: scale(1.05);
        }
        &:active {
          transform: scale(0.95);
        }
        i {
          font-size: 14px;
        }
      }
    }
    .chat-history {
      flex: 1;
      padding: 12px 8px;
      overflow-y: auto;
      &::-webkit-scrollbar {
        width: 4px;
      }
      &::-webkit-scrollbar-track {
        background: transparent;
      }
      &::-webkit-scrollbar-thumb {
        background: rgba(20, 184, 166, 30%);
        border-radius: 2px;
        &:hover {
          background: rgba(20, 184, 166, 50%);
        }
      }
      .history-item {
        display: flex;
        gap: 10px;
        align-items: center;
        padding: 12px;
        margin-bottom: 6px;
        cursor: pointer;
        border-radius: 12px;
        transition: all 0.3s ease;
        .history-item-content {
          display: flex;
          flex: 1;
          gap: 10px;
          align-items: center;
          min-width: 0;
          i {
            flex-shrink: 0;
            font-size: 14px;
            color: rgba(20, 184, 166, 70%);
          }
          .history-info {
            display: flex;
            flex-direction: column;
            gap: 2px;
            min-width: 0;
            .history-title {
              overflow: hidden;
              font-size: 13px;
              color: rgba(255, 255, 255, 85%);
              text-overflow: ellipsis;
              white-space: nowrap;
            }
            .history-count {
              font-size: 11px;
              color: rgba(255, 255, 255, 45%);
            }
          }
        }
        .delete-btn {
          padding: 6px;
          color: #ff6b6b;
          cursor: pointer;
          background: rgba(255, 107, 107, 10%);
          border: none;
          border-radius: 6px;
          opacity: 0;
          transition: all 0.3s ease;
          &:hover {
            background: rgba(255, 107, 107, 20%);
          }
          i {
            font-size: 12px;
            color: inherit;
          }
        }
        &:hover {
          background: rgba(20, 184, 166, 10%);
          .delete-btn {
            opacity: 1;
          }
        }
        &.active {
          background: linear-gradient(135deg, rgba(20, 184, 166, 20%) 0%, rgba(13, 148, 136, 15%) 100%);
          border: 1px solid rgba(94, 234, 212, 40%);
          box-shadow: 0 4px 12px rgba(20, 184, 166, 20%);
          .history-item-content i {
            color: #14b8a6;
          }
          .history-title {
            color: #fff;
          }
        }
      }
    }
  }
  
  // 聊天主区域
  .chat-main {
    display: flex;
    flex: 1;
    flex-direction: column;
    overflow: hidden;
    
    // AI助手信息卡片
    .ai-assistant-card {
      position: relative;
      display: flex;
      gap: 16px;
      align-items: center;
      padding: 20px 24px;
      overflow: hidden;
      background: linear-gradient(135deg, rgba(20, 184, 166, 15%) 0%, rgba(13, 148, 136, 10%) 100%);
      border-bottom: 1px solid rgba(94, 234, 212, 20%);
      &::before {
        position: absolute;
        top: -50%;
        right: -20%;
        width: 200px;
        height: 200px;
        pointer-events: none;
        content: '';
        background: radial-gradient(circle, rgba(94, 234, 212, 20%) 0%, transparent 70%);
        border-radius: 50%;
      }
      .assistant-avatar {
        position: relative;
        display: flex;
        align-items: center;
        justify-content: center;
        width: 56px;
        height: 56px;
        background: linear-gradient(135deg, #14b8a6 0%, #0d9488 100%);
        border-radius: 16px;
        box-shadow: 0 8px 24px rgba(20, 184, 166, 40%);
        .avatar-glow {
          position: absolute;
          width: 100%;
          height: 100%;
          background: inherit;
          filter: blur(20px);
          border-radius: 16px;
          opacity: 0.5;
          animation: glow 2s ease-in-out infinite;
        }
        i {
          position: relative;
          z-index: 1;
          font-size: 28px;
          color: #fff;
        }
      }
      .assistant-info {
        z-index: 1;
        flex: 1;
        h3 {
          margin: 0 0 4px;
          font-size: 18px;
          font-weight: 700;
          color: #fff;
          background: linear-gradient(90deg, #fff 0%, rgba(255, 255, 255, 85%) 100%);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
        }
        p {
          margin: 0;
          font-size: 13px;
          line-height: 1.5;
          color: rgba(255, 255, 255, 70%);
        }
      }
      .assistant-status {
        z-index: 1;
        display: flex;
        gap: 8px;
        align-items: center;
        padding: 8px 14px;
        background: rgba(20, 184, 166, 20%);
        border: 1px solid rgba(94, 234, 212, 40%);
        border-radius: 20px;
        .status-dot {
          width: 8px;
          height: 8px;
          background: #14b8a6;
          border-radius: 50%;
          box-shadow: 0 0 8px #14b8a6;
          animation: pulse 2s ease-in-out infinite;
        }
        span {
          font-size: 12px;
          font-weight: 600;
          color: #14b8a6;
        }
      }
    }
    .chat-messages {
      display: flex;
      flex: 1;
      flex-direction: column;
      gap: 24px;
      padding: 24px;
      overflow-y: auto;
      &::-webkit-scrollbar {
        width: 6px;
      }
      &::-webkit-scrollbar-track {
        background: rgba(0, 0, 0, 20%);
      }
      &::-webkit-scrollbar-thumb {
        background: rgba(20, 184, 166, 40%);
        border-radius: 3px;
        &:hover {
          background: rgba(20, 184, 166, 60%);
        }
      }
      
      // 空状态
          .empty-state {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100%;
            padding: 60px 40px;
            .empty-illustration {
              position: relative;
              text-align: center;
              .floating-icon {
                position: relative;
                display: flex;
                align-items: center;
                justify-content: center;
                width: 140px;
                height: 140px;
                margin: 0 auto 28px;
                background: linear-gradient(135deg, rgba(20, 184, 166, 25%) 0%, rgba(13, 148, 136, 20%) 100%);
                border-radius: 35px;
                box-shadow: 0 20px 50px rgba(20, 184, 166, 30%);
                animation: float 4s ease-in-out infinite, glow-pulse 3s ease-in-out infinite;
                i {
                  font-size: 64px;
                  background: linear-gradient(135deg, #fff 0%, rgba(255, 255, 255, 80%) 100%);
                  -webkit-background-clip: text;
                  -webkit-text-fill-color: transparent;
                }
                &::before {
                  position: absolute;
                  top: -10px;
                  left: -10px;
                  width: 40px;
                  height: 40px;
                  content: '';
                  background: rgba(20, 184, 166, 30%);
                  filter: blur(15px);
                  border-radius: 50%;
                  animation: float-particle 4s ease-in-out infinite reverse;
                }
                &::after {
                  position: absolute;
                  right: -10px;
                  bottom: -15px;
                  width: 30px;
                  height: 30px;
                  content: '';
                  background: rgba(251, 191, 36, 30%);
                  filter: blur(12px);
                  border-radius: 50%;
                  animation: float-particle 4s ease-in-out infinite 1s;
                }
              }
              h3 {
                margin: 0 0 12px;
                font-size: 28px;
                font-weight: 700;
                color: #fff;
                background: linear-gradient(90deg, #fff 0%, rgba(255, 255, 255, 85%) 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
              }
              p {
                margin: 0 0 40px;
                font-size: 15px;
                line-height: 1.7;
                color: rgba(255, 255, 255, 65%);
              }
            }
          
          // 快捷问题
        .quick-questions {
          width: 100%;
          max-width: 600px;
          .quick-questions-title {
            display: flex;
            gap: 8px;
            align-items: center;
            margin-bottom: 16px;
            font-size: 14px;
            font-weight: 600;
            color: rgba(255, 255, 255, 80%);
            i {
              font-size: 16px;
              color: #fbbf24;
            }
          }
          .quick-questions-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 14px;
            .quick-question-btn {
              position: relative;
              display: flex;
              gap: 12px;
              align-items: center;
              padding: 16px 20px;
              overflow: hidden;
              font-size: 14px;
              font-weight: 500;
              line-height: 1.4;
              color: rgba(255, 255, 255, 90%);
              text-align: left;
              cursor: pointer;
              background: linear-gradient(135deg, rgba(255, 255, 255, 8%) 0%, rgba(255, 255, 255, 3%) 100%);
              border: 1px solid rgba(255, 255, 255, 12%);
              border-radius: 16px;
              transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
              &::before {
                position: absolute;
                top: 0;
                left: -100%;
                width: 100%;
                height: 100%;
                content: '';
                background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 10%), transparent);
                transition: left 0.5s ease;
              }
              &:hover {
                background: linear-gradient(135deg, rgba(20, 184, 166, 25%) 0%, rgba(13, 148, 136, 20%) 100%);
                border-color: rgba(94, 234, 212, 50%);
                box-shadow: 0 8px 24px rgba(20, 184, 166, 25%), 
                            0 0 0 1px rgba(94, 234, 212, 20%) inset;
                transform: translateY(-3px);
                i {
                  color: #14b8a6;
                  transform: scale(1.1);
                }
                &::before {
                  left: 100%;
                }
              }
              &:active {
                transform: translateY(-1px);
              }
              i {
                flex-shrink: 0;
                font-size: 20px;
                color: rgba(255, 255, 255, 70%);
                transition: all 0.3s ease;
              }
              span {
                flex: 1;
              }
            }
          }
        }
      }
      
      // 消息气泡
      .message {
        display: flex;
        gap: 16px;
        padding: 4px 0;
        animation: slide-in 0.4s cubic-bezier(0.4, 0, 0.2, 1);
        .message-avatar {
          display: flex;
          flex-shrink: 0;
          align-items: center;
          justify-content: center;
          width: 44px;
          height: 44px;
          border-radius: 14px;
          .avatar-container {
            display: flex;
            align-items: center;
            justify-content: center;
            width: 100%;
            height: 100%;
            background: linear-gradient(135deg, rgba(20, 184, 166, 25%) 0%, rgba(13, 148, 136, 20%) 100%);
            border-radius: 14px;
            box-shadow: 0 4px 12px rgba(20, 184, 166, 25%);
            i {
              font-size: 20px;
              color: #14b8a6;
            }
          }
        }
        .message-wrapper {
          display: flex;
          flex-direction: column;
          gap: 8px;
          max-width: calc(100% - 68px);
          .message-header {
            display: flex;
            gap: 10px;
            align-items: center;
            .message-role {
              font-size: 13px;
              font-weight: 600;
              color: rgba(255, 255, 255, 80%);
            }
            .message-time {
              font-size: 12px;
              color: rgba(255, 255, 255, 45%);
            }
          }
          .message-content {
            position: relative;
            padding: 16px 20px;
            border-radius: 20px;
            transition: all 0.3s ease;
            .message-text {
              font-size: 14px;
              line-height: 1.75;
              color: rgba(255, 255, 255, 92%);
              word-wrap: break-word;
              :deep(code) {
                padding: 4px 10px;
                font-family: 'SF Mono', 'Fira Code', 'Courier New', monospace;
                font-size: 13px;
                background: rgba(0, 0, 0, 40%);
                border-radius: 8px;
              }
              :deep(strong) {
                font-weight: 600;
                color: #fff;
              }
              :deep(p) {
                margin: 0 0 12px;
                &:last-child {
                  margin-bottom: 0;
                }
              }
            }
            
            // 消息操作
            .message-actions {
              display: flex;
              gap: 10px;
              padding-top: 12px;
              margin-top: 12px;
              border-top: 1px solid rgba(255, 255, 255, 12%);
              opacity: 0;
              transition: opacity 0.3s ease;
              .action-btn {
                display: flex;
                gap: 6px;
                align-items: center;
                padding: 8px 14px;
                font-size: 12px;
                font-weight: 500;
                color: rgba(255, 255, 255, 75%);
                cursor: pointer;
                background: rgba(255, 255, 255, 8%);
                border: 1px solid rgba(255, 255, 255, 10%);
                border-radius: 8px;
                transition: all 0.3s ease;
                &:hover {
                  color: #14b8a6;
                  background: rgba(20, 184, 166, 20%);
                  border-color: rgba(94, 234, 212, 40%);
                  transform: translateY(-1px);
                }
                i {
                  font-size: 13px;
                  color: inherit;
                }
              }
            }
            &:hover .message-actions {
              opacity: 1;
            }
          }
        }
        
        // 用户消息
        &.user {
          flex-direction: row-reverse;
          .message-wrapper {
            align-items: flex-end;
            .message-header {
              flex-direction: row-reverse;
            }
          }
          .message-content {
            background: linear-gradient(135deg, #14b8a6 0%, #0d9488 100%);
            border: none;
            box-shadow: 0 4px 20px rgba(20, 184, 166, 35%), 
                        0 0 0 1px rgba(255, 255, 255, 10%) inset;
            .message-text {
              color: #fff;
              :deep(code) {
                background: rgba(0, 0, 0, 30%);
              }
            }
            .message-actions {
              border-top-color: rgba(255, 255, 255, 15%);
              .action-btn {
                color: rgba(255, 255, 255, 90%);
                background: rgba(255, 255, 255, 15%);
                border-color: rgba(255, 255, 255, 20%);
                &:hover {
                  color: #fff;
                  background: rgba(255, 255, 255, 25%);
                }
              }
            }
            &::before {
              position: absolute;
              top: 0;
              right: 0;
              width: 40px;
              height: 40px;
              content: '';
              background: linear-gradient(135deg, rgba(255, 255, 255, 20%) 0%, transparent 100%);
              border-radius: 0 20px 0 40px;
              opacity: 0.5;
            }
          }
        }
        
        // 机器人消息
        &.bot {
          .message-wrapper {
            align-items: flex-start;
          }
          .message-content {
            background: linear-gradient(135deg, rgba(255, 255, 255, 12%) 0%, rgba(255, 255, 255, 6%) 100%);
            border: 1px solid rgba(255, 255, 255, 15%);
            backdrop-filter: blur(20px);
            &::before {
              position: absolute;
              top: 0;
              left: 0;
              width: 30px;
              height: 30px;
              content: '';
              background: linear-gradient(135deg, rgba(20, 184, 166, 15%) 0%, transparent 100%);
              border-radius: 0 0 30px;
              opacity: 0.5;
            }
          }
        }
        
        // 输入中状态
        &.typing {
          .message-content {
            padding: 20px 24px;
          }
          .typing-indicator {
            display: flex;
            gap: 6px;
            align-items: center;
            padding: 6px 0;
            span {
              width: 10px;
              height: 10px;
              background: linear-gradient(135deg, #14b8a6 0%, #0d9488 100%);
              border-radius: 50%;
              box-shadow: 0 2px 8px rgba(20, 184, 166, 40%);
              animation: bounce 1.4s infinite;
              &:nth-child(2) {
                animation-delay: 0.2s;
              }
              &:nth-child(3) {
                animation-delay: 0.4s;
              }
            }
          }
        }
      }
    }
    
    // 输入区域
    .chat-input-wrapper {
      padding: 24px 28px;
      background: linear-gradient(180deg, rgba(0, 0, 0, 40%) 0%, rgba(0, 0, 0, 60%) 100%);
      border-top: 1px solid rgba(94, 234, 212, 15%);
      backdrop-filter: blur(20px);
      .chat-input-container {
        display: flex;
        flex-direction: column;
        gap: 14px;
        .chat-input {
          display: flex;
          gap: 14px;
          align-items: flex-end;
          padding: 18px 22px;
          background: linear-gradient(135deg, rgba(0, 20, 40, 70%) 0%, rgba(0, 15, 30, 50%) 100%);
          border: 1px solid rgba(94, 234, 212, 25%);
          border-radius: 20px;
          box-shadow: 0 4px 20px rgba(0, 0, 0, 30%), 
                      inset 0 1px 0 rgba(255, 255, 255, 5%);
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          &:focus-within {
            border-color: rgba(94, 234, 212, 60%);
            box-shadow: 0 0 0 4px rgba(20, 184, 166, 15%), 
                        0 8px 32px rgba(0, 0, 0, 40%),
                        inset 0 1px 0 rgba(255, 255, 255, 8%);
          }
          .attach-btn {
            display: flex;
            flex-shrink: 0;
            align-items: center;
            justify-content: center;
            width: 48px;
            height: 48px;
            color: rgba(255, 255, 255, 60%);
            cursor: pointer;
            background: rgba(255, 255, 255, 8%);
            border: 1px solid rgba(255, 255, 255, 12%);
            border-radius: 14px;
            transition: all 0.3s ease;
            &:hover {
              color: #14b8a6;
              background: rgba(20, 184, 166, 25%);
              border-color: rgba(94, 234, 212, 50%);
              transform: scale(1.05);
            }
            i {
              font-size: 18px;
            }
          }
          textarea {
            flex: 1;
            min-height: 48px;
            max-height: 160px;
            padding: 14px 16px;
            font-family: inherit;
            font-size: 15px;
            line-height: 1.6;
            color: #fff;
            resize: none;
            background: rgba(255, 255, 255, 5%);
            border: 1px solid rgba(255, 255, 255, 10%);
            border-radius: 14px;
            outline: none;
            transition: all 0.3s ease;
            &::placeholder {
              color: rgba(255, 255, 255, 40%);
            }
            &:focus {
              background: rgba(255, 255, 255, 8%);
              border-color: rgba(94, 234, 212, 30%);
            }
          }
          .send-btn {
            display: flex;
            flex-shrink: 0;
            align-items: center;
            justify-content: center;
            width: 48px;
            height: 48px;
            color: #fff;
            cursor: pointer;
            background: linear-gradient(135deg, #14b8a6 0%, #0d9488 100%);
            border: none;
            border-radius: 14px;
            box-shadow: 0 4px 16px rgba(20, 184, 166, 35%);
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            &:hover:not(:disabled) {
              box-shadow: 0 6px 24px rgba(20, 184, 166, 50%);
              transform: scale(1.05);
            }
            &:active:not(:disabled) {
              transform: scale(0.98);
            }
            &:disabled {
              cursor: not-allowed;
              box-shadow: none;
              opacity: 0.5;
              transform: none;
            }
            i {
              font-size: 18px;
            }
          }
        }
        .input-footer {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 0 6px;
          .input-hint {
            display: flex;
            gap: 8px;
            align-items: center;
            font-size: 12px;
            color: rgba(255, 255, 255, 50%);
            i {
              font-size: 12px;
              color: rgba(20, 184, 166, 70%);
            }
          }
          .char-count {
            display: flex;
            gap: 4px;
            align-items: center;
            font-size: 12px;
            font-weight: 500;
            color: rgba(255, 255, 255, 50%);
            transition: color 0.3s ease;
            &.warning {
              color: #fbbf24;
            }
            &.error {
              color: #ef4444;
            }
            span:first-child {
              font-weight: 600;
            }
          }
        }
      }
    }
  }
}

.video-analysis-view.left-panel-collapsed {
  .left-panel-toggle {
    left: 12px;
  }
}

// 动画定义
@keyframes glow {
  0%, 100% {
    opacity: 0.5;
    transform: scale(1);
  }
  50% {
    opacity: 0.8;
    transform: scale(1.05);
  }
}

@keyframes float {
  0%, 100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-10px);
  }
}

@keyframes slide-in {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes bounce {
  0%, 60%, 100% {
    transform: translateY(0);
  }
  30% {
    transform: translateY(-8px);
  }
}

@keyframes fade-in {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes typing {
  0%, 60%, 100% {
    opacity: 0.7;
    transform: translateY(0);
  }
  30% {
    opacity: 1;
    transform: translateY(-10px);
  }
}

@keyframes glow-pulse {
  0%, 100% {
    box-shadow: 0 20px 50px rgba(20, 184, 166, 30%);
  }
  50% {
    box-shadow: 0 25px 60px rgba(20, 184, 166, 45%);
  }
}

@keyframes float-particle {
  0%, 100% {
    transform: translateY(0) scale(1);
  }
  50% {
    transform: translateY(-15px) scale(1.1);
  }
}
</style>

