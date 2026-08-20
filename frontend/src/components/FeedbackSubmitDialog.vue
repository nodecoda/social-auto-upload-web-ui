<template>
  <el-dialog
    :model-value="modelValue"
    title="提交反馈"
    width="500px"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-form :model="submitForm" label-width="80px">
      <el-form-item label="邮箱" required>
        <el-input v-model="submitForm.email" placeholder="your@email.com" />
      </el-form-item>
      <el-form-item label="内容" required>
        <el-input v-model="submitForm.content" type="textarea" :rows="5" placeholder="详细描述您遇到的问题或建议" />
      </el-form-item>
      <el-form-item label="附件">
        <el-upload
          :auto-upload="false"
          :limit="1"
          :on-change="onFileChange"
          :on-exceed="onExceed"
          :on-remove="onFileRemove"
          accept=".png,.jpg,.jpeg,.gif,.bmp,.webp,.pdf,.doc,.docx,.xlsx,.xls,.pptx,.ppt"
          list-type="picture"
        >
          <el-button :icon="Upload">选择文件 (≤5MB)</el-button>
          <template #tip>
            <div class="el-upload__tip">支持图片、PDF、Office 文档，单文件不超过 5MB</div>
          </template>
        </el-upload>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit">提交</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage, type UploadFile } from 'element-plus'
import { Upload } from '@element-plus/icons-vue'
import { submitFeedback as apiSubmit } from '@/api/feedback'
import { http } from '@/utils/request'

const props = defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'submit-success'): void
}>()

const submitting = ref(false)
const submitForm = ref({ email: '', content: '' })
const submitFile = ref<File | null>(null)

// 每次打开时预填全局邮箱并重置表单
watch(() => props.modelValue, (open) => {
  if (open) {
    submitForm.value = {
      email: localStorage.getItem('global_user_email') || '',
      content: '',
    }
    submitFile.value = null
  }
})

function onFileChange(file: UploadFile) {
  if ((file.size ?? 0) > 5 * 1024 * 1024) {
    ElMessage.error('文件超过 5MB')
    submitFile.value = null
    return false
  }
  submitFile.value = file.raw as File
}
function onExceed() {
  ElMessage.warning('只能上传 1 个文件')
}
function onFileRemove() {
  submitFile.value = null
}

async function handleSubmit() {
  const email = submitForm.value.email.trim()
  const content = submitForm.value.content.trim()
  if (!email || !content) {
    ElMessage.error('邮箱和内容必填')
    return
  }
  // 用户在对话框里可能改了 email，把它同步回 settings + localStorage
  const globalEmail = localStorage.getItem('global_user_email') || ''
  if (email !== globalEmail) {
    localStorage.setItem('global_user_email', email)
    // 同步回后端 settings（让下次 list/vote 也能用上）
    try {
      await http.put('/api/v2/settings', { feedbackEmail: email })
    } catch (_) { /* 后端同步失败不影响本次提交 */ }
  }

  submitting.value = true
  try {
    const fd = new FormData()
    // 后端优先用 settings 里的 email，这里也传作为覆盖（保持兼容性）
    fd.append('email', email)
    fd.append('content', content)
    if (submitFile.value) {
      fd.append('files', submitFile.value)
    }
    await apiSubmit(fd)
    ElMessage.success('提交成功')
    emit('update:modelValue', false)
    emit('submit-success')
  } catch (e) {
    // 错误已由 request.js 拦截器处理
  } finally {
    submitting.value = false
  }
}
</script>
