<template>
  <div
    :data-account-id="account.id"
    :class="['account-card', `platform-${getPlatformClass(account.platform)}`]"
  >
        <div class="card-body">
          <img :src="proxyAvatar(account.avatar) || getDefaultAvatar(account.name)" class="user-avatar" />
          <div class="user-info">
            <span class="user-name">{{ account.name }}</span>
            <div class="platform-row">
              <span class="platform-name">{{ account.platform }}</span>
              <el-tag
                v-if="disabled"
                type="info"
                size="small"
                effect="plain"
                class="disabled-tag"
              >
                已拉黑
              </el-tag>
              <span :class="['status-badge', getStatusClass(account.status)]">
                <span class="status-dot"></span>
                {{ account.status }}
              </span>
            </div>
          </div>
          <div class="platform-logo">
            <img v-if="getPlatformLogo(account.platform)" :src="getPlatformLogo(account.platform) || undefined" :alt="account.platform" class="platform-icon" />
            <span v-else class="platform-letter" :style="{ color: getPlatformColor(account.platform) }">
              {{ getPlatformLetter(account.platform) }}
            </span>
          </div>
        </div>

        <!-- 标签行(独立一行,溢出跑马灯) -->
        <!-- 账号运营数据(stats JSON),按 SORT 升序,最多展示 4 块,超过走悬浮窗 -->
        <div class="account-stats-row" :class="{ 'has-overflow': getExtraStats(account).length > 0 }">
          <!-- 存量数据无运营数据:显示占位提示,引导用户点同步 -->
          <div v-if="!sortStats(account?.stats).length" class="stat-block-empty">
            <el-icon class="empty-icon"><Clock /></el-icon>
            <span class="empty-text">暂无运营数据，点下方同步按钮获取</span>
          </div>

          <template v-for="(item, idx) in getVisibleStats(account)" :key="`${account.id}-${item.NAME}-${idx}`">
            <div
              class="stat-block"
              :class="[`stat-block-${item.ICON}`, { 'is-empty': !Number(item.COUNT) }]"
              :title="item.NAME"
            >
              <div class="stat-icon-wrap">
                <component :is="getIconComponent(item.ICON ?? '')" />
              </div>
              <div class="stat-value">{{ formatStat(item.COUNT) }}</div>
              <div class="stat-label">{{ item.NAME }}</div>
            </div>
          </template>

          <!-- 超出卡片显示位数的(超过 visible count),用"更多"占位 + 原生 CSS hover 浮窗;
             浮窗在卡片 DOM 内,完全自控,不受全局 popper 样式影响。
             浮窗位置由 JS 在 mouseenter 时计算,避免最右侧卡片溢出视口触发横向滚动条 -->
          <div
            v-if="sortStats(account?.stats).length > getVisibleCount(account)"
            class="stat-block stat-block-more stats-more-wrap"
            @mouseenter="handleStatsHover"
          >
            <div class="stat-icon-wrap">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="5" cy="12" r="1"></circle>
                <circle cx="12" cy="12" r="1"></circle>
                <circle cx="19" cy="12" r="1"></circle>
              </svg>
            </div>
            <div class="stat-value">+{{ sortStats(account?.stats).length - getVisibleCount(account) }}</div>
            <div class="stat-label">更多</div>

            <!-- 悬浮浮窗:绝对定位在 stat-block 上方 -->
            <div class="stats-more-popover">
              <div
                v-for="(item, idx) in getExtraStats(account)"
                :key="`extra-${item.NAME}-${idx}`"
                class="stats-more-item"
              >
                <span class="name">{{ item.NAME }}</span>
                <strong class="value">{{ formatStat(item.COUNT) }}</strong>
              </div>
            </div>
          </div>
        </div>
        <div class="account-tags-row">
          <span class="account-tags-label">标签:</span>
          <div
            v-if="account.tags && account.tags.length > 0"
            :class="['account-tags-viewport', { 'is-overflow': tagOverflowMap[account.id] }]"
          >
            <div
              class="account-tags-track"
              :class="{ marquee: tagOverflowMap[account.id] }"
            >
              <span
                v-for="tag in tagOverflowMap[account.id] ? [...account.tags, ...account.tags] : account.tags"
                :key="tag.id + '-' + (tagOverflowMap[account.id] ? 'b' : 'a')"
                class="account-tag"
                :style="{ borderColor: tag.color, color: tag.color }"
              >
                {{ tag.name }}
                <span
                  class="account-tag-remove"
                  title="从该账号移除此标签"
                  @click.stop="emit('remove-tag', account, tag)"
                >×</span>
              </span>
            </div>
          </div>
          <TagPopover
            :visible="tagVisible"
            :account-id="account.id"
            :selected-tags="account.tags || []"
            @update:visible="tagVisible = $event"
            @changed="emit('tag-changed')"
          >
            <button class="tag-add-btn" @click.stop="tagVisible = true">
              <el-icon><Plus /></el-icon>
            </button>
          </TagPopover>
        </div>

        <!-- 卡片底部：操作按钮 -->
        <div class="card-footer">
          <div class="card-actions">
            <button
              v-if="account.status === '异常'"
              class="action-btn login"
              :class="{ 'is-blacklisted': disabled }"
              :disabled="disabled"
              :title="disabled ? '该渠道已被加入黑名单,请先在系统设置中移除' : ''"
              @click="emit('relogin', account)"
            >
              <el-icon><Key /></el-icon>
              {{ disabled ? '已拉黑' : '登录' }}
            </button>
            <button v-else class="action-btn check" @click="emit('check', account)" :disabled="checkingIds.has(account.id)">
              <el-icon v-if="checkingIds.has(account.id)" class="is-loading"><Loading /></el-icon>
              <template v-else>
                <el-icon><Check /></el-icon>
                检查
              </template>
            </button>
            <button
              class="action-btn sync"
              :class="{ 'is-blacklisted': disabled }"
              :disabled="disabled || account.status === '异常' || syncingIds.has(account.id)"
              :title="disabled ? '该渠道已被加入黑名单,请先在系统设置中移除' : ''"
              @click="emit('sync', account)"
            >
              <el-icon v-if="syncingIds.has(account.id)" class="is-loading"><Loading /></el-icon>
              <template v-else>
                <el-icon><Refresh /></el-icon>
                同步
              </template>
            </button>
            <button
              class="action-btn creator"
              :class="{ 'is-blacklisted': disabled }"
              :disabled="disabled || account.status === '异常'"
              :title="disabled ? '该渠道已被加入黑名单,请先在系统设置中移除' : ''"
              @click="emit('creator', account)"
            >
              <el-icon><Link /></el-icon>
              创作中心
            </button>
            <button class="action-btn delete" @click="emit('delete', account)">
              <el-icon><Delete /></el-icon>
              删除
            </button>
          </div>
        </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Check, Clock, Delete, Key, Link, Loading, Plus, Refresh } from '@element-plus/icons-vue'
import TagPopover from '@/components/TagPopover.vue'
import { getDefaultAvatar, proxyAvatar } from '@/utils/avatar'
import {
  type AccountItem,
  type TagItem,
  getPlatformClass,
  getPlatformLogo,
  getPlatformColor,
  getPlatformLetter,
  getStatusClass,
  formatStat,
  sortStats,
  getVisibleCount,
  getVisibleStats,
  getExtraStats,
  handleStatsHover,
  getIconComponent,
  type StatItem,
} from '@/components/accountCardShared'

const props = defineProps<{
  account: AccountItem
  checkingIds: Set<number | string>
  syncingIds: Set<number | string>
  tagOverflowMap: Record<number | string, boolean>
  disabled: boolean
}>()

const emit = defineEmits<{
  (e: 'check', account: AccountItem): void
  (e: 'sync', account: AccountItem): void
  (e: 'relogin', account: AccountItem): void
  (e: 'creator', account: AccountItem): void
  (e: 'delete', account: AccountItem): void
  (e: 'remove-tag', account: AccountItem, tag: TagItem): void
  (e: 'tag-changed'): void
}>()

// 每张卡片的标签弹层可见性（原视图按 accountId 全局管理，此处内聚到卡片）
const tagVisible = ref(false)
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

  .account-card {
    background: $bg-surface;
    border: 1px solid $border;
    border-radius: 16px;
    padding: 20px;
    transition: all $transition-base;
    position: relative;
    // 注意:不能用 overflow: hidden,否则账号卡片"更多"悬浮浮窗(绝对定位、向上超出
    // 卡片边界)会被裁切。卡片内元素均在 padding 内,圆角由 border-radius 自然形成。

    &::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 3px;
      background: linear-gradient(90deg, transparent, rgba($overlay-rgb, 0.1), transparent);
      border-radius: 16px 16px 0 0;
      opacity: 0;
      transition: opacity $transition-base;
    }

    &:hover {
      transform: translateY(-4px);
      border-color: rgba($brand-start, 0.4);
      box-shadow: 0 8px 30px rgba(0, 0, 0, 0.3), 0 0 0 1px rgba($brand-start, 0.1);

      &::before {
        opacity: 1;
      }
    }

    // Platform-specific accent colors
    &.platform-douyin:hover { border-color: rgba($platform-douyin, 0.5); box-shadow: 0 8px 30px rgba(0, 0, 0, 0.3), 0 0 20px rgba($platform-douyin, 0.15); }
    &.platform-kuaishou:hover { border-color: rgba($platform-kuaishou, 0.5); box-shadow: 0 8px 30px rgba(0, 0, 0, 0.3), 0 0 20px rgba($platform-kuaishou, 0.15); }
    &.platform-channels:hover { border-color: rgba($platform-channels, 0.5); box-shadow: 0 8px 30px rgba(0, 0, 0, 0.3), 0 0 20px rgba($platform-channels, 0.15); }
    &.platform-xiaohongshu:hover { border-color: rgba($platform-xiaohongshu, 0.5); box-shadow: 0 8px 30px rgba(0, 0, 0, 0.3), 0 0 20px rgba($platform-xiaohongshu, 0.15); }
    &.platform-bilibili:hover { border-color: rgba($platform-bilibili, 0.5); box-shadow: 0 8px 30px rgba(0, 0, 0, 0.3), 0 0 20px rgba($platform-bilibili, 0.15); }

    .card-body {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 12px;

      .user-avatar {
        width: 48px;
        height: 48px;
        border-radius: 50%;
        object-fit: cover;
        border: 2px solid $border;
        flex-shrink: 0;
      }

      .user-info {
        flex: 1;
        min-width: 0;
        display: flex;
        flex-direction: column;
        gap: 6px;

        .user-name {
          font-size: 16px;
          font-weight: 600;
          color: $text-primary;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .platform-row {
          display: flex;
          align-items: center;
          gap: 10px;

          .platform-name {
            font-size: 13px;
            color: $text-muted;
          }

          .disabled-tag {
            margin-left: 4px;
            border-style: dashed;
          }

          .status-badge {
            display: flex;
            align-items: center;
            gap: 5px;
            font-size: 11px;
            font-weight: 500;
            padding: 2px 8px;
            border-radius: 12px;

            .status-dot {
              width: 5px;
              height: 5px;
              border-radius: 50%;
            }

            &.normal {
              background: rgba($success-color, 0.15);
              color: $success-color;
              .status-dot { background: $success-color; }
            }

            &.pending {
              background: rgba($info-color, 0.15);
              color: $info-color;
              .status-dot { background: $info-color; animation: pulse 1.5s infinite; }
            }

            &.error {
              background: rgba($danger-color, 0.15);
              color: $danger-color;
              .status-dot { background: $danger-color; }
            }
          }
        }
      }

      .platform-logo {
        width: 48px;
        height: 48px;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;

        .platform-icon {
          width: 40px;
          height: 40px;
          object-fit: contain;
        }

        .platform-letter {
          font-size: 20px;
          font-weight: 700;
        }
      }
    }

    // 标签行(独立一行,溢出跑马灯)
    .account-tags-row {
      display: flex;
      align-items: center;
      gap: 6px;
      margin-top: 4px;
      margin-bottom: 12px;
      min-height: 22px;
    }

    // 账号运营数据行(stats JSON):动态渲染统计块
    .account-stats-row {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(0, 1fr));
      gap: 8px;
      margin-top: 8px;
      margin-bottom: 8px;
      // 固定最小高度,让"已同步"(3 块 stat-block) 和"未同步"
      // (1 块 stat-block-empty) 两种情况下卡片下半部分布局一致
      min-height: 64px;

      // 存量未同步数据的占位块(跨满整行,提示用户点同步)
      .stat-block-empty {
        grid-column: 1 / -1;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 6px;
        padding: 10px 12px;
        border-radius: $radius-sm;
        border: 1px dashed $border-light;
        background: rgba($overlay-rgb, 0.03);
        color: $text-muted;
        font-size: 12px;

        .empty-icon {
          font-size: 14px;
          opacity: 0.7;
        }

        .empty-text {
          font-size: 12px;
        }
      }

      .stat-block {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 7px 4px 6px;
        border-radius: $radius-sm;
        border: 1px solid transparent;
        transition: all $transition-fast;
        min-width: 0;
        // 固定 stat-block 高度,与 .stat-block-empty 保持一致,
        // 这样无论"已同步"还是"未同步"账号,卡片下半部分
        // (stats-row + tags-row + actions-row) 高度都一致
        min-height: 64px;

        .stat-icon-wrap {
          width: 22px;
          height: 22px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          margin-bottom: 3px;

          svg {
            width: 12px;
            height: 12px;
          }
        }

        .stat-value {
          font-size: 16px;
          font-weight: 700;
          color: $text-primary;
          font-variant-numeric: tabular-nums;
          line-height: 1.15;
          white-space: nowrap;
        }

        .stat-label {
          font-size: 11px;
          color: $text-muted;
          margin-top: 1px;
          max-width: 100%;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        // 按 ICON 字符串动态配色(stats JSON 里的 ICON 字段值)
        &.stat-block-user {
          background: rgba($brand-start, 0.15);
          border-color: rgba($brand-start, 0.35);
          .stat-icon-wrap { background: $brand-start; color: #fff; }
        }
        &.stat-block-like {
          background: rgba($accent-rose, 0.15);
          border-color: rgba($accent-rose, 0.35);
          .stat-icon-wrap { background: $accent-rose; color: #fff; }
        }
        &.stat-block-follow {
          background: rgba($accent-cyan, 0.15);
          border-color: rgba($accent-cyan, 0.35);
          .stat-icon-wrap { background: $accent-cyan; color: #fff; }
        }
        &.stat-block-play,
        &.stat-block-video {
          background: rgba($info-color, 0.15);
          border-color: rgba($info-color, 0.35);
          .stat-icon-wrap { background: $info-color; color: #fff; }
        }
        &.stat-block-star {
          background: rgba($accent-amber, 0.15);
          border-color: rgba($accent-amber, 0.35);
          .stat-icon-wrap { background: $accent-amber; color: #fff; }
        }
        &.stat-block-coin {
          background: rgba(#eab308, 0.18);
          border-color: rgba(#eab308, 0.4);
          .stat-icon-wrap { background: #eab308; color: #fff; }
        }
        &.stat-block-chat {
          background: rgba($accent-green, 0.15);
          border-color: rgba($accent-green, 0.35);
          .stat-icon-wrap { background: $accent-green; color: #fff; }
        }
        &.stat-block-share {
          background: rgba($accent-cyan, 0.12);
          border-color: rgba($accent-cyan, 0.3);
          .stat-icon-wrap { background: $accent-cyan; color: #fff; }
        }

        // 原创/编辑图标
        &.stat-block-edit {
          background: rgba($accent-amber, 0.15);
          border-color: rgba($accent-amber, 0.35);
          .stat-icon-wrap { background: $accent-amber; color: #fff; }
        }

        // "更多"块:中性灰(不抢眼)+ 作为悬浮浮窗的定位锚点
        &.stat-block-more {
          background: rgba($overlay-rgb, 0.05);
          border-color: $border-light;
          cursor: help;
          position: relative;

          .stat-icon-wrap {
            background: rgba($overlay-rgb, 0.1);
            color: $text-muted;
          }

          .stat-value {
            color: $text-secondary;
          }

          // 原生 hover 浮窗:绝对定位在 more 块上方,卡片 DOM 内完全自控
          .stats-more-popover {
            // 默认隐藏
            visibility: hidden;
            opacity: 0;
            transition: opacity 150ms ease, transform 150ms ease, visibility 150ms;

            // 浮窗样式:品牌紫渐变背景,白色文字,跟卡片整体调性一致
            position: absolute;
            bottom: calc(100% + 8px);
            left: 50%;
            // 水平方向:默认居中(translateX(-50%)),JS 在 hover 时根据视口边界
            // 设置 --stats-popover-offset 变量微调,避免最右侧卡片溢出
            transform: translateX(calc(-50% + var(--stats-popover-offset, 0px))) translateY(4px);
            z-index: 100;

            min-width: 220px;
            padding: 10px 14px;
            border-radius: $radius-base;
            background: linear-gradient(135deg, rgba($brand-start, 0.95), rgba($brand-end, 0.92));
            border: 1px solid rgba($brand-start, 0.6);
            box-shadow: 0 6px 20px rgba($brand-start, 0.35), 0 2px 6px rgba(0, 0, 0, 0.15);

            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px 18px;

            // 鼠标悬停 more 块或浮窗自身时显示
            pointer-events: none;
          }

          // hover 时显示浮窗
          &:hover .stats-more-popover {
            visibility: visible;
            opacity: 1;
            transform: translateX(calc(-50% + var(--stats-popover-offset, 0px))) translateY(0);
            pointer-events: auto;
          }

          // 浮窗内的每一项
          .stats-more-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            min-width: 0;

            .name {
              font-size: 12px;
              color: rgba(255, 255, 255, 0.78);
              font-weight: 500;
            }

            .value {
              font-size: 13px;
              font-weight: 700;
              color: #fff;
              font-variant-numeric: tabular-nums;
            }
          }
        }

        // 数据为 0 时:数字和图标淡化,背景保留彩色(避免变成"灰板")
        &.is-empty {
          .stat-icon-wrap {
            opacity: 0.5;
          }

          .stat-value {
            color: $text-muted;
            font-weight: 600;
          }
        }

        &:hover {
          transform: translateY(-1px);
          border-color: $border-active;
        }
      }
    }

    // 悬浮窗内的"更多数据"网格 —— 移到全局 <style> 块定义(el-tooltip 内容渲染到 body,
    // scoped CSS 里的 :deep() 编译后仍带外层选择器前缀,无法匹配 popper DOM)
    // 见 <style lang="scss"> 块末尾的全局 .account-stats-tooltip 样式

    .account-tags-label {
      font-size: 12px;
      color: $text-muted;
      font-weight: 500;
      flex: 0 0 auto;
      user-select: none;
    }

    .account-tags-viewport {
      // 按内容自适应,溢出时收缩并启用 mask + marquee
      flex: 0 1 auto;
      min-width: 0;
      overflow: hidden;
      position: relative;

      // 仅溢出时渐隐边缘(正常情况保持 chip 完整显示)
      &.is-overflow {
        mask-image: linear-gradient(to right, transparent 0, black 12px, black calc(100% - 12px), transparent 100%);
        -webkit-mask-image: linear-gradient(to right, transparent 0, black 12px, black calc(100% - 12px), transparent 100%);
      }
    }

    .account-tags-track {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      width: max-content;
      padding-right: 6px;

      &.marquee {
        animation: tag-marquee 18s linear infinite;

        &:hover { animation-play-state: paused; }
      }
    }

    @keyframes tag-marquee {
      from { transform: translateX(0); }
      to { transform: translateX(-50%); }
    }

    .account-tag {
      position: relative;
      display: inline-flex;
      align-items: center;
      padding: 1px 7px;
      border: 1px solid;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 500;
      line-height: 16px;
      white-space: nowrap;
      flex-shrink: 0;
      transition: all $transition-fast;

      &:hover {
        .account-tag-remove {
          opacity: 1;
          transform: scale(1);
        }
      }
    }

    .account-tag-remove {
      position: absolute;
      top: -5px;
      right: -5px;
      width: 14px;
      height: 14px;
      border-radius: 50%;
      background: $danger-color;
      color: #fff;
      font-size: 11px;
      font-weight: 700;
      line-height: 1;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      opacity: 0;
      transform: scale(0.6);
      cursor: pointer;
      transition: all $transition-fast;
      box-shadow: 0 1px 4px rgba(0, 0, 0, 0.4);
      z-index: 1;

      &:hover {
        background: #dc2626;
        transform: scale(1.1);
      }
    }

    .tag-add-btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 18px;
      height: 18px;
      flex: 0 0 auto;
      border: 1px dashed rgba($overlay-rgb, 0.2);
      border-radius: 4px;
      background: transparent;
      color: $text-muted;
      cursor: pointer;
      font-size: 12px;
      transition: all $transition-base;

      &:hover {
        border-color: $brand-start;
        color: $brand-start;
        background: rgba($brand-start, 0.1);
      }
    }

    .card-footer {
      display: flex;
      align-items: center;
      padding-top: 12px;
      border-top: 1px solid $border-light;

      .card-actions {
        display: flex;
        align-items: center;
        gap: 6px;
        width: 100%;
      }

      .action-btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 4px;
        padding: 6px 8px;
        border: none;
        border-radius: 8px;
        font-size: 12px;
        font-weight: 500;
        cursor: pointer;
        transition: all $transition-base;
        background: rgba($overlay-rgb, 0.05);
        color: $text-secondary;
        white-space: nowrap;
        flex: 1 1 0;
        min-width: 0;

        .el-icon {
          font-size: 14px;
        }

        &:hover:not(:disabled) {
          transform: translateY(-1px);
        }

        &:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        &.is-blacklisted {
          opacity: 0.5;
          cursor: not-allowed;
        }

        &.check {
          background: rgba($success-color, 0.1);
          color: $success-color;
          &:hover:not(:disabled) { background: rgba($success-color, 0.2); box-shadow: 0 2px 10px rgba($success-color, 0.2); }
        }

        &.login {
          background: rgba($warning-color, 0.1);
          color: $warning-color;
          &:hover:not(:disabled) { background: rgba($warning-color, 0.2); box-shadow: 0 2px 10px rgba($warning-color, 0.2); }
        }

        &.sync {
          background: rgba($info-color, 0.1);
          color: $info-color;
          &:hover:not(:disabled) { background: rgba($info-color, 0.2); box-shadow: 0 2px 10px rgba($info-color, 0.2); }
        }

        &.creator {
          background: rgba($accent-cyan, 0.1);
          color: $accent-cyan;
          &:hover:not(:disabled) { background: rgba($accent-cyan, 0.2); box-shadow: 0 2px 10px rgba($accent-cyan, 0.2); }
        }

        &.delete {
          background: rgba($danger-color, 0.1);
          color: $danger-color;
          &:hover:not(:disabled) { background: rgba($danger-color, 0.2); box-shadow: 0 2px 10px rgba($danger-color, 0.2); }
        }
      }
    }
  }
</style>
