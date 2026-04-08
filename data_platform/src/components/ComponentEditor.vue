<template>
  <div v-if="visible" class="component-editor-overlay" @click.self="close">
    <div class="component-editor">
      <div class="editor-header">
        <h3>{{ componentData.name }} - 组件信息</h3>
        <button class="close-btn" @click="close">
          <i class="fa-solid fa-times"></i>
        </button>
      </div>
      
      <div class="editor-body">
        <div class="form-group">
          <label>组件名称</label>
          <input v-model="formData.name" type="text" readonly />
        </div>
        
        <div class="form-group">
          <label>组件编号</label>
          <input v-model="formData.number" type="text" />
        </div>
        
        <div class="form-group">
          <label>运行状态</label>
          <select v-model="formData.status">
            <option value="normal">正常</option>
            <option value="warning">告警</option>
            <option value="error">故障</option>
            <option value="maintenance">维护中</option>
          </select>
        </div>
        
        <div class="form-group">
          <label>温度 (°C)</label>
          <input v-model.number="formData.temperature" type="number" step="0.1" />
        </div>
        
        <div class="form-group">
          <label>振动值 (mm/s)</label>
          <input v-model.number="formData.vibration" type="number" step="0.01" />
        </div>
        
        <div class="form-group">
          <label>运行时长 (小时)</label>
          <input v-model.number="formData.runningHours" type="number" />
        </div>
        
        <div class="form-group">
          <label>最后维护日期</label>
          <input v-model="formData.lastMaintenance" type="date" />
        </div>
        
        <div class="form-group full-width">
          <label>备注</label>
          <textarea v-model="formData.remarks" rows="3"></textarea>
        </div>
      </div>
      
      <div class="editor-footer">
        <button class="btn-cancel" @click="close">取消</button>
        <button class="btn-save" @click="save">保存</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

interface ComponentData {
  name: string
  number?: string
  status?: string
  temperature?: number
  vibration?: number
  runningHours?: number
  lastMaintenance?: string
  remarks?: string
}

interface Props {
  visible: boolean
  componentData: ComponentData
}

const props = defineProps<Props>()
const emit = defineEmits<{
  close: []
  save: [data: ComponentData]
}>()

const formData = ref<ComponentData>({
  name: '',
  number: '',
  status: 'normal',
  temperature: 0,
  vibration: 0,
  runningHours: 0,
  lastMaintenance: '',
  remarks: ''
})

watch(() => props.componentData, (newData) => {
  if (newData) {
    formData.value = { ...newData }
  }
}, { immediate: true, deep: true })

const close = () => {
  emit('close')
}

const save = () => {
  emit('save', formData.value)
}
</script>

<style lang="scss" scoped>
.component-editor-overlay {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  left: 0;
  z-index: 100000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 70%);
  backdrop-filter: blur(5px);
}
.component-editor {
  display: flex;
  flex-direction: column;
  width: 600px;
  max-width: 90vw;
  max-height: 90vh;
  overflow: hidden;
  background: linear-gradient(135deg, rgba(10, 22, 40, 95%) 0%, rgba(26, 38, 66, 95%) 100%);
  border: 2px solid rgba(94, 234, 212, 50%);
  border-radius: 16px;
  box-shadow: 0 8px 32px rgba(13, 148, 136, 30%);
}
.editor-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid rgba(94, 234, 212, 30%);
  h3 {
    margin: 0;
    font-size: 20px;
    font-weight: bold;
    color: #14b8a6;
  }
  .close-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    padding: 0;
    font-size: 24px;
    color: #fff;
    cursor: pointer;
    background: transparent;
    border: none;
    border-radius: 4px;
    transition: all 0.3s;
    &:hover {
      color: #f44;
      background: rgba(255, 68, 68, 20%);
    }
  }
}
.editor-body {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  padding: 24px;
  overflow-y: auto;
  .form-group {
    display: flex;
    flex-direction: column;
    gap: 8px;
    &.full-width {
      grid-column: 1 / -1;
    }
    label {
      font-size: 14px;
      font-weight: 500;
      color: #8fb9f5;
    }
    input, select, textarea {
      padding: 10px 12px;
      font-size: 14px;
      color: #fff;
      background: rgba(13, 148, 136, 10%);
      border: 1px solid rgba(94, 234, 212, 30%);
      border-radius: 8px;
      transition: all 0.3s;
      &:focus {
        background: rgba(13, 148, 136, 15%);
        border-color: #14b8a6;
        outline: none;
      }
      &:read-only {
        cursor: not-allowed;
        background: rgba(13, 148, 136, 5%);
      }
    }
    textarea {
      font-family: inherit;
      resize: vertical;
    }
    select {
      cursor: pointer;
      option {
        color: #fff;
        background: #1a2642;
      }
    }
  }
}
.editor-footer {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  padding: 16px 24px;
  border-top: 1px solid rgba(94, 234, 212, 30%);
  button {
    padding: 10px 24px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    border: none;
    border-radius: 8px;
    transition: all 0.3s;
    &.btn-cancel {
      color: #fff;
      background: rgba(255, 255, 255, 10%);
      border: 1px solid rgba(255, 255, 255, 20%);
      &:hover {
        background: rgba(255, 255, 255, 15%);
      }
    }
    &.btn-save {
      color: #fff;
      background: linear-gradient(135deg, rgba(13, 148, 136, 80%) 0%, rgba(20, 184, 166, 80%) 100%);
      border: 1px solid rgba(94, 234, 212, 60%);
      &:hover {
        background: linear-gradient(135deg, rgba(13, 148, 136, 100%) 0%, rgba(20, 184, 166, 100%) 100%);
        box-shadow: 0 4px 15px rgba(20, 184, 166, 40%);
      }
    }
  }
}
</style>
