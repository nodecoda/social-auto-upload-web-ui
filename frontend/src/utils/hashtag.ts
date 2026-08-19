import { watch, nextTick } from 'vue'

/**
 * 描述/标题中的 #xxx 话题抽取工具
 *
 * 语义与 PublishCenter.vue 旧的 DESC_HASHTAG_RE 和后端
 * backend/impl/douyin/platform.py 的 _HASHTAG_PATTERN 一致:
 * 行首或空白后的 # 才算话题开头,不匹配 "a#b" / "http://x#anchor" / "##" / 孤立 "#"
 */

// eslint-disable-next-line no-useless-backreference
export const HASHTAG_RE = /(?:^|\s)#([^\s#]+)/g

export interface HashtagResult {
  cleanedText: string
  hashtags: string[]
}

/**
 * 从一段文本中提取所有 #xxx 话题。
 * - cleanedText: 去除所有匹配项后的文本(末尾的尾部空白会被压紧)
 * - hashtags: 数组,裸字符串(去掉 # 和首尾空白),已按首次出现顺序去重
 *
 * 示例:
 *   "今天天气真好 #旅行 #旅行 #美食" => { cleanedText: "今天天气真好", hashtags: ["旅行", "美食"] }
 *   "#a #b #c" => { cleanedText: "", hashtags: ["a", "b", "c"] }
 */
export function extractHashtags(text?: string | null): HashtagResult {
  if (!text) return { cleanedText: text || '', hashtags: [] }
  const seen = new Set<string>()
  const hashtags: string[] = []
  // 收集裸字符串(去 # 和首尾空白)
  for (const m of text.matchAll(HASHTAG_RE)) {
    const tag = (m[1] || '').trim()
    if (!tag) continue
    if (seen.has(tag)) continue
    seen.add(tag)
    hashtags.push(tag)
  }
  if (hashtags.length === 0) return { cleanedText: text, hashtags }
  // 移除所有匹配项(包括 matchAll 过程中吞掉的前导空白),再压紧尾部空白
  const cleanedText = text.replace(HASHTAG_RE, '').replace(/\s+$/, '')
  return { cleanedText, hashtags }
}

/**
 * 计算文本中独立 #xxx 话题的数量(用于平台上限校验:douyin≤5、xhs≤10 等)
 * 与后端 _count_hashtags 同语义
 */
export function countDescriptionHashtags(text?: string | null): number {
  if (!text) return 0
  return (text.match(HASHTAG_RE) || []).length
}

export interface UseAutoExtractHashtagsOptions<T extends Record<string, any>> {
  form: T
  descKey?: string
  tagKey?: string
  maxTags?: number
  getReservedTagCount?: (form: T) => number
}

/**
 * Vue 组合式函数:监听表单描述字段变化,实时把 #xxx 抽取到 tags 数组,
 * 并从描述文本中清除 #xxx 字样。
 *
 * - 实时触发(基于 watch,flush: 'post')
 * - 内部用标志位 guard 防止 watch 嵌套赋值导致死循环
 * - 已有标签自动去重(基于 form.tags.includes)
 * - 可指定平台上限(maxTags),超出截断;抖音等平台同时考虑活动数
 * - 加载已有草稿时不主动处理(避免破坏现有数据),仅在 description 后续被修改时触发
 */
export function useAutoExtractHashtags<T extends Record<string, unknown>>(options: UseAutoExtractHashtagsOptions<T>): void {
  const {
    descKey = 'description',
    tagKey = 'tags',
    maxTags,
    getReservedTagCount = () => 0,
  } = options || {}
  // 局部转为宽松 Record 以允许写索引 (泛型 T 在 TS 4.9+ 禁止写索引)
  const form: Record<string, any> = (options?.form || {}) as Record<string, any>

  if (!form) return

  let writing = false

  watch(
    () => form[descKey] as string | undefined,
    (newVal) => {
      if (writing) return
      const { cleanedText, hashtags } = extractHashtags(newVal || '')
      if (hashtags.length === 0) {
        // 无 hashtag,不需要写回。原文与清理后一致时也跳过,避免抖动。
        if (cleanedText === newVal) return
      }
      // 计算本次最多能加多少(平台上限减去已存在的标签数和 reserved)
      const existing: string[] = Array.isArray(form[tagKey]) ? form[tagKey] : []
      const reserved = Number(getReservedTagCount(form as T)) || 0
      const capacity = typeof maxTags === 'number' ? Math.max(0, maxTags - existing.length - reserved) : Infinity
      const toAdd = capacity === Infinity ? hashtags : hashtags.slice(0, capacity)
      if (toAdd.length === 0) {
        // 即便不加标签,也尝试把描述中的 #xxx 清掉,否则意义不大
        // 但为安全,如果 cleanedText 等于 newVal,直接 return
        if (cleanedText === newVal) return
      }

      writing = true
      try {
        // 写回描述(去除 #xxx 字样)
        form[descKey] = cleanedText
        // 追加标签(去重)
        if (toAdd.length > 0) {
          if (!Array.isArray(form[tagKey])) form[tagKey] = []
          const tags: string[] = form[tagKey]
          for (const tag of toAdd) {
            if (!tags.includes(tag)) tags.push(tag)
          }
        }
      } finally {
        // 等到当前响应式更新 flush 完成再放行,避免内部赋值再次触发本 watcher
        nextTick(() => {
          writing = false
        })
      }
    },
    { flush: 'post' },
  )
}
