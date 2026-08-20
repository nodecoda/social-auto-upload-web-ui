<template>
  <div class="action-card" @click="emit('navigate', route)">
    <div class="action-icon" :class="`action-icon-${variant}`">
      <slot name="icon" />
    </div>
    <div class="action-title">{{ title }}</div>
    <div class="action-desc">{{ desc }}</div>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  variant: 'purple' | 'blue' | 'cyan' | 'green'
  title: string
  desc: string
  route: string
}>(), {
  variant: 'purple',
})

const emit = defineEmits<{
  (e: 'navigate', route: string): void
}>()
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.action-card {
  background: $bg-elevated;
  border: 1px solid $border;
  border-radius: $radius-card;
  padding: 24px;
  cursor: pointer;
  transition: $transition-base;
  display: flex;
  flex-direction: column;
  align-items: flex-start;

  &:hover {
    transform: translateY(-4px);
    border-color: $border-active;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2), 0 0 0 1px rgba($brand-start, 0.15);
  }

  .action-icon {
    width: 48px;
    height: 48px;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 14px;

    :deep(.el-icon) {
      font-size: 22px;
      color: #fff;
    }

    &.action-icon-purple {
      background: linear-gradient(135deg, $brand-start, $brand-end);
    }

    &.action-icon-blue {
      background: linear-gradient(135deg, $brand-end, $accent-cyan);
    }

    &.action-icon-cyan {
      background: linear-gradient(135deg, $accent-cyan, $accent-green);
    }

    &.action-icon-green {
      background: linear-gradient(135deg, $accent-green, $accent-amber);
    }
  }

  .action-title {
    font-size: 15px;
    font-weight: 600;
    color: $text-primary;
    margin-bottom: 4px;
  }

  .action-desc {
    font-size: 12px;
    color: $text-muted;
  }
}
</style>
