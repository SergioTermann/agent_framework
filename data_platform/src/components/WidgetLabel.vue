<template>
  <div class="equipment-label" @click="onClick">
    <span class="label-number">{{ number }}</span>
    <span class="label-name">{{ name }}</span>
  </div>
</template>
<script setup lang="ts">
interface PropsType {
  name: string
  number?: number // 设备编号（可选）
}
const props = defineProps<PropsType>()

const onClick = () => {}
</script>
<style lang="scss" scoped>
.equipment-label {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: center;
  padding: 5px 30px;
  font-weight: bolder;
  color: #fff;
  pointer-events: all;
  cursor: pointer;
  background-color: #0005;
  background-repeat: no-repeat;
  background-size: 100% 100%;
  border-radius: 100px;
  .label-number {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    font-size: 14px;
    font-weight: bold;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 50%;
    box-shadow: 0 2px 8px rgba(102, 126, 234, 40%);
  }
  .label-name {
    font-size: 14px;
  }
}
</style>
