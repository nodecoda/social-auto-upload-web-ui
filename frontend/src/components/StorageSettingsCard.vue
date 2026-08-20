<template>
  <div class="settings-card">
    <h3 class="card-title">
      <svg class="title-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
      文件存储
    </h3>
    <div class="setting-row">
      <div class="setting-info">
        <span class="setting-label">存储类型</span>
        <span class="setting-desc">选择素材文件的存储方式，S3 兼容存储支持 MinIO、阿里云 OSS、AWS S3 等</span>
      </div>
      <div class="setting-control">
        <el-radio-group v-model="storage.type">
          <el-radio value="local">本地存储</el-radio>
          <el-radio value="s3">S3 兼容存储</el-radio>
        </el-radio-group>
      </div>
    </div>
    <template v-if="storage.type === 's3'">
      <div class="setting-row">
        <div class="setting-info">
          <span class="setting-label">Endpoint</span>
        </div>
        <div class="setting-control">
          <el-input v-model="storage.s3.endpoint" placeholder="http://127.0.0.1:9000" style="width: 300px" />
        </div>
      </div>
      <div class="setting-row">
        <div class="setting-info">
          <span class="setting-label">Access Key</span>
        </div>
        <div class="setting-control">
          <el-input v-model="storage.s3.access_key" style="width: 300px" />
        </div>
      </div>
      <div class="setting-row">
        <div class="setting-info">
          <span class="setting-label">Secret Key</span>
        </div>
        <div class="setting-control">
          <el-input v-model="storage.s3.secret_key" type="password" show-password style="width: 300px" />
        </div>
      </div>
      <div class="setting-row">
        <div class="setting-info">
          <span class="setting-label">Bucket</span>
        </div>
        <div class="setting-control">
          <el-input v-model="storage.s3.bucket" style="width: 300px" />
        </div>
      </div>
      <div class="setting-row">
        <div class="setting-info">
          <span class="setting-label">Region</span>
        </div>
        <div class="setting-control">
          <el-input v-model="storage.s3.region" placeholder="可选" style="width: 300px" />
        </div>
      </div>
      <div class="setting-row">
        <div class="setting-info">
          <span class="setting-label">连接测试</span>
          <span class="setting-desc">验证 S3 配置是否正确，确认可以正常连接</span>
        </div>
        <div class="setting-control">
          <button class="cache-btn" style="border-color: rgba(var(--el-color-primary-rgb), 0.3); background: rgba(var(--el-color-primary-rgb), 0.06); color: var(--el-color-primary);" :disabled="s3Testing" @click="testS3Connection">
            {{ s3Testing ? '测试中...' : '测试连接' }}
          </button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { http, type ApiResponse } from '@/utils/request'
import { getErrorMessage } from '@/utils/error'

export interface S3Config {
  endpoint: string
  access_key: string
  secret_key: string
  bucket: string
  region: string
}

export interface StorageConfig {
  type: 'local' | 's3'
  s3: S3Config
}

const props = defineProps<{
  storage: StorageConfig
}>()

const s3Testing = ref(false)

async function testS3Connection() {
  s3Testing.value = true
  try {
    const resp = (await http.post('/api/materials/test-s3', props.storage.s3)) as ApiResponse
    if (resp.code === 200) {
      ElMessage.success('S3 连接成功')
    } else {
      ElMessage.error(resp.msg || '连接失败')
    }
  } catch (e: unknown) {
    const msg = getErrorMessage(e)
    ElMessage.error('连接失败: ' + msg)
  }
  s3Testing.value = false
}
</script>

<style scoped lang="scss">
@use '@/styles/variables' as *;

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

    .cache-btn {
      padding: 8px 20px;
      border: 1px solid rgba($danger-color, 0.3);
      border-radius: $radius-base;
      background: rgba($danger-color, 0.06);
      color: $danger-color;
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
      transition: $transition-base;
      font-family: inherit;
      outline: none;

      &:hover:not(:disabled) {
        background: rgba($danger-color, 0.12);
        border-color: rgba($danger-color, 0.5);
      }

      &:disabled {
        opacity: 0.5;
        cursor: not-allowed;
      }
    }
  }
}
</style>
