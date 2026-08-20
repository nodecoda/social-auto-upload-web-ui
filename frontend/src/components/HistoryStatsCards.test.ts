import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import HistoryStatsCards from './HistoryStatsCards.vue'

const ElIcon = { template: '<i class="el-icon-stub"><slot /></i>' }

const stats = { total: 42, successRate: 87.5, monthlyTotal: 10 }

const mountIt = () =>
  mount(HistoryStatsCards, {
    props: { stats },
    global: { stubs: { ElIcon } },
  })

describe('HistoryStatsCards', () => {
  it('renders three stat cards with values', () => {
    const w = mountIt()
    expect(w.findAll('.stat-card')).toHaveLength(3)
    expect(w.text()).toContain('42')
    expect(w.text()).toContain('总发布数')
    expect(w.text()).toContain('87.5%')
    expect(w.text()).toContain('成功率')
    expect(w.text()).toContain('10')
    expect(w.text()).toContain('本月发布')
  })

  it('applies color variant classes to each card', () => {
    const w = mountIt()
    const classes = w.findAll('.stat-card').map(c => c.classes())
    expect(classes[0]).toContain('stat-purple')
    expect(classes[1]).toContain('stat-blue')
    expect(classes[2]).toContain('stat-cyan')
  })

  it('renders icon for each card', () => {
    const w = mountIt()
    expect(w.findAll('.stat-icon .el-icon-stub')).toHaveLength(3)
  })
})
