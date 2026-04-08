<template>
  <div v-if="visible" class="tool-editor-overlay" @click.self="close">
    <div class="tool-editor">
      <div class="editor-header">
        <h3>{{ toolData.name }} - 工具信息</h3>
        <button class="close-btn" @click="close">
          <i class="fa-solid fa-times"></i>
        </button>
      </div>
      
      <div class="editor-body">
        <div class="form-group">
          <label>工具名称</label>
          <input v-model="formData.name" type="text" readonly />
        </div>
        
        <div class="form-group">
          <label>工具编号</label>
          <input v-model="formData.number" type="text" />
        </div>
        
        <div class="form-group">
          <label>工具状态</label>
          <select v-model="formData.status">
            <option value="available">可用</option>
            <option value="in-use">使用中</option>
            <option value="maintenance">维护中</option>
            <option value="damaged">损坏</option>
          </select>
        </div>
        
        <div class="form-group">
          <label>所属部门</label>
          <input v-model="formData.department" type="text" placeholder="如：维修班组1" />
        </div>
        
        <div class="form-group">
          <label>使用次数</label>
          <input v-model.number="formData.usageCount" type="number" />
        </div>
        
        <div class="form-group">
          <label>购买日期</label>
          <input v-model="formData.purchaseDate" type="date" />
        </div>
        
        <div class="form-group">
          <label>最后使用日期</label>
          <input v-model="formData.lastUsedDate" type="date" />
        </div>
        
        <div class="form-group">
          <label>下次校验日期</label>
          <input v-model="formData.nextCalibrationDate" type="date" />
        </div>
        
        <div class="form-group full-width">
          <label>存放位置</label>
          <input v-model="formData.location" type="text" placeholder="如：工具间A区3号柜" />
        </div>
        
        <div class="form-group full-width">
          <label>备注</label>
          <textarea v-model="formData.remarks" rows="3" placeholder="工具使用说明、注意事项等"></textarea>
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

interface ToolData {
  name: string
  number?: string
  status?: string
  department?: string
  usageCount?: number
  purchaseDate?: string
  lastUsedDate?: string
  nextCalibrationDate?: string
  location?: string
  remarks?: string
}

interface Props {
  visible: boolean
  toolData: ToolData
}

const props = defineProps<Props>()
const emit = defineEmits<{
  close: []
  save: [data: ToolData]
}>()

const formData = ref<ToolData>({
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

watch(() => props.toolData, (newData) => {
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
.tool-editor-overlay {
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
.tool-editor {
  display: flex;
  flex-direction: column;
  width: 600px;
  max-width: 90vw;
  max-height: 90vh;
  overflow: hidden;
  background: linear-gradient(135deg, rgba(10, 30, 20, 95%) 0%, rgba(20, 50, 35, 95%) 100%);
  border: 2px solid rgba(116, 250, 189, 50%);
  border-radius: 16px;
  box-shadow: 0 8px 32px rgba(116, 250, 189, 30%);
}
.editor-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid rgba(116, 250, 189, 30%);
  h3 {
    margin: 0;
    font-size: 20px;
    font-weight: bold;
    color: #74fabd;
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
      color: #a8e6cf;
    }
    input, select, textarea {
      padding: 10px 12px;
      font-size: 14px;
      color: #fff;
      background: rgba(116, 250, 189, 10%);
      border: 1px solid rgba(116, 250, 189, 30%);
      border-radius: 8px;
      transition: all 0.3s;
      &:focus {
        background: rgba(116, 250, 189, 15%);
        border-color: #74fabd;
        outline: none;
      }
      &:read-only {
        cursor: not-allowed;
        background: rgba(116, 250, 189, 5%);
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
        background: #1a3026;
      }
    }
  }
}
.editor-footer {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  padding: 16px 24px;
  border-top: 1px solid rgba(116, 250, 189, 30%);
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
      background: linear-gradient(135deg, rgba(116, 250, 189, 80%) 0%, rgba(100, 230, 170, 80%) 100%);
      border: 1px solid rgba(116, 250, 189, 60%);
      &:hover {
        background: linear-gradient(135deg, rgba(116, 250, 189, 100%) 0%, rgba(100, 230, 170, 100%) 100%);
        box-shadow: 0 4px 15px rgba(116, 250, 189, 40%);
      }
    }
  }
}
</style>

