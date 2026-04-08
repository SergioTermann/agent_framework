<template>
  <div class="monitor-view">
    <!-- 返回按钮 -->
    <div class="back-button" @click="goBack">
      <i class="fa-solid fa-arrow-left"></i>
      <span>返回地图</span>
    </div>
    
    <!-- 工具栏按钮 -->
    <div class="tools-button" @click="toggleTools" :class="{ active: toolsVisible }">
      <i class="fa-solid fa-toolbox"></i>
      <span>{{ toolsVisible ? '隐藏工具' : '显示工具' }}</span>
    </div>
    
    <!-- 状态指示器（仅分解模式显示） -->
    <div class="status-indicator" v-if="isDecomposed">
      <i class="fa-solid fa-info-circle"></i>
      <span>分解模式：点击选择对象，拖动红/绿/蓝箭头移动</span>
    </div>

    <ComponentEditor
      :visible="editorVisible"
      :component-data="currentComponent"
      @close="closeEditor"
      @save="saveComponentData"
    />
    
    <ToolEditor
      :visible="toolEditorVisible"
      :tool-data="currentTool"
      @close="closeToolEditor"
      @save="saveToolData"
    />
    
    <Layout :loading="loading">
      <template #left>
        <WidgetPanel08 title="故障码历史" />
        <WidgetPanel05 title="偏航角度监测" />
        <ToolsPanel 
          v-show="toolsVisible"
          @tool-double-click="handleToolDoubleClick"
          @tool-click="handleToolClick"
          @tool-drag-start="handleToolDragStart"
          @tool-drag-end="handleToolDragEnd"
        />
      </template>
      <template #right>
        <WidgetPanel04 title="参数监测" />
        <WidgetPanel07
          v-show="current"
          :title="current + '详情'"
          :name="current"
        />
        <WidgetPanel06 v-show="!current" title="运行监测" />
        
        <!-- AI助手面板 -->
        <LayoutPanel title="AI助手">
          <div class="ai-chat-content">
            <div class="chat-messages" ref="aiChatMessages">
              <div v-if="aiMessages.length === 0" class="empty-state">
                <i class="fa-solid fa-comments"></i>
                <p>向AI助手提问关于风机的问题</p>
              </div>
              <div 
                v-for="(msg, index) in aiMessages" 
                :key="index"
                class="message"
                :class="msg.type"
              >
                <div class="message-avatar">
                  <i :class="msg.type === 'user' ? 'fa-solid fa-user' : 'fa-solid fa-robot'"></i>
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
            
            <div class="chat-input">
              <input 
                v-model="aiInputMessage" 
                @keyup.enter="sendAiMessage"
                type="text" 
                placeholder="输入您的问题..." 
              />
              <button @click="sendAiMessage" :disabled="!aiInputMessage.trim()">
                <i class="fa-solid fa-paper-plane"></i>
              </button>
            </div>
          </div>
        </LayoutPanel>
      </template>
      <template #middle>
        <div 
          style=" position: relative; z-index: 1;width: 100%; height: 100%; pointer-events: auto;" 
          ref="container"
          @dragover.prevent.stop="handleDragOver"
          @drop.prevent.stop="handleDrop"
          @dragenter.prevent.stop
        >
          <!-- 框选矩形框 -->
          <div
            v-if="isBoxSelecting && boxSelectStart && boxSelectEnd"
            class="box-select-overlay"
            :style="{
              left: Math.min(boxSelectStart.x, boxSelectEnd.x) + 'px',
              top: Math.min(boxSelectStart.y, boxSelectEnd.y) + 'px',
              width: Math.abs(boxSelectEnd.x - boxSelectStart.x) + 'px',
              height: Math.abs(boxSelectEnd.y - boxSelectStart.y) + 'px',
            }"
          ></div>
        </div>
      </template>
    </Layout>
  </div>
</template>

<script setup lang="ts">
import {
  WidgetPanel04,
  WidgetPanel05,
  WidgetPanel06,
  WidgetPanel07,
  WidgetPanel08,
  ComponentEditor,
  ToolEditor,
  ToolsPanel,
} from '@/components'
import { provide, ref, onMounted, nextTick, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Layout, LayoutPanel } from '@/layout'
import { useTurbine } from '@/hooks'
import { useAiChatStore } from '@/stores/aiChatStore'
import { difyService } from '@/services/difyService'

const router = useRouter()
const route = useRoute()

// 从路由参数获取风场和风机信息
const currentWindField = ref<string>(route.query.windField as string || '')
const currentTurbine = ref<string>(route.query.turbine as string || '')

// 风机监控逻辑
const {
  container,
  loading,
  current,
  eqDecomposeAnimation,
  eqComposeAnimation,
  startWarning,
  stopWarning,
  isBoxSelecting,
  boxSelectStart,
  boxSelectEnd,
  selectedObjects,
  onComponentClick,
  toggleTools,
  toolsVisible,
  zoomInCamera,
  addDraggableTool,
  addDraggableToolAtPosition,
  isDecomposed, // 获取分解状态
} = useTurbine()

// AI助手对话框状态 - 使用全局 store
const aiChatStore = useAiChatStore()
const { aiMessages } = aiChatStore
const aiInputMessage = ref('')
const aiChatMessages = ref<HTMLElement | null>(null)

// AI 正在输入状态
const isAiTyping = ref(false)

// 滚动到底部的函数
const scrollAiChatToBottom = () => {
  // 使用多重延迟确保 DOM 完全渲染
  nextTick(() => {
    setTimeout(() => {
      if (aiChatMessages.value) {
        // 使用 requestAnimationFrame 确保在浏览器重绘后滚动
        requestAnimationFrame(() => {
          if (aiChatMessages.value) {
            aiChatMessages.value.scrollTop = aiChatMessages.value.scrollHeight
            // 再次确保滚动到底部
            setTimeout(() => {
              if (aiChatMessages.value) {
                aiChatMessages.value.scrollTop = aiChatMessages.value.scrollHeight
              }
            }, 100)
          }
        })
      }
    }, 100)
  })
}

// 监听 AI 消息变化，自动滚动到底部
watch(() => aiChatStore.aiMessages.value, () => {
  scrollAiChatToBottom()
}, { deep: true })

// 发送AI消息
const sendAiMessage = async () => {
  if (!aiInputMessage.value.trim()) return
  
  const newMessage = {
    type: 'user' as const,
    text: aiInputMessage.value,
    time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
    location: currentWindField.value || currentTurbine.value ? {
      windField: currentWindField.value,
      turbine: currentTurbine.value
    } : undefined
  }
  
  aiChatStore.addMessage(newMessage)
  const userMsg = aiInputMessage.value
  aiInputMessage.value = ''
  
  // 滚动到底部
  scrollAiChatToBottom()
  
  // 显示 AI 正在输入
  isAiTyping.value = true
  
  try {
    // 构建包含上下文的查询
    let contextQuery = userMsg
    if (currentWindField.value && currentTurbine.value) {
      contextQuery = `当前查看的是${currentWindField.value}的${currentTurbine.value}。${userMsg}`
    }
    
    // 调用 Dify API
    const response = await difyService.sendMessage(contextQuery, 'monitor-user')
    
    const replyMessage = {
      type: 'bot' as const,
      text: response.answer,
      time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    }
    
    aiChatStore.addMessage(replyMessage)
    
    scrollAiChatToBottom()
  } catch (error) {
    console.error('AI 回复失败:', error)
    
    // 如果 API 调用失败，使用备用回复
    const fallbackMessage = {
      type: 'bot' as const,
      text: '抱歉，我暂时无法回答您的问题。请稍后再试。',
      time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    }
    
    aiChatStore.addMessage(fallbackMessage)
    
    scrollAiChatToBottom()
  } finally {
    isAiTyping.value = false
  }
}

// 组件编辑器状态
const editorVisible = ref(false)
const currentComponent = ref({
  name: '',
  number: '',
  status: 'normal',
  temperature: 0,
  vibration: 0,
  runningHours: 0,
  lastMaintenance: '',
  remarks: ''
})

// 组件数据存储
const componentDataMap = ref<Record<string, any>>({})

// 工具编辑器状态
const toolEditorVisible = ref(false)
const currentTool = ref({
  name: '',
  number: '',
  status: 'available',
  department: '',
  usageCount: 0,
  purchaseDate: '',
  lastUsedDate: '',
  nextCalibrationDate: '',
  location: '',
  remarks: ''
})

// 工具数据存储
const toolDataMap = ref<Record<string, any>>({})

// 提供事件给子组件
provide('events', {
  eqDecomposeAnimation,
  eqComposeAnimation,
  startWarning,
  stopWarning,
})

// 返回地图
const goBack = () => {
  router.push('/')
}

// 加载组件数据
const loadComponentData = async () => {
  try {
    // 先尝试从 localStorage 加载
    const localData = localStorage.getItem('componentData')
    if (localData) {
      componentDataMap.value = JSON.parse(localData)
    }
    
    // 然后尝试从 API 加载
    const response = await fetch('/api/component-data.json')
    if (response.ok) {
      componentDataMap.value = await response.json()
    }
  } catch (error) {
  }
}

// 加载工具数据
const loadToolData = async () => {
  try {
    // 先尝试从 localStorage 加载
    const localData = localStorage.getItem('toolData')
    if (localData) {
      toolDataMap.value = JSON.parse(localData)
    }
    
    // 然后尝试从 API 加载
    const response = await fetch('/api/tool-data.json')
    if (response.ok) {
      toolDataMap.value = await response.json()
    }
  } catch (error) {
  }
}

// 处理组件点击
const handleComponentClick = (componentName: string) => {
  const existingData = componentDataMap.value[componentName] || {}
  currentComponent.value = {
    name: componentName,
    number: existingData.number || `${componentName}-001`,
    status: existingData.status || 'normal',
    temperature: existingData.temperature || 45.5,
    vibration: existingData.vibration || 2.3,
    runningHours: existingData.runningHours || 15680,
    lastMaintenance: existingData.lastMaintenance || new Date().toISOString().split('T')[0],
    remarks: existingData.remarks || ''
  }
  editorVisible.value = true
}

// 保存组件数据
const saveComponentData = async (data: any) => {
  componentDataMap.value[data.name] = data
  
  try {
    const response = await fetch('/api/save-component-data', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        componentName: data.name,
        data: data,
        allData: componentDataMap.value
      })
    })
    
    if (response.ok) {
    } else {
      console.error('保存失败')
    }
  } catch (error) {
    console.error('保存错误:', error)
    // 降级方案：保存到 localStorage
    localStorage.setItem('componentData', JSON.stringify(componentDataMap.value))
  }
  
  editorVisible.value = false
}

// 关闭编辑器
const closeEditor = () => {
  editorVisible.value = false
}

// 处理工具点击事件（单击显示编辑器）
const handleToolClick = (toolName: string) => {
  const existingData = toolDataMap.value[toolName] || {}
  
  currentTool.value = {
    name: toolName,
    number: existingData.number || `TOOL-${toolName}-001`,
    status: existingData.status || 'available',
    department: existingData.department || '维修班组1',
    usageCount: existingData.usageCount || 0,
    purchaseDate: existingData.purchaseDate || new Date().toISOString().split('T')[0],
    lastUsedDate: existingData.lastUsedDate || '',
    nextCalibrationDate: existingData.nextCalibrationDate || '',
    location: existingData.location || '工具间A区',
    remarks: existingData.remarks || ''
  }
  toolEditorVisible.value = true
}

// 保存工具数据
const saveToolData = async (data: any) => {
  toolDataMap.value[data.name] = data
  
  try {
    const response = await fetch('/api/save-tool-data', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        toolName: data.name,
        data: data,
        allData: toolDataMap.value
      })
    })
    
    if (response.ok) {
    } else {
      console.error('❌ 保存失败')
    }
  } catch (error) {
    console.error('❌ 保存错误:', error)
    // 降级方案：保存到 localStorage
    localStorage.setItem('toolData', JSON.stringify(toolDataMap.value))
  }
  
  toolEditorVisible.value = false
}

// 关闭工具编辑器
const closeToolEditor = () => {
  toolEditorVisible.value = false
}

// 处理工具双击事件
const handleToolDoubleClick = (toolName: string) => {
  // 添加可拖动的3D工具到场景
  addDraggableTool(toolName)
}

// 处理工具拖拽开始
const handleToolDragStart = (toolName: string, event: DragEvent) => {
  // 可以在这里添加视觉反馈
}

// 处理工具拖拽结束
const handleToolDragEnd = (event: DragEvent) => {
}

// 处理拖拽悬停（在3D场景上）
const handleDragOver = (event: DragEvent) => {
  // 允许放置
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = 'copy'
  }
}

// 处理放置工具到3D场景
const handleDrop = (event: DragEvent) => {
  
  // 工具可以在任何状态下放置（不仅限于分解状态）
  const toolName = event.dataTransfer?.getData('text/plain')
  
  if (toolName && container.value) {
    
    // 计算放置位置（鼠标在3D场景中的位置）
    const rect = container.value.getBoundingClientRect()
    
    const mouse = {
      x: ((event.clientX - rect.left) / rect.width) * 2 - 1,
      y: -((event.clientY - rect.top) / rect.height) * 2 + 1
    }
    
    
    // 添加工具到场景，并放置在鼠标位置附近
    addDraggableToolAtPosition(toolName, mouse)
  } else {
  }
}

onMounted(async () => {
  // 确保 container 已经准备好
  await nextTick()
  
  // 等待一下，确保 DOM 完全渲染
  setTimeout(() => {
    loadComponentData()
    loadToolData() // 加载工具数据
    // 设置组件点击回调
    onComponentClick.value = handleComponentClick
    
    // 初始化时滚动AI聊天到底部
    scrollAiChatToBottom()
    
    // 在窗口级别添加拖放事件监听，确保能捕获到所有拖放操作
    const windowDragOverHandler = (e: DragEvent) => {
      // 阻止默认行为，允许放置
      e.preventDefault()
      e.stopPropagation()
      if (e.dataTransfer) {
        e.dataTransfer.dropEffect = 'copy'
      }
    }
    
    const windowDropHandler = (e: DragEvent) => {
      // 阻止默认行为
      e.preventDefault()
      e.stopPropagation()
      
      // 检查是否在 3D 区域内放置
      if (container.value) {
        const rect = container.value.getBoundingClientRect()
        const isInContainer = 
          e.clientX >= rect.left && 
          e.clientX <= rect.right &&
          e.clientY >= rect.top &&
          e.clientY <= rect.bottom
        
        
        if (isInContainer) {
          handleDrop(e)
        } else {
        }
      } else {
      }
    }
    
    window.addEventListener('dragover', windowDragOverHandler, false)
    window.addEventListener('drop', windowDropHandler, false)
  }, 100)
})
</script>

<style lang="scss" scoped>
.monitor-view {
  position: relative;
  width: 100%;
  height: 100%;
}
.back-button {
  position: fixed;
  top: 12px;
  left: 20px;
  z-index: 99999;
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 10px 18px;
  font-size: 14px;
  font-weight: 500;
  color: #fff;
  pointer-events: auto;
  cursor: pointer;
  background: linear-gradient(135deg, rgba(13, 148, 136, 30%) 0%, rgba(20, 184, 166, 20%) 100%);
  border: 1.5px solid rgba(94, 234, 212, 60%);
  border-radius: 8px;
  box-shadow: 0 4px 15px rgba(13, 148, 136, 20%);
  transition: all 0.3s ease;
  backdrop-filter: blur(10px);
  i {
    font-size: 15px;
    transition: transform 0.3s ease;
  }
  &:hover {
    background: linear-gradient(135deg, rgba(13, 148, 136, 50%) 0%, rgba(20, 184, 166, 40%) 100%);
    border-color: #14b8a6;
    box-shadow: 0 6px 20px rgba(20, 184, 166, 40%);
    transform: translateY(-2px);
    i {
      transform: scale(1.15);
    }
  }
  &:active {
    transform: translateY(0) scale(0.98);
  }
}
.tools-button {
  position: fixed;
  top: 12px;
  left: 150px;
  z-index: 99999;
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 10px 18px;
  font-size: 14px;
  font-weight: 500;
  color: #fff;
  pointer-events: auto;
  cursor: pointer;
  background: linear-gradient(135deg, rgba(255, 140, 0, 30%) 0%, rgba(255, 165, 0, 20%) 100%);
  border: 1.5px solid rgba(255, 165, 0, 60%);
  border-radius: 8px;
  box-shadow: 0 4px 15px rgba(255, 140, 0, 20%);
  transition: all 0.3s ease;
  backdrop-filter: blur(10px);
  i {
    font-size: 15px;
    transition: transform 0.3s ease;
  }
  &:hover {
    background: linear-gradient(135deg, rgba(255, 140, 0, 50%) 0%, rgba(255, 165, 0, 40%) 100%);
    border-color: #ffa500;
    box-shadow: 0 6px 20px rgba(255, 140, 0, 40%);
    transform: translateY(-2px);
    i {
      transform: scale(1.15);
    }
  }
  &.active {
    background: linear-gradient(135deg, rgba(0, 200, 0, 30%) 0%, rgba(0, 255, 0, 20%) 100%);
    border: 1.5px solid rgba(0, 255, 0, 60%);
    box-shadow: 0 4px 15px rgba(0, 200, 0, 20%);
    &:hover {
      background: linear-gradient(135deg, rgba(0, 200, 0, 50%) 0%, rgba(0, 255, 0, 40%) 100%);
      border-color: #0f0;
      box-shadow: 0 6px 20px rgba(0, 200, 0, 40%);
    }
  }
  &:active {
    transform: translateY(0) scale(0.98);
  }
}
.status-indicator {
  position: fixed;
  top: 20px;
  left: 360px;
  z-index: 99999;
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 12px 20px;
  font-size: 14px;
  font-weight: 500;
  color: #74fabd;
  pointer-events: none;
  background: linear-gradient(135deg, rgba(116, 250, 189, 20%) 0%, rgba(100, 230, 170, 15%) 100%);
  border: 2px solid rgba(116, 250, 189, 50%);
  border-radius: 10px;
  box-shadow: 0 4px 15px rgba(116, 250, 189, 30%);
  backdrop-filter: blur(10px);
  animation: pulse 2s ease-in-out infinite;
  i {
    font-size: 16px;
  }
  
  @keyframes pulse {
    0%, 100% {
      box-shadow: 0 4px 15px rgba(116, 250, 189, 30%);
    }
    50% {
      box-shadow: 0 4px 20px rgba(116, 250, 189, 50%);
    }
  }
}

// AI助手面板样式
.ai-chat-content {
  display: flex;
  flex-direction: column;
  height: 100%;
  .chat-messages {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: 12px;
    padding: 10px;
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
    .empty-state {
      display: flex;
      flex: 1;
      flex-direction: column;
      gap: 10px;
      align-items: center;
      justify-content: center;
      color: rgba(255, 255, 255, 40%);
      text-align: center;
      i {
        font-size: 36px;
        color: rgba(20, 184, 166, 30%);
      }
      p {
        margin: 0;
        font-size: 13px;
      }
    }
    .message {
      display: flex;
      gap: 8px;
      animation: message-slide 0.3s ease;
      &.user {
        flex-direction: row-reverse;
        .message-avatar {
          background: rgba(20, 184, 166, 20%);
        }
        .message-content {
          align-items: flex-end;
          .message-text {
            background: rgba(20, 184, 166, 15%);
          }
        }
      }
      &.bot .message-avatar {
        background: rgba(94, 234, 212, 20%);
      }
      .message-avatar {
        display: flex;
        flex-shrink: 0;
        align-items: center;
        justify-content: center;
        width: 30px;
        height: 30px;
        border-radius: 50%;
        i {
          font-size: 14px;
          color: #fff;
        }
      }
      .message-content {
        display: flex;
        flex: 1;
        flex-direction: column;
        gap: 2px;
        max-width: 75%;
        .message-location {
          display: flex;
          gap: 4px;
          align-items: center;
          padding: 0 4px;
          font-size: 10px;
          color: rgba(20, 184, 166, 80%);
          i {
            font-size: 9px;
          }
        }
        .message-text {
          padding: 8px 12px;
          font-size: 13px;
          line-height: 1.4;
          color: #fff;
          word-wrap: break-word;
          background: rgba(13, 148, 136, 10%);
          border-radius: 8px;
        }
        .message-time {
          padding: 0 4px;
          font-size: 10px;
          color: rgba(255, 255, 255, 40%);
        }
      }
    }
  }
  .chat-input {
    display: flex;
    gap: 8px;
    padding: 10px;
    border-top: 1px solid rgba(94, 234, 212, 20%);
    input {
      flex: 1;
      padding: 8px 12px;
      font-size: 13px;
      color: #fff;
      background: rgba(0, 20, 40, 30%);
      border: 1px solid rgba(94, 234, 212, 20%);
      border-radius: 6px;
      outline: none;
      transition: all 0.3s ease;
      &::placeholder {
        color: rgba(255, 255, 255, 30%);
      }
      &:focus {
        background: rgba(0, 20, 40, 50%);
        border-color: rgba(20, 184, 166, 50%);
      }
    }
    button {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 36px;
      height: 36px;
      font-size: 14px;
      color: #fff;
      cursor: pointer;
      background: rgba(13, 148, 136, 20%);
      border: 1px solid rgba(20, 184, 166, 30%);
      border-radius: 6px;
      transition: all 0.3s ease;
      &:hover:not(:disabled) {
        background: rgba(13, 148, 136, 35%);
        border-color: rgba(20, 184, 166, 50%);
      }
      &:disabled {
        cursor: not-allowed;
        opacity: 0.4;
      }
    }
  }
  
  // 框选矩形框样式
  .box-select-overlay {
    position: absolute;
    z-index: 1000;
    box-sizing: border-box;
    pointer-events: none;
    background: rgba(13, 148, 136, 10%);
    border: 2px dashed rgba(20, 184, 166, 80%);
  }
}

@keyframes message-slide {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

</style>

