<template>
  <div class="video-detection-panel" :style="{ left: position.x + 'px', top: position.y + 'px' }">
    <div class="panel-header" @mousedown="startDrag">
      <div class="panel-title">
        <i class="fa-solid fa-brain"></i>
        <span>风电第一视角 - AI智能分析</span>
      </div>
      <div class="panel-controls">
        <button @click="toggleMinimize" class="control-btn">
          <i :class="minimized ? 'fa-solid fa-window-maximize' : 'fa-solid fa-window-minimize'"></i>
        </button>
        <button @click="$emit('close')" class="control-btn close-btn">
          <i class="fa-solid fa-xmark"></i>
        </button>
      </div>
    </div>
    
    <div class="panel-body" v-show="!minimized">
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
        
        <!-- 错误提示 -->
        <div v-if="videoError" class="video-error">
          <i class="fa-solid fa-exclamation-triangle"></i>
          <p>视频加载失败</p>
          <small>请将视频文件放到 <code>public/videos/turbine-view.mp4</code></small>
          <small>或点击下方按钮选择本地视频</small>
          <label class="upload-btn">
            <i class="fa-solid fa-upload"></i>
            选择视频文件
            <input 
              type="file" 
              accept="video/*" 
              @change="handleFileUpload" 
              style="display: none"
            />
          </label>
        </div>
      </div>
      
      <div class="detection-info">
        <div class="info-item">
          <span class="info-label">AI模型:</span>
          <span class="info-value">{{ aiModel }}</span>
        </div>
        <div class="info-item">
          <span class="info-label">分析状态:</span>
          <span class="info-value" :class="{ analyzing: isAnalyzing }">
            {{ isAnalyzing ? '分析中...' : '就绪' }}
          </span>
        </div>
        <div class="info-item">
          <span class="info-label">检测对象:</span>
          <span class="info-value">{{ detectedObjects.length }} 个</span>
        </div>
      </div>
      
      <!-- AI分析结果 -->
      <div class="ai-analysis" v-if="aiAnalysis">
        <div class="analysis-header">
          <i class="fa-solid fa-wand-magic-sparkles"></i>
          <span>AI分析结果</span>
        </div>
        <div class="analysis-content">{{ aiAnalysis }}</div>
      </div>
      
      <div class="detected-objects" v-if="detectedObjects.length > 0">
        <div 
          v-for="(obj, index) in detectedObjects" 
          :key="index"
          class="object-tag"
          :style="{ borderColor: obj.color }"
        >
          <span class="object-name">{{ obj.name }}</span>
          <span class="object-confidence">{{ (obj.confidence * 100).toFixed(1) }}%</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, computed } from 'vue'
import { visionService } from '@/services/visionService'

// Props
const props = defineProps<{
  videoSrc?: string
}>()

// Emits
const emit = defineEmits<{
  close: []
}>()

// Refs
const videoElement = ref<HTMLVideoElement | null>(null)
const detectionCanvas = ref<HTMLCanvasElement | null>(null)
const videoContainer = ref<HTMLDivElement | null>(null)

// State
const minimized = ref(false)
const position = ref({ x: 20, y: 80 })
const isDragging = ref(false)
const dragOffset = ref({ x: 0, y: 0 })
const aiModel = ref('硅基流动 Qwen-VL-Max')
const isAnalyzing = ref(false)
const aiAnalysis = ref('')
const detectedObjects = ref<Array<{
  name: string
  confidence: number
  description?: string
  color: string
}>>([])
const videoError = ref(false)
const isPlaying = ref(false)
let analysisInterval: number | null = null
let lastAnalysisTime = 0

// 使用默认视频URL
const videoSrc = computed(() => {
  if (props.videoSrc) return props.videoSrc
  return '/videos/turbine-view.mp4'
})

// 风电设备颜色映射
const EQUIPMENT_COLORS: Record<string, string> = {
  '风机叶片': '#ff4444',
  '塔筒': '#44ff44',
  '机舱': '#4444ff',
  '轮毂': '#ffff44',
  '发电机': '#ff44ff',
  '齿轮箱': '#44ffff',
  '变流器': '#ff8844',
  '控制柜': '#88ff44',
}

// 拖动相关
const startDrag = (e: MouseEvent) => {
  isDragging.value = true
  dragOffset.value = {
    x: e.clientX - position.value.x,
    y: e.clientY - position.value.y
  }
  document.addEventListener('mousemove', onDrag)
  document.addEventListener('mouseup', stopDrag)
}

const onDrag = (e: MouseEvent) => {
  if (isDragging.value) {
    position.value = {
      x: e.clientX - dragOffset.value.x,
      y: e.clientY - dragOffset.value.y
    }
  }
}

const stopDrag = () => {
  isDragging.value = false
  document.removeEventListener('mousemove', onDrag)
  document.removeEventListener('mouseup', stopDrag)
}

// 最小化/最大化
const toggleMinimize = () => {
  minimized.value = !minimized.value
}

// 视频加载完成
const onVideoLoaded = () => {
  const video = videoElement.value
  const canvas = detectionCanvas.value
  if (video && canvas) {
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    videoError.value = false
  }
}

// 视频加载错误
const onVideoError = () => {
  videoError.value = true
  console.error('❌ 视频加载失败，请检查视频路径或网络连接')
}

// 手动播放/暂停
const togglePlay = () => {
  const video = videoElement.value
  if (!video) return
  
  if (video.paused) {
    video.play().then(() => {
      isPlaying.value = true
    }).catch(err => {
      console.error('播放失败:', err)
      videoError.value = true
    })
  } else {
    video.pause()
    isPlaying.value = false
  }
}

// 处理本地文件上传
const handleFileUpload = (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  
  if (file && file.type.startsWith('video/')) {
    const url = URL.createObjectURL(file)
    const video = videoElement.value
    
    if (video) {
      video.src = url
      videoError.value = false
      
      video.addEventListener('loadedmetadata', () => {
        video.play().then(() => {
          isPlaying.value = true
        }).catch(() => {
        })
      }, { once: true })
    }
  } else {
    alert('请选择有效的视频文件')
  }
}

// 开始AI分析
const startDetection = () => {
  if (analysisInterval) return
  isPlaying.value = true
  lastAnalysisTime = Date.now()
  
  // 立即进行一次分析
  analyzeCurrentFrame()
  
  // 每5秒分析一次（避免频繁调用API）
  analysisInterval = window.setInterval(analyzeCurrentFrame, 5000)
}

// 停止AI分析
const stopDetection = () => {
  if (analysisInterval) {
    window.clearInterval(analysisInterval)
    analysisInterval = null
    isPlaying.value = false
  }
}

// 分析当前帧
const analyzeCurrentFrame = async () => {
  const video = videoElement.value
  const canvas = detectionCanvas.value
  
  if (!video || !canvas || video.paused || video.ended) {
    return
  }
  
  isAnalyzing.value = true
  
  try {
    // 捕获当前帧
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    
    // 绘制视频帧到canvas
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
    
    // 转换为base64图像
    const imageData = canvas.toDataURL('image/jpeg', 0.8)
    
    // 调用多模态大模型分析
    const result = await visionService.analyzeFrame(imageData)
    
    if (result.success) {
      aiAnalysis.value = result.analysis
      
      // 更新检测对象
      if (result.detectedObjects && result.detectedObjects.length > 0) {
        detectedObjects.value = result.detectedObjects.map(obj => ({
          name: obj.name,
          confidence: obj.confidence,
          description: obj.description,
          color: EQUIPMENT_COLORS[obj.name] || '#14b8a6'
        }))
      }
      
    } else {
      console.warn('⚠️ AI分析失败:', result.error)
    }
  } catch (error) {
    console.error('❌ 分析过程出错:', error)
  } finally {
    isAnalyzing.value = false
  }
}

// 生命周期
onMounted(() => {
  // 尝试自动播放（可能被浏览器阻止）
  setTimeout(() => {
    const video = videoElement.value
    if (video && !videoError.value) {
      video.play().then(() => {
        isPlaying.value = true
      }).catch(() => {
        isPlaying.value = false
      })
    }
  }, 500)
})

onBeforeUnmount(() => {
  stopDetection()
  document.removeEventListener('mousemove', onDrag)
  document.removeEventListener('mouseup', stopDrag)
  if (videoElement.value) {
    videoElement.value.pause()
    videoElement.value.src = ''
    videoElement.value.load()
  }
})
</script>

<style scoped lang="scss">
.video-detection-panel {
  position: fixed;
  z-index: 1000;
  width: 480px;
  background: linear-gradient(135deg, rgba(0, 20, 40, 95%), rgba(0, 40, 80, 95%));
  border: 2px solid rgba(0, 255, 255, 30%);
  border-radius: 8px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 50%);
  backdrop-filter: blur(10px);
  .panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    cursor: move;
    user-select: none;
    background: linear-gradient(135deg, rgba(0, 100, 255, 20%), rgba(0, 200, 255, 20%));
    border-bottom: 1px solid rgba(0, 255, 255, 30%);
    .panel-title {
      display: flex;
      gap: 8px;
      align-items: center;
      font-size: 14px;
      font-weight: bold;
      color: #0ff;
      i {
        font-size: 16px;
      }
    }
    .panel-controls {
      display: flex;
      gap: 8px;
      .control-btn {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 28px;
        height: 28px;
        color: #fff;
        cursor: pointer;
        background: rgba(255, 255, 255, 10%);
        border: 1px solid rgba(255, 255, 255, 20%);
        border-radius: 4px;
        transition: all 0.3s;
        &:hover {
          background: rgba(255, 255, 255, 20%);
          border-color: rgba(255, 255, 255, 40%);
        }
        &.close-btn:hover {
          background: rgba(255, 0, 0, 30%);
          border-color: rgba(255, 0, 0, 60%);
        }
      }
    }
  }
  .panel-body {
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 16px;
    .video-container {
      position: relative;
      width: 100%;
      padding-bottom: 56.25%; // 16:9
      overflow: hidden;
      background: #000;
      border-radius: 6px;
      video {
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        object-fit: cover;
      }
      .detection-overlay {
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        pointer-events: none;
      }
      .video-controls {
        position: absolute;
        bottom: 10px;
        left: 50%;
        transform: translateX(-50%);
        .play-btn {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 50px;
          height: 50px;
          color: #0ff;
          cursor: pointer;
          background: rgba(0, 0, 0, 60%);
          border: 2px solid rgba(0, 255, 255, 60%);
          border-radius: 50%;
          transition: all 0.3s;
          &:hover {
            background: rgba(0, 100, 255, 80%);
            transform: scale(1.1);
          }
          i {
            font-size: 20px;
          }
        }
      }
      .video-error {
        position: absolute;
        top: 0;
        left: 0;
        display: flex;
        flex-direction: column;
        gap: 12px;
        align-items: center;
        justify-content: center;
        width: 100%;
        height: 100%;
        color: #ff6b6b;
        text-align: center;
        background: rgba(0, 0, 0, 90%);
        i {
          font-size: 48px;
        }
        p {
          margin: 0;
          font-size: 16px;
          font-weight: bold;
        }
        small {
          margin: 5px 0;
          font-size: 12px;
          color: rgba(255, 255, 255, 60%);
          code {
            padding: 2px 6px;
            font-family: monospace;
            background: rgba(255, 255, 255, 10%);
            border-radius: 3px;
          }
        }
        .upload-btn {
          display: flex;
          gap: 8px;
          align-items: center;
          padding: 10px 20px;
          margin-top: 15px;
          font-size: 14px;
          color: #fff;
          cursor: pointer;
          background: rgba(0, 200, 255, 80%);
          border: 2px solid #0ff;
          border-radius: 6px;
          transition: all 0.3s;
          &:hover {
            background: rgba(0, 200, 255, 100%);
            transform: scale(1.05);
          }
          i {
            font-size: 16px;
          }
        }
      }
    }
    .detection-info {
      display: flex;
      justify-content: space-around;
      padding: 12px;
      background: rgba(0, 0, 0, 30%);
      border-radius: 6px;
      .info-item {
        display: flex;
        flex-direction: column;
        gap: 4px;
        align-items: center;
        .info-label {
          font-size: 11px;
          color: rgba(255, 255, 255, 60%);
        }
        .info-value {
          font-size: 14px;
          font-weight: bold;
          color: #14b8a6;
          &.analyzing {
            color: #fa0;
            animation: pulse 1.5s ease-in-out infinite;
          }
        }
      }
    }
    .ai-analysis {
      padding: 12px;
      background: rgba(0, 50, 100, 50%);
      border: 1px solid rgba(13, 148, 136, 30%);
      border-radius: 6px;
      .analysis-header {
        display: flex;
        gap: 8px;
        align-items: center;
        margin-bottom: 10px;
        font-size: 13px;
        font-weight: bold;
        color: #14b8a6;
        i {
          color: #fa0;
        }
      }
      .analysis-content {
        max-height: 150px;
        overflow-y: auto;
        font-size: 12px;
        line-height: 1.6;
        color: rgba(255, 255, 255, 90%);
        white-space: pre-wrap;
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
      }
    }
    .detected-objects {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      .object-tag {
        display: flex;
        gap: 6px;
        align-items: center;
        padding: 6px 12px;
        font-size: 12px;
        background: rgba(13, 148, 136, 10%);
        border: 1px solid;
        border-radius: 20px;
        .object-name {
          font-weight: bold;
          color: #fff;
        }
        .object-confidence {
          color: rgba(255, 255, 255, 70%);
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
</style>

