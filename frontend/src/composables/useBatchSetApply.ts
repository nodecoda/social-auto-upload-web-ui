import { getPlatformByKey } from '@/config/platforms'

/** 批量设置载荷（full 全量 / partial 仅已填字段） */
export interface BatchSetPayload {
  title?: string
  description?: string
  tags?: string[]
  scheduleTime?: string
  mode?: 'full' | 'partial'
}

/** 渠道/账号级配置字典（批量设写入目标，值类型动态） */
export type BatchSetConfig = Record<string, unknown>

/** 批量设所需的最小依赖面（结构类型，真实 store/状态兼容） */
export interface BatchSetRefs {
  platformConfigs: Record<string, Record<string, unknown>>
  accountOverrides: Record<string | number, Record<string, unknown>>
  accountChecked: Record<string | number, boolean>
  accountStore: { accounts: Array<{ id: number | string; platform: string }> }
}

/**
 * 视频发布批量设 composable。
 * 把 payload (title/description/tags/scheduleTime) 写入 checkedPlatformKeys 中每个渠道的:
 *   1) platformConfigs[platformKey] (渠道级, 覆盖)
 *   2) 该渠道下已开 accountChecked 的账号 → accountOverrides[id] (账号级, 覆盖)
 *
 * 注：视频侧 enableTimer 在发布时由 scheduleTime 派生（PublishCenter.vue 构造 publishData 时
 *   enableTimer = scheduleTime ? 1 : 0），故此处只写 scheduleTime。
 *
 * @param {object} refs  { platformConfigs, accountOverrides, accountChecked, accountStore }
 * @returns {{ applyBatchSet: (checkedPlatformKeys: string[], payload: { title: string, description: string, tags: string[], scheduleTime: string }) => void }}
 */
export function useBatchSetApply({ platformConfigs, accountOverrides, accountChecked, accountStore }: BatchSetRefs): { applyBatchSet: (checkedPlatformKeys: string[], payload: BatchSetPayload) => void } {
  function applyBatchSet(checkedPlatformKeys: string[], payload: BatchSetPayload): void {
    const { title, description, tags, scheduleTime } = payload
    const mode = payload.mode ?? 'full'
    const tagsCopy = Array.isArray(tags) ? [...tags] : []
    const scheduleTimeValue = scheduleTime || ''

    // partial 模式：仅覆盖已填写（非空）字段，空值字段跳过保持原值
    const isPartial = mode === 'partial'
    const hasTitle = title !== undefined && title !== ''
    const hasDescription = description !== undefined && description !== ''
    const hasTags = tagsCopy.length > 0
    const hasScheduleTime = scheduleTimeValue !== ''

    for (const pk of checkedPlatformKeys) {
      // 1. 渠道级（覆盖）
      if (!platformConfigs[pk]) platformConfigs[pk] = {}
      if (!isPartial || hasTitle) platformConfigs[pk].title = title
      if (!isPartial || hasDescription) platformConfigs[pk].description = description
      if (!isPartial || hasTags) platformConfigs[pk].tags = tagsCopy
      if (!isPartial || hasScheduleTime) platformConfigs[pk].scheduleTime = scheduleTimeValue

      // 2. 该渠道下所有账号（覆盖）—— 不再用 accountChecked 筛选：
      //    五角星(账号级表单个性化)走的是 accountOverrides，与媒体开关 accountChecked 无关，
      //    故批量设置应替换该渠道下所有账号，无论是否已个性化。
      const platformCfg = getPlatformByKey(pk)
      if (!platformCfg) continue
      const accounts = (accountStore?.accounts || []).filter((a) => a.platform === platformCfg.name)
      for (const acc of accounts) {
        if (!accountOverrides[acc.id]) accountOverrides[acc.id] = {}
        if (!isPartial || hasTitle) accountOverrides[acc.id].title = title
        if (!isPartial || hasDescription) accountOverrides[acc.id].description = description
        if (!isPartial || hasTags) accountOverrides[acc.id].tags = tagsCopy
        if (!isPartial || hasScheduleTime) accountOverrides[acc.id].scheduleTime = scheduleTimeValue
      }
    }
  }

  return { applyBatchSet }
}
