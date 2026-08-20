# 前端编码规范 (Frontend Coding Standards)

> 适用于 `frontend/` 目录。技术栈：Vue 3.5 `<script setup lang="ts">` · TypeScript 5.9 `strict` · Vite 6 · Pinia 3 (setup syntax) · Element Plus 2.9 · Vue Router 4 · Vitest 2 (jsdom)。
> 简明规则见仓库根目录 `.cursorrules`；本文件为完整版（规则 + 理由 + 好坏示例 + 例外）。

## 0. 技术栈基线

| 项 | 值 |
|---|---|
| Vue | 3.5.x，全部 SFC 使用 `<script setup lang="ts">` |
| TypeScript | 5.9.x，`"strict": true`（全量开启） |
| 构建 | Vite 6 + `vue-tsc --noEmit` 类型检查 |
| 状态 | Pinia 3（setup syntax） |
| UI | Element Plus 2.9（含 icons-vue） |
| 路由 | Vue Router 4 |
| 测试 | Vitest 2 + @vue/test-utils 2 + jsdom |
| 目录 | `src/{views,components,composables,stores,api,utils,config,router,styles,assets}` |

**验证命令**（在 `frontend/` 下执行，提交前必须全绿）：
```bash
npx vue-tsc --noEmit
npx vitest run
npx vite build
```

---

## 1. 只用 Composition API

**规则**：所有 SFC 使用 `<script setup lang="ts">`。禁止 Options API（`defineComponent`、`data()/methods`、`this.`）。

**理由**：Composition API 是 Vue 3 的官方推荐写法，类型推导完整、逻辑可复用、与 `<script setup>` 的编译宏（props/emits）天然配合。

**允许的例外**：附加的普通 `<script lang="ts">` 块仅用于暴露非响应式常量给模板（如 `$options.borderColor`）。**优先**改用 `defineOptions` 或顶层 `const`。

**坏**：
```vue
<script lang="ts">
import { defineComponent } from 'vue'
export default defineComponent({
  data: () => ({ count: 0 }),
  methods: { inc() { this.count++ } },
})
</script>
```

**好**：
```vue
<script setup lang="ts">
const count = ref(0)
const inc = () => count.value++
</script>
```

**治理约定**：遇到旧组件（含双 `<script>` 块滥用），在改动它的同一批次内迁移为 `<script setup>`。

---

## 2. `<script setup>` 声明顺序

**规则**（自上而下）：
1. imports
2. 编译宏：`defineProps` / `defineEmits`（**不要显式 import 它们**，由编译器注入）
3. 状态：`ref` / `reactive`
4. 派生：`computed`
5. 函数
6. `watch` / 生命周期钩子

**理由**：固定的阅读顺序降低认知负担；编译宏置顶让读者第一时间看到组件对外契约。

**好**：
```ts
import { ref, computed, watch, onMounted } from 'vue'
import { useAccountStore } from '@/stores/account'

const props = withDefaults(defineProps<{ modelValue: boolean }>(), { modelValue: false })
const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void }>()

const keyword = ref('')
const filtered = computed(() => keyword.value.trim())
const load = async () => { /* ... */ }
onMounted(load)
```

---

## 3. 类型化 Props 与 Emits（核心规则）

### 3.1 Props：泛型 + withDefaults

- 使用 `defineProps<{ name: Type }>()` 泛型形式。
- 默认值使用 `withDefaults()`。
- **禁止**在模板/逻辑中用 `||` 做 fallback：`0 || 10 === 10`（假值陷阱）。
- **禁止**修改 props（只读）。
- 函数类型 props 写成 `(arg: T) => void`，**禁止**裸 `Function` 类型。

**坏**：
```vue
<script setup lang="ts">
defineProps({
  count: { type: Number, default: 10 },
  onChange: Function,
})
</script>
<template><div>{{ count || 10 }}</div></template>
```

**好**：
```vue
<script setup lang="ts">
withDefaults(defineProps<{ count?: number; onChange?: (v: number) => void }>(), { count: 10 })
</script>
<template><div>{{ count }}</div></template>
```

### 3.2 Emits：泛型签名（当前治理重点）

- 使用 `defineEmits<{ (e: 'event', payload: T): void }>()` **call signature** 形式。
- **禁止**数组形式 `defineEmits(['a', 'b'])` —— payload 类型丢失，调用方无法获得类型安全。
- 事件名保持 kebab-case 或 camelCase 均可，但**同一组件内一致**；`update:modelValue` 必须用冒号形式（v-model 契约）。
- payload 必须显式标注类型；多个事件依次列出。

**坏**（本仓库 48 处现状）：
```ts
const emit = defineEmits(['update:modelValue', 'confirm'])
emit('update:modelValue', value) // 无 payload 校验
```

**好**：
```ts
const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'confirm', payload: { accountId: string }): void
}>()
```

**理由**：数组形式下 `emit('update:modelValue', ...)` 的实参是 `any`，模板消费端与测试都失去类型保护；泛型签名让误传 payload 在 `vue-tsc` 阶段即报错。

---

## 4. Composables

**规则**：
- 命名 `use*`（如 `useAutoSave`、`useChannelForm`、`useConfigMerge`），放在 `src/composables/`。
- 返回 refs（**不要**在返回对象里包 `.value` 或解包后返回裸值）。
- 用 `onScopeDispose` 清理副作用（定时器、事件监听、请求取消）。
- **只允许在组件/其他 composable 的顶层调用**；不要在条件、循环、回调里调用。
- import 模块时**不得**产生副作用（顶层不执行 API 请求、不设置全局状态）。

**好**：
```ts
export function useAutoSave(source: Ref<string>, save: (v: string) => Promise<void>) {
  const timer = ref<ReturnType<typeof setTimeout>>()
  const schedule = () => { /* ... */ }
  onScopeDispose(() => clearTimeout(timer.value))
  return { schedule }
}
```

---

## 5. Pinia（setup syntax）

**规则**：
- `defineStore('id', () => { ... })`，store id 与文件名一致（如 `src/stores/account.ts` → `'account'`）。
- 消费端：state/getters 用 `storeToRefs(store)` 解构；actions 直接解构（保持 `this` 绑定）。
- **禁止**直接解构响应式 store 字段（会丢失响应性）。

**好**：
```ts
const store = useAccountStore()
const { total, list } = storeToRefs(store)
const { fetchList } = store // action
```

---

## 6. v-for 与 :key（当前治理重点）

**规则**：
- 每个 `v-for` 必须有 `:key`，优先稳定业务 id（`item.id`）。
- 本仓库约定**多行属性写法**：`v-for` 与 `:key` 分两行（示例见下）。
- `:key` 不得使用 `index`，除非：列表为**纯追加**（append-only）或**静态**；此时加注释说明。
- `<template v-for>` 时 `:key` 写在 `<template>` 标签上。
- 禁止 `v-if` 与 `v-for` 同元素（Vue 3 中 `v-if` 优先级更高，会造成不可预期的跳过渲染）。

**好**（多行写法 + 稳定 key）：
```vue
<el-option
  v-for="item in platformList"
  :key="item.id"
  :label="item.name"
  :value="item.key"
/>
```

**可接受的例外**（本仓库已存在的 11 处，均符合"纯追加/静态"）：
- `el-tag v-for="(tag, index) in form.tags"`（6 个平台面板）：可删可增 —— 见下方"治理结论"。
- `v-for="i in 28"`（Sponsor 静态星星）。
- 批量结果列表（`results` 纯追加）、`el-table-column` 静态列。

> **治理结论（2026-08）**：全仓 102 处 `v-for` 均已带 `:key`（含多行写法），无需补 key。仅 index-key 的 11 处按上述例外保留（纯文本渲染无内部状态，删除中间项无副作用）。

---

## 7. 模板卫生

**规则**：
- 模板 ≤ 100 行；超出拆子组件。
- 嵌套 ≤ 3 层。
- 单文件脚本逻辑函数 ≤ 30 行；超出抽 composable/子组件。
- 组件原则上单根元素（除非刻意 fragment）。
- 复杂表达式抽到 computed/函数，模板只保留声明式输出。

---

## 8. 异步组件

**规则**：
- `defineAsyncComponent` 仅用于**路由级**或重型懒加载组件（大图、编辑器等），并配置 `loadingComponent` / `errorComponent` / `delay` / `timeout`。
- `<Suspense>` 仅包裹有 **top-level await** 的组件。

---

## 9. TypeScript strict 细则

- 保持 `"strict": true`（本项目已全开，勿关闭）。
- **类型导入**用 `import type { ... }`；值 + 类型混用时用 `import { type X, y }`。
- 公共/导出函数写**显式返回类型**。
- **错误处理**：统一用 `src/utils/error.ts` 的 `getErrorMessage(e)`，**禁止**对 `unknown` 错误直接 `.message`：
  ```ts
  // 坏
  catch (e) { ElMessage.error(e.message) }
  // 好
  catch (e) { ElMessage.error(getErrorMessage(e)) }
  ```
- `any` 仅允许在 **API 边界**（`src/api/*`、`src/utils/request.ts` 的 axios 层）；业务代码必须类型化。现状：API 边界存在少量 `any`（约 61 处），视为已知例外，新增代码不扩散。

---

## 10. 命名与目录

| 类别 | 约定 | 示例 |
|---|---|---|
| 组件文件 | PascalCase 多词 | `ImagePublishPanel.vue` |
| 视图 | 语义化页面名 | `src/views/AccountManagement.vue` |
| Composables | `use*` camelCase | `useChannelForm.ts` |
| Stores | 文件名 = id | `src/stores/account.ts` |
| API 模块 | 按资源分文件 | `src/api/account.ts` |
| Utils | 纯函数 | `src/utils/error.ts` |
| 配置 | 平台/常量 | `src/config/platforms.ts` |
| 测试 | `*.test.ts` 与源文件同目录 | `useChannelForm.test.ts` |

---

## 11. 测试（Vitest）

**规则**：
- 每个测试独立 `mount`（**不在** `beforeEach` 共享 wrapper）。
- 断言渲染结果 DOM 与 `emitted()` 事件；**不**断言 `wrapper.vm` 内部状态。
- **不用** HTML snapshot。
- 覆盖：组件关键交互、composable 行为、store 逻辑；当前 183 用例全绿为基线。

**好**：
```ts
it('emits confirm with payload', async () => {
  const wrapper = mount(Dialog, { props: { modelValue: true } })
  await wrapper.get('button.confirm').trigger('click')
  expect(wrapper.emitted('confirm')).toHaveLength(1)
  expect(wrapper.emitted('confirm')![0]).toEqual([{ accountId: '1' }])
})
```

---

## 12. 治理清单（2026-08-20 基线）

| 项 | 状态 | 处置 |
|---|---|---|
| `defineEmits([...])` 数组形式 | **48 处待改** | 批量迁移为泛型签名（Rule 3.2） |
| v-for 缺 `:key` | 0 处 ✓ | 已全部合规（多行写法） |
| `:key="index"` | 11 处 | 按例外保留（纯追加/静态，Rule 6） |
| Options API / `this.` | 0 处 ✓ | Dashboard.vue 双 script 块属例外，可精简 |
| `defineProps([` 数组形式 | 0 处 ✓ | — |
| `v-if` + `v-for` 同元素 | 0 处 ✓ | — |
| 组件文件名 PascalCase | ✓ | — |
| `storeToRefs` 使用 | 0 处（现为 `store.xxx`） | 合规；新代码按 Rule 5 |

---

*基于 Vue 官方风格指南（Priority A/B/C/D）、官方 TypeScript 指南与社区 .cursorrules 实践整理，按本仓库技术栈裁剪。*
