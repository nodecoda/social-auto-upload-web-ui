import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import RecentMaterialsTable, { type MaterialItem } from './RecentMaterialsTable.vue'

const ElTable = {
  name: 'ElTable',
  props: ['data'],
  template: '<div class="el-table-stub"><slot /></div>',
}

const ElTableColumn = {
  name: 'ElTableColumn',
  props: ['prop', 'label'],
  template: `
    <div class="el-table-column-stub">
      <span class="el-table-column-label">{{ label }}</span>
      <slot :row="{ original_filename: 'demo.mp4', file_size: 5242880, file_type: 'video', upload_time: '2026-08-01 10:00:00' }" />
    </div>
  `,
}

const mountTable = (props: { materials: MaterialItem[]; loading: boolean }) =>
  mount(RecentMaterialsTable, {
    props,
    global: {
      stubs: { ElTable, ElTableColumn },
      directives: { loading: {} },
    },
  })

describe('RecentMaterialsTable', () => {
  it('renders header, column labels and material cells', () => {
    const wrapper = mountTable({
      materials: [{ id: 1, original_filename: 'demo.mp4', file_type: 'video' }],
      loading: false,
    })
    expect(wrapper.text()).toContain('最近素材')
    expect(wrapper.text()).toContain('查看全部')
    expect(wrapper.text()).toContain('文件名')
    expect(wrapper.text()).toContain('大小')
    expect(wrapper.text()).toContain('类型')
    expect(wrapper.text()).toContain('上传时间')
    expect(wrapper.text()).toContain('demo.mp4')
    expect(wrapper.text()).toContain('5.00 MB')
    expect(wrapper.text()).toContain('视频')
    expect(wrapper.text()).toContain('2026-08-01 10:00:00')
  })

  it('emits view-all when 查看全部 is clicked', async () => {
    const wrapper = mountTable({ materials: [], loading: false })
    await wrapper.find('.view-all-link').trigger('click')
    expect(wrapper.emitted('view-all')).toHaveLength(1)
  })

  it('shows empty state when no materials and not loading', () => {
    const wrapper = mountTable({ materials: [], loading: false })
    expect(wrapper.find('.empty-state').exists()).toBe(true)
    expect(wrapper.text()).toContain('暂无素材数据')
  })

  it('hides empty state while loading', () => {
    const wrapper = mountTable({ materials: [], loading: true })
    expect(wrapper.find('.empty-state').exists()).toBe(false)
  })
})
