<template>
  <div class="settings-card">
    <h3 class="card-title">
      <svg class="title-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
      发布设置
    </h3>
    <div class="setting-row">
      <div class="setting-info">
        <span class="setting-label">上传视频后自动填充标题</span>
        <span class="setting-desc">上传视频成功后，自动将文件名填入所有渠道的标题字段</span>
      </div>
      <div class="setting-control">
        <el-switch v-model="autoFillTitle" />
      </div>
    </div>
    <div class="setting-row">
      <div class="setting-info">
        <span class="setting-label">自动保存草稿</span>
        <span class="setting-desc">发布界面内容（视频、封面、标题、描述等）发生变更时，自动定时将当前内容保存为草稿，避免意外丢失</span>
      </div>
      <div class="setting-control">
        <el-switch v-model="autoSaveDraft" />
      </div>
    </div>
    <div class="setting-row" v-if="autoSaveDraft">
      <div class="setting-info">
        <span class="setting-label">自动保存间隔（秒）</span>
        <span class="setting-desc">检测到内容变更后，等待指定时间再执行保存。间隔过短可能频繁触发请求，建议设置为 10-30 秒</span>
      </div>
      <div class="setting-control">
        <el-input-number v-model="autoSaveInterval" :min="10" :max="300" controls-position="right" style="width: 120px" />
      </div>
    </div>
    <div class="setting-row">
      <div class="setting-info">
        <span class="setting-label">账号登录状态检查机制</span>
        <span class="setting-desc">选择账号 Cookie 有效性的检测时机。两个机制互斥，只能生效一个</span>
      </div>
      <div class="setting-control">
        <el-select v-model="accountCheckMode" style="width: 220px">
          <el-option label="发布前检测（默认）" value="pre-publish" />
          <el-option label="项目启动时后台检测" value="startup" />
        </el-select>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  autoFillTitle: boolean
  autoSaveDraft: boolean
  autoSaveInterval: number
  accountCheckMode: string
}>()

const emit = defineEmits<{
  (e: 'update:autoFillTitle', v: boolean): void
  (e: 'update:autoSaveDraft', v: boolean): void
  (e: 'update:autoSaveInterval', v: number): void
  (e: 'update:accountCheckMode', v: string): void
}>()

const autoFillTitle = computed({
  get: () => props.autoFillTitle,
  set: (v: boolean) => emit('update:autoFillTitle', v),
})
const autoSaveDraft = computed({
  get: () => props.autoSaveDraft,
  set: (v: boolean) => emit('update:autoSaveDraft', v),
})
const autoSaveInterval = computed({
  get: () => props.autoSaveInterval,
  set: (v: number) => emit('update:autoSaveInterval', v),
})
const accountCheckMode = computed({
  get: () => props.accountCheckMode,
  set: (v: string) => emit('update:accountCheckMode', v),
})
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.settings-card {
  background: $bg-elevated;
  border: 1px solid $border;
  border-radius: $radius-card;
  padding: $spacing-lg;
  margin-bottom: $spacing-md;

  .card-title {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 16px;
    font-weight: 600;
    color: $text-primary;
    margin: 0 0 $spacing-lg 0;
    padding-bottom: $spacing-sm;
    border-bottom: 1px solid $border;

    .title-icon {
      width: 20px;
      height: 20px;
      color: $text-secondary;
    }
  }

  .setting-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 0;

    &:not(:last-child) {
      border-bottom: 1px solid $border-light;
    }

    .setting-info {
      display: flex;
      flex-direction: column;
      gap: 4px;
      flex: 1;

      .setting-label {
        font-size: 14px;
        color: $text-primary;
        font-weight: 500;
      }

      .setting-desc {
        font-size: 12px;
        color: $text-muted;
        line-height: 1.5;
      }
    }

    .setting-control {
      flex-shrink: 0;
      margin-left: $spacing-lg;
      display: flex;
      align-items: center;
      gap: 12px;
    }
  }
}
</style>
