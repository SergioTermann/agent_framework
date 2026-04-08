<template>
  <LayoutPanel>
    <div class="container">
      <div
        class="item"
        v-for="(item, index) in source"
        :key="index"
        :class="{ error: item.status, editing: editingIndex === index }"
      >
        <div class="icon" :class="item.icon"></div>
        <div class="label">{{ item.label }}</div>
        <div class="key" @click="startEdit(index)">
          <input
            v-if="editingIndex === index"
            v-model="editingValue"
            @blur="saveEdit(index)"
            @keyup.enter="saveEdit(index)"
            @keyup.esc="cancelEdit"
            class="value-input"
            type="number"
            step="any"
            ref="inputRefs"
          />
          <span v-else class="value">{{ item.value }}</span>
          <span class="unit">{{ item.unit }}</span>
        </div>
        <i class="alert fa-solid fa-triangle-exclamation"></i>
        <i v-if="editingIndex === index" class="edit-icon fa-solid fa-check" @click.stop="saveEdit(index)"></i>
      </div>
    </div>
  </LayoutPanel>
</template>
<script setup lang="ts">
import { LayoutPanel } from '@/layout'
import { Random } from 'mockjs'
import { ref, nextTick } from 'vue'

const source = ref([
  {
    icon: 'fa-solid fa-temperature-three-quarters',
    label: '温度',
    value: '23',
    unit: '度',
    status: Random.pick([true, false]),
  },
  {
    icon: 'fa-solid fa-umbrella',
    label: '湿度',
    value: '70',
    unit: '%',
    status: Random.pick([true, false]),
  },
  {
    icon: 'fa-solid fa-fan',
    label: '气压',
    value: '23',
    unit: 'kPa',
    status: Random.pick([true, false]),
  },
  {
    icon: 'fa-solid fa-wind',
    label: '最大风速',
    value: '11',
    unit: 'm/s',
    status: Random.pick([true, false]),
  },
  {
    icon: 'fa-solid fa-temperature-arrow-up',
    label: '环境温度',
    value: '15',
    unit: '度',
    status: Random.pick([true, false]),
  },
  {
    icon: 'fa-solid fa-weight-scale',
    label: '负荷率',
    value: '23',
    unit: '%',
    status: Random.pick([true, false]),
  },
  {
    icon: 'fa-solid fa-plug',
    label: '总功率',
    value: '12',
    unit: 'kVa',
    status: Random.pick([true, false]),
  },
  {
    icon: 'fa-solid fa-plug',
    label: '有功功率',
    value: '12',
    unit: 'kVa',
    status: Random.pick([true, false]),
  },
  {
    icon: 'fa-solid fa-plug',
    label: '无功功率',
    value: '12',
    unit: 'kVa',
    status: Random.pick([true, false]),
  },
])

const editingIndex = ref<number | null>(null)
const editingValue = ref('')
const inputRefs = ref<(HTMLInputElement | null)[]>([])

const startEdit = (index: number) => {
  editingIndex.value = index
  editingValue.value = source.value[index].value
  nextTick(() => {
    const input = inputRefs.value[index]
    if (input) {
      input.focus()
      input.select()
    }
  })
}

const saveEdit = (index: number) => {
  if (editingIndex.value === index && editingValue.value !== '') {
    source.value[index].value = editingValue.value
  }
  editingIndex.value = null
  editingValue.value = ''
}

const cancelEdit = () => {
  editingIndex.value = null
  editingValue.value = ''
}
</script>

<style lang="scss" scoped>
$emphasize-color: #74f7fd;
.container {
  box-sizing: border-box;
  display: grid;
  grid-template-rows: 1fr 1fr 1fr;
  grid-template-columns: 1fr 1fr 1fr;
  grid-gap: 10px;
  height: 100%;
  padding: 10px;

  $icon-size: 34px;
  .item {
    position: relative;
    box-sizing: border-box;
    display: grid;
    grid-template-rows: 1fr 1fr;
    grid-template-columns: $icon-size 1fr;
    grid-gap: 4px 10px;
    align-items: center;
    width: 100%;
    height: 100%;
    padding: 10px 12px;
    overflow: hidden;
    background-color: rgba(93, 101, 122, 20%);
    &.error {
      .icon {
        color: $emphasize-color;
        border: 1px solid $emphasize-color;
        border-radius: 50%;
      }
      .alert {
        // display: block;
        color: #74fab022;
      }
      .label,
      .key {
        color: $emphasize-color;
      }
    }
    .icon {
      display: flex;
      grid-row: 1 / 3;
      grid-column: 1;
      align-items: center;
      justify-content: center;
      width: $icon-size;
      height: $icon-size;
      border: 1px solid #fff;
      border-radius: 50%;
    }
    .label {
      grid-row: 1;
      grid-column: 2;
      align-self: end;
      font-size: 13px;
      color: #999;
      text-align: right;
    }
    .key {
      position: relative;
      grid-row: 2;
      grid-column: 2;
      align-self: start;
      font-size: 14px;
      color: #fff;
      text-align: right;
      cursor: pointer;
      transition: all 0.3s ease;
      &:hover {
        .value {
          color: #74f7fd;
          text-decoration: underline;
        }
      }
      .value {
        margin-right: 6px;
        font-size: 18px;
        font-weight: bold;
        transition: color 0.3s ease;
      }
      .value-input {
        width: 80px;
        padding: 2px 6px;
        margin-right: 6px;
        font-size: 18px;
        font-weight: bold;
        color: #fff;
        text-align: right;
        background: rgba(116, 247, 253, 20%);
        border: 1px solid #74f7fd;
        border-radius: 4px;
        outline: none;
        &:focus {
          background: rgba(116, 247, 253, 30%);
          border-color: #74f7fd;
          box-shadow: 0 0 8px rgba(116, 247, 253, 50%);
        }
      }
      .unit {
        font-size: 13px;
      }
    }
    &.editing {
      .key {
        .value-input {
          animation: input-pulse 1.5s ease-in-out infinite;
        }
      }
    }
    .edit-icon {
      position: absolute;
      top: 8px;
      right: 8px;
      z-index: 10;
      padding: 4px;
      font-size: 14px;
      color: #74f7fd;
      cursor: pointer;
      background: rgba(116, 247, 253, 10%);
      border-radius: 4px;
      transition: all 0.3s ease;
      &:hover {
        background: rgba(116, 247, 253, 30%);
        transform: scale(1.1);
      }
    }
    .alert {
      position: absolute;
      top: 10px;
      right: 10px;
      font-size: 70px;
      color: #ffffff09;
    }
  }
}

@keyframes input-pulse {
  0%, 100% {
    border-color: #74f7fd;
    box-shadow: 0 0 8px rgba(116, 247, 253, 50%);
  }
  50% {
    border-color: #74fab0;
    box-shadow: 0 0 12px rgba(116, 250, 176, 70%);
  }
}
</style>
