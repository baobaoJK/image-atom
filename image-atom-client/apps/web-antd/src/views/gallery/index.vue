<script lang="ts" setup>
import type { CategoryItem, ImageItem, TagItem } from '#/api/gallery';

import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';

import { useMediaQuery } from '@vueuse/core';
import {
  Button,
  Dropdown,
  Menu,
  MenuItem,
  Modal,
  Pagination,
  Select,
  message,
} from 'ant-design-vue';

import {
  batchDeleteImageApi,
  deleteImageApi,
  getStatsApi,
  listCategoriesApi,
  listImagesApi,
  listTagsApi,
} from '#/api/gallery';
import { copyImageWithFallback } from '#/utils/clipboard';
import type { ShareEnv } from '#/utils/share';
import { detectShareEnv, saveImageToPhone, shareImage } from '#/utils/share';
import BatchEditModal from './batch-edit-modal.vue';
import EditImageModal from './edit-modal.vue';

defineOptions({ name: 'Gallery' });

const PAGE_SIZE = 30;

const router = useRouter();
const isPc = useMediaQuery('(min-width: 768px)');

const items = ref<ImageItem[]>([]);
const tags = ref<TagItem[]>([]);
const categories = ref<CategoryItem[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(PAGE_SIZE);
const hasMore = ref(false);
const loading = ref(false);
const activeTag = ref('');
const activeCategory = ref('');
const activeType = ref<'' | 'animated' | 'static'>('');
const copyingId = ref<number | null>(null);

// 右键菜单与编辑弹窗
const contextItem = ref<null | ImageItem>(null);
const editOpen = ref(false);
const editing = ref<null | ImageItem>(null);
// 分享：不支持系统分享面板时展示长按保存的预览兜底
const previewItem = ref<null | ImageItem>(null);
const sharingId = ref<number | null>(null);

// ---------- 框选与批量操作（无需开关，按住拖动即可框选） ----------
const selectedIds = ref(new Set<number>());
const batchEditOpen = ref(false);
const marqueeRect = ref<null | { h: number; w: number; x: number; y: number }>(
  null,
);
const marqueeRemove = ref(false);
// 框选结束后的残余 click 不应再触发选中切换/复制
let dragSuppressClick = false;

interface GridDragState {
  active: boolean;
  baseSelection: Set<number>;
  pressingCard: null | number;
  removeMode: boolean;
  startX: number;
  startY: number;
}

let gridDragState: null | GridDragState = null;
const MARQUEE_THRESHOLD = 5;

function toggleSelect(id: number) {
  const next = new Set(selectedIds.value);
  if (next.has(id)) {
    next.delete(id);
  } else {
    next.add(id);
  }
  selectedIds.value = next;
}

function selectAllCurrent() {
  selectedIds.value = new Set(items.value.map((item) => item.id));
}

function clearSelection() {
  selectedIds.value = new Set<number>();
}

/** 反选：当前页内，选中的取消、未选中的全选 */
function invertSelection() {
  const next = new Set<number>();
  for (const item of items.value) {
    if (!selectedIds.value.has(item.id)) next.add(item.id);
  }
  selectedIds.value = next;
}

async function handleBatchDelete() {
  const ids = [...selectedIds.value];
  if (ids.length === 0) return;
  Modal.confirm({
    content: '将同时删除这些图片的原图和缩略图文件，且不可恢复。',
    okText: '全部删除',
    okType: 'danger',
    title: `确认删除选中的 ${ids.length} 张图片？`,
    async onOk() {
      try {
        await batchDeleteImageApi(ids);
        message.success(`已删除 ${ids.length} 张图片`);
        clearSelection();
        await refreshFilters();
        fetchList('replace');
      } catch {
        message.error('批量删除失败');
      }
    },
  });
}

function onBatchUpdated() {
  clearSelection();
  refreshFilters();
  fetchList('replace');
}

function applyMarqueeSelection(rect: {
  h: number;
  w: number;
  x: number;
  y: number;
}) {
  const drag = gridDragState;
  const next = new Set(drag?.baseSelection ?? selectedIds.value);
  const remove = drag?.removeMode ?? false;
  document
    .querySelectorAll<HTMLElement>('.pc-grid .pc-card[data-id]')
    .forEach((el) => {
      const id = Number(el.dataset.id);
      const box = el.getBoundingClientRect();
      const intersect =
        box.right > rect.x &&
        box.left < rect.x + rect.w &&
        box.bottom > rect.y &&
        box.top < rect.y + rect.h;
      if (remove) {
        // Ctrl 反向框选：框住的从选择中剔除
        if (intersect) next.delete(id);
      } else if (intersect) {
        next.add(id);
      }
    });
  selectedIds.value = next;
}

function onGridMouseMove(e: MouseEvent) {
  if (!gridDragState) return;
  e.preventDefault();
  // 拖动中随时可按/松 Shift 在"加选"与"反选"间切换
  gridDragState.removeMode = e.shiftKey;
  marqueeRemove.value = e.shiftKey;
  const dx = Math.abs(e.clientX - gridDragState.startX);
  const dy = Math.abs(e.clientY - gridDragState.startY);
  // 未超过阈值前当作单击，不画框
  if (
    !gridDragState.active &&
    dx < MARQUEE_THRESHOLD &&
    dy < MARQUEE_THRESHOLD
  ) {
    return;
  }
  gridDragState.active = true;
  const rect = {
    h: dy,
    w: dx,
    x: Math.min(gridDragState.startX, e.clientX),
    y: Math.min(gridDragState.startY, e.clientY),
  };
  marqueeRect.value = rect;
  // Windows 式实时选区：拖动过程中相交的卡片即时高亮/剔除
  applyMarqueeSelection(rect);
}

function onGridMouseUp(e: MouseEvent) {
  if (!gridDragState) return;
  document.removeEventListener('mousemove', onGridMouseMove);
  document.removeEventListener('mouseup', onGridMouseUp);
  const { active, pressingCard } = gridDragState;
  gridDragState = null;
  marqueeRect.value = null;

  if (active) {
    // 拖拽结束：拦截后续 click，避免误切换最后按下的卡片
    dragSuppressClick = true;
    setTimeout(() => {
      dragSuppressClick = false;
    }, 80);
    return;
  }
  // 没有移动 → 普通单击：卡片自身的 click 事件（handleCardClick）负责切换选中，
  // 这里只处理点在网格空白处的情况（与 Windows 一致，点击空白清除选择）
  if (pressingCard === null && !(e.target as HTMLElement).closest?.('.pc-card')) {
    clearSelection();
  }
}

/** Windows 式框选：网格任意位置（包括图片上）按住拖动即可框选；
 * 按住 Ctrl 拖动为反向框选（剔除）。 */
function onGridMouseDown(e: MouseEvent) {
  if (!isPc.value || e.button !== 0) return;
  e.preventDefault(); // 阻止文字选择与浏览器原生图片拖拽
  const cardEl = (e.target as HTMLElement).closest?.('.pc-card');
  gridDragState = {
    active: false,
    baseSelection: new Set(selectedIds.value),
    pressingCard: cardEl ? Number((cardEl as HTMLElement).dataset.id) : null,
    removeMode: e.shiftKey,
    startX: e.clientX,
    startY: e.clientY,
  };
  marqueeRemove.value = e.shiftKey;
  document.addEventListener('mousemove', onGridMouseMove);
  document.addEventListener('mouseup', onGridMouseUp);
}

const sentinelRef = ref<HTMLElement>();
let observer: null | IntersectionObserver = null;

const categoryOptions = ref<{ label: string; value: string }[]>([]);
// 图片类型数量（用于筛选按钮显示"静态图 N / 动态图 N"）
const typeCounts = ref({ animated: 0, static: 0 });

async function fetchList(mode: 'append' | 'replace') {
  if (loading.value) return;
  loading.value = true;
  try {
    const result = await listImagesApi({
      category: activeCategory.value || undefined,
      page: page.value,
      pageSize: pageSize.value,
      tags: activeTag.value || undefined,
      type: activeType.value,
    });
    items.value =
      mode === 'append' ? [...items.value, ...result.items] : result.items;
    total.value = result.total;
    hasMore.value = result.hasMore;
    // 翻页 / 筛选后列表已变化，Windows 式选择不跨页保留
    if (mode === 'replace') clearSelection();
  } finally {
    loading.value = false;
  }
}

async function refreshFilters() {
  const [tagList, categoryList, stats] = await Promise.all([
    listTagsApi(activeCategory.value || undefined, activeType.value || undefined),
    listCategoriesApi(),
    getStatsApi(),
  ]);
  typeCounts.value = stats.typeCounts;
  tags.value = tagList;
  categories.value = categoryList;
  categoryOptions.value = categoryList.map((c) => ({
    label: `${c.name} (${c.count})`,
    value: c.name,
  }));
}

function selectTag(name: string) {
  if (activeTag.value === name) return;
  activeTag.value = name;
}

function selectType(name: '' | 'animated' | 'static') {
  if (activeType.value === name) return;
  activeType.value = name;
}

// 切换分类：标签栏按分类联动刷新；当前选中的标签若不在新分类里则重置
// 分类或图片类型变化：标签栏按新范围联动刷新；失效标签自动重置
watch([activeCategory, activeType], async () => {
  page.value = 1;
  const tagList = await listTagsApi(
    activeCategory.value || undefined,
    activeType.value || undefined,
  );
  tags.value = tagList;
  if (activeTag.value && !tagList.some((t) => t.name === activeTag.value)) {
    activeTag.value = '';
  } else {
    fetchList('replace');
  }
});

// 标签变化：回到第 1 页重新拉取
watch(activeTag, () => {
  page.value = 1;
  fetchList('replace');
});

// PC：翻页 / 每页数量变化都重新拉取
watch(
  () => page.value,
  (_newPage, oldPage) => {
    if (isPc.value && oldPage !== undefined) fetchList('replace');
  },
);
watch(pageSize, () => {
  page.value = 1;
  if (isPc.value) fetchList('replace');
});

// 移动端：触底加载下一页
function loadMore() {
  if (!isPc.value && hasMore.value && !loading.value) {
    page.value += 1;
    fetchList('append');
  }
}

async function handleCardClick(item: ImageItem, event?: MouseEvent) {
  // 框选拖拽结束时浏览器会补发一次 click，此时忽略
  if (dragSuppressClick) return;
  // Shift + 单击：切换单张选中
  if (event?.shiftKey) {
    toggleSelect(item.id);
    return;
  }
  if (copyingId.value) return;
  copyingId.value = item.id;
  try {
    message.success(await copyImageWithFallback(item.url));
  } catch {
    message.error('复制失败');
  } finally {
    copyingId.value = null;
  }
}

function formatSize(size: number): string {
  return size > 1024 * 1024
    ? `${(size / 1024 / 1024).toFixed(1)}MB`
    : `${Math.max(1, Math.round(size / 1024))}KB`;
}

// ---------- 右键菜单 ----------
function onMenuClick({ key }: { key: string | number }) {
  const item = contextItem.value;
  if (!item) return;
  switch (key) {
    case 'edit': {
      editing.value = item;
      editOpen.value = true;
      break;
    }
    case 'delete': {
      confirmDelete(item);
      break;
    }
    case 'share': {
      handleShare(item);
      break;
    }
    case 'open': {
      window.open(item.url, '_blank');
      break;
    }
    case 'copy-link': {
      navigator.clipboard
        .writeText(`${location.origin}${item.url}`)
        .then(() => message.success('原图链接已复制'))
        .catch(() => message.error('复制失败'));
      break;
    }
  }
}

// ---------- 分享到微信 / QQ ----------
// 分享弹窗：在微信 / QQ 内置浏览器里打开时给出对应操作指引
const shareEnv = ref<'' | ShareEnv>('');
const shareEnvHint = computed(() => {
  switch (shareEnv.value) {
    case 'qq': {
      return 'QQ 内长按图片即可「保存」或「发送给好友」';
    }
    case 'wechat': {
      return '微信内长按图片转发给朋友，或点右上角 ⋯ 发送到聊天';
    }
    default: {
      return '长按图片保存后，可在微信 / QQ 中发送';
    }
  }
});

async function handleShare(item: ImageItem) {
  if (sharingId.value) return;
  sharingId.value = item.id;
  shareEnv.value = detectShareEnv();
  try {
    const result = await shareImage(
      item.url,
      item.originalName,
      '来自图元的表情包',
    );
    if (result === 'file-shared') {
      message.success('已调起分享，选择微信或QQ即可发送图片');
    } else if (result === 'link-shared') {
      message.success('已调起分享');
    } else {
      // 微信 / QQ 内置浏览器等不支持系统分享：展示大图 + 保存/长按引导
      previewItem.value = item;
    }
  } catch (error) {
    // 用户取消分享面板不算错误
    if ((error as { name?: string })?.name !== 'AbortError') {
      message.error('分享失败');
    }
  } finally {
    sharingId.value = null;
  }
}

async function savePreviewImage(item: ImageItem) {
  try {
    await saveImageToPhone(item.url, item.originalName);
    message.success('已开始下载，请到相册 / 下载目录查看');
  } catch {
    message.error('保存失败，请长按图片保存');
  }
}

async function copyPreviewLink(item: ImageItem) {
  try {
    await navigator.clipboard.writeText(`${location.origin}${item.url}`);
    message.success('原图链接已复制');
  } catch {
    message.error('复制失败');
  }
}

async function copyPreviewImage(item: ImageItem) {
  try {
    message.success(await copyImageWithFallback(item.url));
  } catch {
    message.error('复制失败');
  }
}

function confirmDelete(item: ImageItem) {
  Modal.confirm({
    content: '将同时删除原图和缩略图文件，且不可恢复。',
    okText: '删除',
    okType: 'danger',
    title: `确认删除「${item.originalName}」？`,
    async onOk() {
      try {
        await deleteImageApi(item.id);
        items.value = items.value.filter((img) => img.id !== item.id);
        total.value -= 1;
        if (items.value.length === 0 && page.value > 1) {
          page.value -= 1;
        } else if (isPc.value) {
          fetchList('replace');
        }
        refreshFilters();
        message.success('已删除');
      } catch {
        message.error('删除失败');
      }
    },
  });
}

// ---------- 编辑弹窗回调 ----------
function onSaved(updated: ImageItem) {
  items.value = items.value.map((item) =>
    item.id === updated.id ? updated : item,
  );
  refreshFilters();
}

function onDeleted(id: number) {
  items.value = items.value.filter((item) => item.id !== id);
  total.value -= 1;
  if (items.value.length === 0 && page.value > 1) {
    page.value -= 1;
  } else if (isPc.value) {
    fetchList('replace');
  }
  refreshFilters();
}

onMounted(async () => {
  await refreshFilters();
  await fetchList('replace');
  observer = new IntersectionObserver(
    (entries) => {
      if (entries[0]?.isIntersecting) loadMore();
    },
    { rootMargin: '400px' },
  );
  if (sentinelRef.value) observer.observe(sentinelRef.value);
});

onBeforeUnmount(() => observer?.disconnect());
</script>

<template>
  <div class="gallery-page p-4 md:p-5">
    <!-- 筛选栏：图片类型 / 分类 / 标签 -->
    <div class="mb-3 flex flex-wrap items-center gap-2">
      <button
        class="type-chip"
        :class="{ 'type-chip-active': activeType === '' }"
        @click="selectType('')"
      >
        全部
        <span class="opacity-60">
          {{ typeCounts.static + typeCounts.animated }}
        </span>
      </button>
      <button
        class="type-chip"
        :class="{ 'type-chip-active': activeType === 'static' }"
        @click="selectType('static')"
      >
        静态图
        <span class="opacity-60">{{ typeCounts.static }}</span>
      </button>
      <button
        class="type-chip"
        :class="{ 'type-chip-active': activeType === 'animated' }"
        @click="selectType('animated')"
      >
        动态图
        <span class="opacity-60">{{ typeCounts.animated }}</span>
      </button>
      <Select
        v-model:value="activeCategory"
        :options="categoryOptions"
        allow-clear
        class="min-w-36"
        placeholder="分类文件夹"
        size="small"
      />
    </div>
    <div v-if="tags.length" class="mb-4 flex flex-wrap items-center gap-2">
      <button
        class="tag-chip"
        :class="{ 'tag-chip-active': activeTag === '' }"
        @click="selectTag('')"
      >
        全部标签
      </button>
      <button
        v-for="tag in tags"
        :key="tag.id"
        class="tag-chip"
        :class="{ 'tag-chip-active': activeTag === tag.name }"
        @click="selectTag(tag.name)"
      >
        {{ tag.name }}
        <span class="opacity-60">{{ tag.count }}</span>
      </button>
    </div>

    <!-- 空状态 -->
    <div
      v-if="!loading && items.length === 0"
      class="flex flex-col items-center gap-3 py-20"
    >
      <p class="text-muted-foreground text-lg">没有符合条件的表情包</p>
      <Button type="primary" @click="router.push('/upload')">去上传</Button>
    </div>

    <!-- PC：网格布局 + 分页（右键菜单） -->
    <template v-if="isPc">
      <Dropdown :trigger="['contextmenu']">
        <div class="pc-grid select-none" @dragstart.prevent @mousedown="onGridMouseDown">
          <div
            v-for="item in items"
            :key="item.id"
            class="pc-card"
            :class="{ 'pc-card-selected': selectedIds.has(item.id) }"
            :data-id="item.id"
            @click="handleCardClick(item, $event)"
            @contextmenu="contextItem = item"
          >
            <div v-if="marqueeRect" class="pc-check" :class="{ 'pc-check-on': selectedIds.has(item.id) }">
              {{ selectedIds.has(item.id) ? '✓' : '' }}
            </div>
            <img
              :alt="item.originalName"
              class="pc-img pointer-events-none"
              decoding="async"
              draggable="false"
              loading="lazy"
              :src="item.thumbUrl"
            />
            <div class="pc-overlay">
              <span class="pc-meta">
                {{ item.category }} · {{ item.format.toUpperCase() }} ·
                {{ formatSize(item.size) }}
              </span>
              <span class="pc-copy-tip">
                {{ copyingId === item.id ? '复制中...' : '点击复制 · 右键管理' }}
              </span>
              <div v-if="item.tags.length" class="pc-tags">
                <span v-for="tag in item.tags" :key="tag" class="pc-tag">
                  {{ tag }}
                </span>
              </div>
            </div>
          </div>
        </div>
        <template #overlay>
          <Menu @click="onMenuClick">
            <MenuItem key="share">分享到微信/QQ</MenuItem>
            <MenuItem key="edit">编辑</MenuItem>
            <MenuItem key="open">打开原图</MenuItem>
            <MenuItem key="copy-link">复制原图链接</MenuItem>
            <MenuItem key="delete">
              <span class="text-red-500">删除</span>
            </MenuItem>
          </Menu>
        </template>
      </Dropdown>
      <div class="mt-5 flex justify-center">
        <Pagination
          v-model:current="page"
          v-model:page-size="pageSize"
          :page-size-options="['30', '50', '100']"
          :show-size-changer="true"
          :total="total"
        />
      </div>
    </template>

    <!-- 移动端：瀑布流 + 触底加载（长按同样呼出右键菜单） -->
    <template v-else>
      <Dropdown :trigger="['contextmenu']">
        <div class="mobile-waterfall">
          <div
            v-for="item in items"
            :key="item.id"
            class="mobile-card"
            :class="{ 'pc-card-selected': selectedIds.has(item.id) }"
            :data-id="item.id"
            @click="handleCardClick(item, $event)"
            @contextmenu="contextItem = item"
          >
            <div v-if="marqueeRect" class="pc-check" :class="{ 'pc-check-on': selectedIds.has(item.id) }">
              {{ selectedIds.has(item.id) ? '✓' : '' }}
            </div>
            <div class="mobile-img-wrap">
              <img
                :alt="item.originalName"
                class="mobile-img"
                decoding="async"
                loading="lazy"
                :src="item.thumbUrl"
              />
            </div>
            <div class="mobile-info">
              <span class="mobile-meta">
                {{ item.category }} · {{ item.format.toUpperCase() }} ·
                {{ formatSize(item.size) }}
              </span>
              <div v-if="item.tags.length" class="mobile-tags">
                <span v-for="tag in item.tags" :key="tag" class="mobile-tag">
                  {{ tag }}
                </span>
              </div>
              <Button
                :loading="sharingId === item.id"
                class="mobile-share"
                size="small"
                type="primary"
                @click.stop="handleShare(item)"
              >
                分享
              </Button>
            </div>
          </div>
        </div>
        <template #overlay>
          <Menu @click="onMenuClick">
            <MenuItem key="share">分享到微信/QQ</MenuItem>
            <MenuItem key="edit">编辑</MenuItem>
            <MenuItem key="open">打开原图</MenuItem>
            <MenuItem key="copy-link">复制原图链接</MenuItem>
            <MenuItem key="delete">
              <span class="text-red-500">删除</span>
            </MenuItem>
          </Menu>
        </template>
      </Dropdown>
      <div ref="sentinelRef" class="h-2" />
      <div class="text-muted-foreground py-4 text-center text-sm">
        <span v-if="loading">加载中...</span>
        <span v-else-if="!hasMore && items.length > 0">
          已加载全部 {{ items.length }} 张
        </span>
      </div>
    </template>

    <!-- 框选矩形 -->
    <div
      v-if="marqueeRect"
      class="marquee-rect"
      :class="{ 'marquee-rect-remove': marqueeRemove }"
      :style="{
        left: marqueeRect.x + 'px',
        top: marqueeRect.y + 'px',
        width: marqueeRect.w + 'px',
        height: marqueeRect.h + 'px',
      }"
    />

    <!-- 批量操作栏：有选中时出现 -->
    <Transition name="batch-bar">
      <div v-if="selectedIds.size > 0" class="batch-bar">
        <span class="text-sm">
          已选 <b>{{ selectedIds.size }}</b> 张
        </span>
        <span class="h-5 w-px bg-accent" />
        <Button :disabled="items.length === 0" size="small" @click="selectAllCurrent">
          全选本页
        </Button>
        <Button :disabled="items.length === 0" size="small" @click="invertSelection">
          反选
        </Button>
        <Button :disabled="selectedIds.size === 0" size="small" @click="clearSelection">
          清空
        </Button>
        <Button
          :disabled="selectedIds.size === 0"
          size="small"
          type="primary"
          @click="batchEditOpen = true"
        >
          编辑
        </Button>
        <Button
          :disabled="selectedIds.size === 0"
          danger
          size="small"
          @click="handleBatchDelete"
        >
          删除
        </Button>
      </div>
    </Transition>

    <!-- 批量编辑弹窗 -->
    <BatchEditModal
      v-model:open="batchEditOpen"
      :categories="categories"
      :selected-count="selectedIds.size"
      :selected-ids="[...selectedIds]"
      @updated="onBatchUpdated"
    />

    <!-- 编辑弹窗 -->
    <EditImageModal
      v-model:open="editOpen"
      :categories="categories"
      :image="editing"
      @deleted="onDeleted"
      @saved="onSaved"
    />

    <!-- 分享兜底弹窗：微信 / QQ 内置浏览器不支持调起系统分享时 -->
    <Modal
      :footer="null"
      :open="!!previewItem"
      title="分享表情包"
      @cancel="previewItem = null"
    >
      <template v-if="previewItem">
        <img
          :alt="previewItem.originalName"
          class="mx-auto max-h-[55vh] object-contain"
          :src="previewItem.url"
        />
        <p class="text-muted-foreground mt-3 text-center text-sm">
          {{ shareEnvHint }}
        </p>
        <div class="mt-3 flex flex-wrap justify-center gap-2">
          <Button type="primary" @click="savePreviewImage(previewItem)">
            保存到手机
          </Button>
          <Button @click="copyPreviewImage(previewItem)">复制图片</Button>
          <Button @click="copyPreviewLink(previewItem)">复制链接</Button>
        </div>
      </template>
    </Modal>
  </div>
</template>

<style scoped>
.type-chip {
  border-radius: 999px;
  padding: 4px 12px;
  font-size: 13px;
  border: 1px solid hsl(var(--border));
  color: hsl(var(--foreground) / 80%);
  background: transparent;
  cursor: pointer;
  transition: all 0.2s;
}

.type-chip:hover {
  border-color: hsl(var(--primary));
  color: hsl(var(--primary));
}

.type-chip-active {
  background: hsl(var(--primary));
  border-color: hsl(var(--primary));
  color: hsl(var(--primary-foreground));
}

.tag-chip {
  border-radius: 999px;
  padding: 4px 12px;
  font-size: 13px;
  border: 1px solid hsl(var(--border));
  color: hsl(var(--foreground) / 80%);
  background: transparent;
  cursor: pointer;
  transition: all 0.2s;
}

.tag-chip:hover {
  border-color: hsl(var(--primary));
  color: hsl(var(--primary));
}

.tag-chip-active {
  background: hsl(var(--primary) / 15%);
  border-color: hsl(var(--primary));
  color: hsl(var(--primary));
}

/* ---------- 批量模式 ---------- */
.pc-card-selected {
  outline: 2px solid hsl(var(--primary));
  outline-offset: -2px;
}

.pc-check {
  position: absolute;
  top: 6px;
  right: 6px;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 999px;
  border: 1.5px solid rgb(255 255 255 / 90%);
  background: rgb(0 0 0 / 35%);
  color: #fff;
  font-size: 13px;
  backdrop-filter: blur(2px);
}

.pc-check-on {
  background: hsl(var(--primary));
  border-color: hsl(var(--primary));
}

.marquee-rect {
  position: fixed;
  z-index: 100;
  border: 2px solid hsl(var(--primary));
  background: hsl(var(--primary) / 15%);
  border-radius: 4px;
  pointer-events: none;
}

.marquee-rect-remove {
  border-style: dashed;
  border-color: hsl(var(--destructive));
  background: hsl(var(--destructive) / 10%);
}

.batch-bar {
  position: fixed;
  bottom: 24px;
  left: 50%;
  z-index: 90;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  border-radius: 12px;
  border: 1px solid hsl(var(--border));
  background: hsl(var(--card));
  box-shadow: 0 6px 24px rgb(0 0 0 / 25%);
  transform: translateX(-50%);
}

.batch-bar-enter-active,
.batch-bar-leave-active {
  transition: all 0.25s ease;
}

.batch-bar-enter-from,
.batch-bar-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(16px);
}

/* ---------- PC 网格 ---------- */
.pc-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
  gap: 14px;
}

.pc-card {
  position: relative;
  height: 170px;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid hsl(var(--border));
  background: repeating-conic-gradient(
      hsl(var(--accent)) 0% 25%,
      transparent 0% 50%
    )
    50% / 16px 16px;
  cursor: pointer;
}

.pc-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.pc-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  padding: 8px 10px;
  background: linear-gradient(to top, rgb(0 0 0 / 70%), transparent 55%);
  opacity: 0;
  transition: opacity 0.2s;
}

.pc-card:hover .pc-overlay {
  opacity: 1;
}

.pc-meta {
  font-size: 12px;
  color: rgb(255 255 255 / 85%);
}

.pc-copy-tip {
  font-size: 13px;
  font-weight: 500;
  color: #fff;
}

.pc-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}

.pc-tag {
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 999px;
  background: rgb(255 255 255 / 20%);
  color: #fff;
  backdrop-filter: blur(4px);
}

/* ---------- 移动端瀑布流（一行 4 张） ---------- */
.mobile-waterfall {
  column-count: 4;
  column-gap: 6px;
}

.mobile-card {
  position: relative;
  break-inside: avoid;
  margin-bottom: 6px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid hsl(var(--border));
  background: hsl(var(--card));
  cursor: pointer;
}

.mobile-img-wrap {
  position: relative;
}

.mobile-img {
  width: 100%;
  display: block;
}

.mobile-share {
  display: block;
  width: 100%;
  height: 24px;
  margin-top: 4px;
  font-size: 11px;
}

.mobile-info {
  padding: 4px 5px 5px;
}

.mobile-meta {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 10px;
  color: hsl(var(--foreground) / 55%);
}

.mobile-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
  margin-top: 3px;
}

.mobile-tag {
  font-size: 9px;
  padding: 0 5px;
  border-radius: 999px;
  background: hsl(var(--accent));
  color: hsl(var(--foreground) / 75%);
}
</style>
