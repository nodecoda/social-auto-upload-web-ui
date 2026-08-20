<template>
  <div class="channel-grid">
    <div
      v-for="p in platforms"
      :key="p.key"
      :class="['channel-card', {
        'is-checked': checkedKeys.has(p.key),
        'is-disabled': p.count === 0
      }]"
      role="checkbox"
      :aria-checked="checkedKeys.has(p.key)"
      :aria-disabled="p.count === 0"
      :tabindex="p.count === 0 ? -1 : 0"
      @click="emit('toggle', p)"
      @keydown.enter.prevent="emit('toggle', p)"
      @keydown.space.prevent="emit('toggle', p)"
    >
      <img v-if="p.logo" :src="p.logo" :alt="p.name" class="channel-logo" />
      <div v-else class="channel-logo channel-logo-fallback">{{ p.name?.charAt(0) }}</div>
      <div class="channel-name">{{ p.name }}</div>
      <div class="channel-count">{{ p.count }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
export interface BatchChannelOption {
  key: string
  name: string
  logo?: string
  count: number
}

const props = defineProps<{
  platforms: BatchChannelOption[]
  checkedKeys: Set<string>
}>()

const emit = defineEmits<{
  (e: 'toggle', p: BatchChannelOption): void
}>()
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.channel-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 6px;
  width: 100%;
}

.channel-card {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border: 1px solid $border;
  border-radius: 8px;
  background: $bg-elevated;
  cursor: pointer;
  transition: all 0.15s ease;
  user-select: none;
  min-height: 36px;

  &:hover:not(.is-disabled) {
    border-color: $brand-start;
    background: rgba($brand-start, 0.04);
  }

  &.is-checked {
    border-color: $brand-start;
    background: rgba($brand-start, 0.1);
    box-shadow: 0 0 0 1px $brand-start inset;
  }

  &.is-disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .channel-logo {
    width: 20px;
    height: 20px;
    border-radius: 4px;
    object-fit: contain;
    flex-shrink: 0;
  }
  .channel-logo-fallback {
    display: flex;
    align-items: center;
    justify-content: center;
    background: $bg-surface;
    color: $text-muted;
    font-size: 11px;
    font-weight: 700;
    flex-shrink: 0;
  }

  .channel-name {
    flex: 1;
    font-size: 12px;
    font-weight: 500;
    color: $text-primary;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .channel-count {
    flex-shrink: 0;
    width: 22px;
    height: 22px;
    border-radius: 50%;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: $bg-surface;
    color: $text-muted;
    font-size: 11px;
    font-weight: 500;
  }
}
</style>
