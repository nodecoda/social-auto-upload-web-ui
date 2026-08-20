<template>
  <section class="batch-meta">
    <el-collapse v-model="metaOpen">
      <el-collapse-item title="批次元信息" name="meta">
        <div class="meta-grid">
          <div class="meta-item">
            <span class="meta-label">批次 ID</span>
            <span class="meta-value">
              <code>{{ batch?.id }}</code>
              <el-button link size="small" @click="copyBatchId">复制</el-button>
            </span>
          </div>
          <div class="meta-item">
            <span class="meta-label">定时发布时间</span>
            <span class="meta-value">{{ batch?.schedule_time || '未设置' }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">开始时间</span>
            <span class="meta-value">{{ batch?.started_at || '—' }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">结束时间</span>
            <span class="meta-value">{{ batch?.finished_at || '—' }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">账号数</span>
            <span class="meta-value">
              批次记录 {{ batch?.account_count }} ·
              实际展示 {{ accountCount }}
            </span>
          </div>
        </div>
      </el-collapse-item>
    </el-collapse>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ElMessage } from 'element-plus'

interface HistoryBatchMeta {
  id: string
  schedule_time?: string
  started_at?: string
  finished_at?: string
  account_count?: number
}

const props = defineProps<{
  batch: HistoryBatchMeta | null
  accountCount: number
  metaOpen: string[]
}>()

const emit = defineEmits<{
  (e: 'update:metaOpen', v: string[]): void
}>()

// el-collapse 的 v-model 需要可写值：走 emit 回写，避免直接改 prop
const metaOpen = computed({
  get: () => props.metaOpen,
  set: (v: string[]) => emit('update:metaOpen', v),
})

async function copyBatchId() {
  if (!props.batch?.id) return
  try {
    await navigator.clipboard.writeText(props.batch.id)
    ElMessage.success('已复制批次 ID')
  } catch (e) {
    ElMessage.error('复制失败')
  }
}
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

// 4. 批次元信息折叠卡：左右 0/20 padding 配合 el-collapse-item 内部 padding 形成节奏
.batch-meta {
  background: $bg-elevated;
  border: 1px solid $border;
  border-radius: $radius-card;
  padding: 0 4px;  // 让 el-collapse-item 的内边距更接近主体节奏

  .meta-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 12px 24px;
    padding: 4px 16px 16px;
  }

  .meta-item {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 8px 0;
  }

  .meta-label {
    font-size: 12px;
    color: $text-muted;
    letter-spacing: 0.02em;
  }

  .meta-value {
    font-size: 13px;
    color: $text-secondary;
    display: flex;
    align-items: center;
    gap: 8px;
    line-height: 1.5;

    code {
      font-family: 'Fira Code', 'JetBrains Mono', Menlo, monospace;
      font-size: 12px;
      background: rgba($overlay-rgb, 0.05);
      padding: 2px 8px;
      border-radius: 4px;
      color: $text-primary;
    }
  }
}
</style>
