/**
 * 平台配置契约测试：supportsImage 能力面必须与后端 impl 层 supports_image 一致。
 *
 * 后端 A4 门控真源：alipay/douyin/kuaishou/weibo/weixin_gzh/xiaohongshu 6 平台
 * supports_image=True（其余平台抛 NotImplementedError）。前端图集入口由本配置
 * 单源驱动（ImagePublish.vue 用 platformList.filter(p => p.supportsImage)），
 * 此测试防止白名单与后端漂移。
 */
import { describe, expect, it } from 'vitest'
import { platformList } from './platforms'

const EXPECTED_IMAGE_KEYS = new Set(['xiaohongshu', 'douyin', 'kuaishou', 'weibo', 'alipay', 'weixin_gzh'])

describe('platforms 能力面', () => {
  it('supportsImage 平台集合与后端 supports_image 一致（6 平台）', () => {
    const imageKeys = platformList.filter(p => p.supportsImage).map(p => p.key)
    expect(new Set(imageKeys)).toEqual(EXPECTED_IMAGE_KEYS)
  })

  it('全部平台都声明了 supportsImage 字段（无遗漏）', () => {
    for (const p of platformList) {
      expect(typeof p.supportsImage, `平台 ${p.key} 缺少 supportsImage`).toBe('boolean')
    }
  })
})
