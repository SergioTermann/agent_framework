<template>
  <LayoutPanel title="维修工具">
    <div class="tools-panel">
      <div class="tools-grid">
        <div 
          v-for="tool in tools" 
          :key="tool.name"
          class="tool-item"
          :class="{ active: selectedTool === tool.name, dragging: draggingTool === tool.name }"
          draggable="true"
          @click.stop="selectTool(tool.name)"
          @dblclick.stop="handleDoubleClick(tool.name)"
          @dragstart="handleDragStart($event, tool.name)"
          @dragend="handleDragEnd"
        >
          <div class="tool-icon">
            <i :class="tool.icon"></i>
          </div>
          <div class="tool-name">{{ tool.name }}</div>
        </div>
      </div>
    </div>
  </LayoutPanel>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { LayoutPanel } from '@/layout'

const emit = defineEmits<{
  toolDoubleClick: [toolName: string]
  toolClick: [toolName: string]
  toolDragStart: [toolName: string, event: DragEvent]
  toolDragEnd: [event: DragEvent]
}>()

const selectedTool = ref<string | null>(null)
const draggingTool = ref<string | null>(null)

const tools = [
  { name: '扳手', icon: 'fa-solid fa-wrench' },
  { name: '螺丝刀', icon: 'fa-solid fa-screwdriver' },
  { name: '钳子', icon: 'fa-solid fa-hand' },
  { name: '工具箱', icon: 'fa-solid fa-toolbox' },
  { name: '手电筒', icon: 'fa-solid fa-flashlight' },
  { name: '油桶', icon: 'fa-solid fa-oil-can' },
]

const selectTool = (toolName: string) => {
  selectedTool.value = selectedTool.value === toolName ? null : toolName
  emit('toolClick', toolName)
}

const handleDoubleClick = (toolName: string) => {
  emit('toolDoubleClick', toolName)
}

const handleDragStart = (event: DragEvent, toolName: string) => {
  draggingTool.value = toolName
  
  // 设置拖拽数据
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'copy'
    // 使用多种格式设置数据，确保兼容性
    event.dataTransfer.setData('text/plain', toolName)
    event.dataTransfer.setData('text/html', toolName)
    event.dataTransfer.setData('application/x-tool-name', toolName)
    
    // 创建自定义拖拽图像
    const dragImage = event.target as HTMLElement
    if (dragImage) {
      event.dataTransfer.setDragImage(dragImage, 0, 0)
    }
  } else {
  }
  
  // 不阻止事件传播，让拖放事件正常工作
  emit('toolDragStart', toolName, event)
}

const handleDragEnd = (event: DragEvent) => {
  draggingTool.value = null
  emit('toolDragEnd', event)
}
</script>

<style lang="scss" scoped>
.tools-panel {
  position: relative;
  z-index: 999;
  height: 100%;
  padding: 10px;
  overflow-x: hidden;
  overflow-y: auto;
  pointer-events: auto !important;
  
  // 滚动条样式 - 青绿色调
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
}
.tools-grid {
  position: relative;
  z-index: 999;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  min-height: min-content;
  pointer-events: auto !important;
}
.tool-item {
  position: relative;
  z-index: 10;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 15px;
  pointer-events: auto !important;
  cursor: pointer;
  user-select: none;
  background: linear-gradient(135deg, rgba(116, 250, 189, 10%), rgba(116, 250, 189, 5%));
  border: 1px solid rgba(116, 250, 189, 20%);
  border-radius: 8px;
  transition: all 0.3s ease;
  &:hover {
    z-index: 11;
    background: linear-gradient(135deg, rgba(116, 250, 189, 20%), rgba(116, 250, 189, 10%));
    border-color: rgba(116, 250, 189, 40%);
    box-shadow: 0 4px 12px rgba(116, 250, 189, 30%);
    transform: translateY(-2px);
  }
  &.active {
    z-index: 11;
    background: linear-gradient(135deg, rgba(116, 250, 189, 30%), rgba(116, 250, 189, 15%));
    border-color: #74fabd;
    box-shadow: 0 0 15px rgba(116, 250, 189, 50%);
  }
  &.dragging {
    opacity: 0.5;
    transform: scale(0.95);
  }
  .tool-icon {
    margin-bottom: 8px;
    font-size: 32px;
    color: #74fabd;
    pointer-events: none;
  }
  .tool-name {
    font-size: 14px;
    color: #fff;
    text-align: center;
    pointer-events: none;
  }
}
</style>

