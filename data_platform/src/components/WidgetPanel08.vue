<template>
  <LayoutPanel>
    <div class="wrap">
      <div class="item-list" ref="container">
        <div
          class="item"
          v-for="item in list"
          :key="item.id"
          :class="{ critical: item.level === '严重', warning: item.level === '警告' }"
        >
          <div class="item-code">{{ item.code }}</div>
          <div class="item-desc">{{ item.description }}</div>
          <div class="item-field">{{ item.windField }}</div>
          <div class="item-level">{{ item.level }}</div>
          <div class="item-time">{{ item.time }}</div>
        </div>
      </div>
    </div>
  </LayoutPanel>
</template>
<script setup lang="ts">
import { LayoutPanel } from '@/layout'
import { ref, onMounted, onUnmounted } from 'vue'
import { Random } from 'mockjs'

// 故障码定义
const faultCodes = [
  { code: 'E001', desc: '发电机温度过高', level: '严重' },
  { code: 'E002', desc: '齿轮箱润滑油压力低', level: '严重' },
  { code: 'W001', desc: '叶片振动异常', level: '警告' },
  { code: 'W002', desc: '偏航系统响应延迟', level: '警告' },
  { code: 'E003', desc: '主轴承温度异常', level: '严重' },
  { code: 'W003', desc: '变桨系统电流波动', level: '警告' },
  { code: 'E004', desc: '变流器过载保护', level: '严重' },
  { code: 'W004', desc: '冷却系统效率下降', level: '警告' },
  { code: 'E005', desc: '控制柜通讯故障', level: '严重' },
  { code: 'W005', desc: '风速传感器偏差', level: '警告' },
]

// 风场列表
const windFields = [
  '长岭风场',
  '白城风场',
  '通榆风场',
  '洮南风场',
  '镇赉风场',
]

// 生成历史故障记录
interface FaultItem {
  id: number
  code: string
  description: string
  windField: string
  level: string
  time: string
}

const list = ref<FaultItem[]>(
  Array.from({ length: 12 }, (_, index) => {
    const fault = Random.pick(faultCodes)
    return {
      id: index,
      code: fault.code,
      description: fault.desc,
      windField: Random.pick(windFields),
      level: fault.level,
      time: Random.datetime('MM/dd HH:mm:ss'),
    }
  }).sort((a, b) => new Date(b.time).getTime() - new Date(a.time).getTime())
)

const container = ref<HTMLElement>()
let timer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  if (timer) window.clearInterval(timer)
  // 每5秒滚动一次
  timer = setInterval(() => {
    if (!container.value) return
    container.value.classList.add('scroll')
    setTimeout(() => {
      if (!timer || !container.value) return void 0
      container.value.classList.remove('scroll')
      list.value.push(list.value.shift())
    }, 2000)
  }, 5000)
})

onUnmounted(() => {
  if (timer) window.clearInterval(timer)
})
</script>

<style lang="scss" scoped>
@keyframes row-out {
  from {
    top: 0;
  }
  to {
    top: -40px;
  }
}
.wrap {
  height: 100%;
  overflow: hidden;
}
.item-list {
  display: flex;
  flex-direction: column;
  grid-gap: 8px;
  height: 100%;
  &.scroll {
    .item:first-child {
      position: relative;
      animation: row-out 2s ease-in-out forwards;
    }
  }
  .item {
    display: grid;
    grid-template-columns: 70px 1fr 100px 50px 130px;
    grid-gap: 10px;
    align-items: center;
    padding: 8px 12px;
    font-size: 13px;
    background: linear-gradient(90deg, rgba(13, 148, 136, 10%) 0%, rgba(13, 148, 136, 5%) 100%);
    border-left: 3px solid #0d9488;
    border-radius: 4px;
    transition: all 0.3s;
    &:hover {
      background: linear-gradient(90deg, rgba(13, 148, 136, 20%) 0%, rgba(13, 148, 136, 10%) 100%);
      transform: translateX(5px);
    }
    &.warning {
      background: linear-gradient(90deg, rgba(255, 165, 0, 10%) 0%, rgba(255, 165, 0, 5%) 100%);
      border-left-color: #ffa500;
    }
    &.critical {
      background: linear-gradient(90deg, rgba(255, 68, 68, 10%) 0%, rgba(255, 68, 68, 5%) 100%);
      border-left-color: #f44;
    }
    .item-code {
      font-family: 'Courier New', monospace;
      font-size: 14px;
      font-weight: bold;
      color: #14b8a6;
    }
    .item-desc {
      overflow: hidden;
      color: #fff;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .item-field {
      overflow: hidden;
      font-size: 13px;
      color: #5eead4;
      text-align: center;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .item-level {
      padding: 2px 8px;
      font-size: 12px;
      font-weight: bold;
      text-align: center;
      border-radius: 4px;
    }
    &.warning .item-level {
      color: #ffa500;
      background: rgba(255, 165, 0, 20%);
    }
    &.critical .item-level {
      color: #f44;
      background: rgba(255, 68, 68, 20%);
    }
    .item-time {
      font-size: 12px;
      color: #8fb9f5;
      text-align: right;
    }
  }
}
</style>

