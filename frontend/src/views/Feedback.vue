<template>
  <div class="feedback-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">一键反馈</h1>
        <p class="page-subtitle">查看、提交、投票反馈，与作者一起改进产品</p>
      </div>
      <el-button type="primary" :icon="Plus" @click="submitVisible = true">提交反馈</el-button>
    </div>

    <div class="filter-bar">
      <span class="filter-label">状态</span>
      <el-select v-model="statusFilter" placeholder="选择状态" class="status-select" @change="handleStatusChange">
        <el-option label="全部" value="all" />
        <el-option label="待确认" :value="1" />
        <el-option label="处理中" :value="2" />
        <el-option label="已完成" :value="3" />
        <el-option label="已拒绝" :value="4" />
      </el-select>
      <el-button :icon="Refresh" @click="loadList" :loading="loading">刷新</el-button>
    </div>

    <div v-loading="loading" class="card-grid">
      <el-empty v-if="!loading && sortedList.length === 0" description="暂无反馈" />
      <FeedbackCard
        v-for="fb in sortedList"
        :key="fb.id"
        :fb="fb"
        :voted="votedIds.has(fb.id)"
        @vote="handleVote"
        @open="openDrawer"
      />
    </div>

    <div v-if="total > 0" class="pagination-wrapper">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :page-sizes="[10, 20, 50]"
        :total="total"
        layout="total, sizes, prev, pager, next, jumper"
        @current-change="loadList"
        @size-change="onSizeChange"
      />
    </div>

    <!-- 详情抽屉 -->
    <el-drawer
      v-model="drawerVisible"
      :title="`反馈 #${currentFb?.id || ''}`"
      size="500px"
      direction="rtl"
    >
      <div v-if="currentFb" class="drawer-content">
        <el-tag :type="statusTagType(currentFb.status)" size="small">
          {{ statusLabel(currentFb.status) }}
        </el-tag>
        <div v-if="currentFb.assignee" class="drawer-assignee">
          处理人：{{ currentFb.assignee }}
        </div>
        <div class="drawer-time">{{ formatTime(currentFb.created_at) }}</div>
        <div class="drawer-content-text">{{ currentFb.content }}</div>
        <div v-if="currentFb.attachments && currentFb.attachments.length" class="drawer-attachments">
          <h4>附件</h4>
          <el-image
            v-for="att in currentFb.attachments"
            :key="att.id"
            :src="att.file_url"
            :preview-src-list="currentFb.attachments.map(a => a.file_url)"
            :initial-index="0"
            fit="cover"
            class="attachment-img"
          />
        </div>
        <div class="drawer-vote">
          <button
            :class="['vote-btn', { voted: votedIds.has(currentFb.id) }]"
            :disabled="votedIds.has(currentFb.id)"
            @click="handleVote(currentFb)"
          >
            <el-icon><CaretTop /></el-icon>
            <span>{{ votedIds.has(currentFb.id) ? '已支持' : '我也支持' }}</span>
            <span class="vote-num">{{ currentFb.vote_count || 0 }}</span>
          </button>
        </div>
      </div>
    </el-drawer>

    <!-- 提交反馈对话框 -->
    <FeedbackSubmitDialog
      v-model="submitVisible"
      @submit-success="loadList"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { listFeedback, voteFeedback as apiVote } from '@/api/feedback'
import { type ApiResponse } from '@/utils/request'
import { getErrorMessage } from '@/utils/error'
import FeedbackCard from '@/components/FeedbackCard.vue'
import FeedbackSubmitDialog from '@/components/FeedbackSubmitDialog.vue'
import {
  type FeedbackItem,
  statusLabel,
  statusTagType,
  formatTime,
} from '@/components/feedbackShared'

const router = useRouter()

const statusFilter = ref('all')
const loading = ref(false)
const list = ref<FeedbackItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)

const drawerVisible = ref(false)
const currentFb = ref<FeedbackItem | null>(null)

const submitVisible = ref(false)

const VOTED_LS_KEY = 'feedback_voted_ids'
const votedIds = ref<Set<number>>(new Set(JSON.parse(localStorage.getItem(VOTED_LS_KEY) || '[]')))

function persistVotedIds() {
  localStorage.setItem(VOTED_LS_KEY, JSON.stringify([...votedIds.value]))
}

const sortedList = computed(() => {
  return [...list.value].sort((a, b) => {
    if ((b.vote_count || 0) !== (a.vote_count || 0)) {
      return (b.vote_count || 0) - (a.vote_count || 0)
    }
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  })
})

async function loadList() {
  loading.value = true
  try {
    const params: { page: number; pageSize: number; includeAll?: boolean; status?: string } = {
      page: page.value,
      pageSize: pageSize.value
    }
    if (statusFilter.value === 'all') {
      params.includeAll = true
    } else {
      params.status = statusFilter.value
    }
    const res = (await listFeedback(params)) as ApiResponse<{ list?: FeedbackItem[]; total?: number }>
    list.value = res.data?.list || []
    total.value = res.data?.total || 0
  } catch (e) {
    list.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function handleStatusChange() {
  page.value = 1
  loadList()
}
function onSizeChange(s: number) {
  pageSize.value = s
  page.value = 1
  loadList()
}

function openDrawer(fb: FeedbackItem) {
  currentFb.value = fb
  drawerVisible.value = true
}

async function handleVote(fb: FeedbackItem) {
  // 后端从 settings 表读 email；前端不再传。前端只用来判断是否需要引导去设置。
  const localEmail = localStorage.getItem('global_user_email') || ''
  if (!localEmail) {
    await promptForEmail()
    return
  }
  if (votedIds.value.has(fb.id)) return
  try {
    await apiVote({ id: fb.id })
    votedIds.value.add(fb.id)
    persistVotedIds()
    fb.vote_count = (fb.vote_count || 0) + 1
    ElMessage.success('+1 成功')
  } catch (e) {
    // 400 您已经为该反馈 +1 过了
    if (getErrorMessage(e).includes('+1 过了')) {
      votedIds.value.add(fb.id)
      persistVotedIds()
      ElMessage.warning('您已为此反馈投过票')
    }
    // 其他错误已被 request.js 拦截器处理
  }
}

async function promptForEmail() {
  try {
    await ElMessageBox.confirm(
      '请前往设置页填写反馈邮箱',
      '需要邮箱',
      { confirmButtonText: '去设置', cancelButtonText: '取消', type: 'warning' }
    )
    router.push('/settings')
  } catch (_) {
    // 用户取消，不操作
  }
}

onMounted(async () => {
  const email = localStorage.getItem('global_user_email')
  if (!email) {
    await promptForEmail()
  }
  await loadList()
})
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.feedback-page {
  padding: 24px;
  width: 100%;
  max-width: none;
  margin: 0;
  box-sizing: border-box;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 24px;
}

.page-title {
  font-size: 24px;
  font-weight: 700;
  color: $text-primary;
  margin-bottom: 4px;
}

.page-subtitle {
  font-size: 13px;
  color: $text-muted;
}

.filter-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;

  .filter-label {
    color: $text-secondary;
    font-size: 14px;
  }

  .status-select {
    width: 160px;
  }
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 20px;
  min-height: 200px;
}




.vote-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 6px;
  border: 1px solid $border;
  background: rgba($overlay-rgb, 0.04);
  color: $text-primary;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  font-family: inherit;

  &:hover:not(:disabled) {
    border-color: $brand-start;
    color: $brand-start;
    background: rgba($brand-start, 0.1);
    transform: translateY(-1px);
  }

  &:disabled,
  &.voted {
    border-color: $brand-start;
    background: linear-gradient(135deg, $brand-start, $brand-end);
    color: #fff;
    cursor: default;
  }

  .vote-num {
    padding: 0 6px;
    background: rgba(0, 0, 0, 0.15);
    border-radius: 10px;
    font-size: 11px;
    font-weight: 600;
    min-width: 18px;
    text-align: center;
  }

  &:not(.voted) .vote-num {
    background: rgba($overlay-rgb, 0.08);
  }
}







.pagination-wrapper {
  display: flex;
  justify-content: center;
  padding: 24px 0;
}

.drawer-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.drawer-assignee {
  font-size: 13px;
  color: $text-secondary;
}

.drawer-time {
  font-size: 12px;
  color: $text-muted;
}

.drawer-content-text {
  padding: 12px;
  background: $bg-surface;
  border-radius: 8px;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 14px;
  line-height: 1.6;
}

.drawer-attachments {
  h4 {
    font-size: 14px;
    margin-bottom: 8px;
    color: $text-primary;
  }
  .attachment-img {
    width: 100px;
    height: 100px;
    border-radius: 6px;
    margin-right: 8px;
    margin-bottom: 8px;
  }
}

.drawer-vote {
  padding-top: 12px;
  border-top: 1px solid $border;

  .vote-btn {
    padding: 8px 16px;
    font-size: 13px;
  }
}
</style>
