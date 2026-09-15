<script lang="ts" setup>
import type { ImageStats } from '#/api/gallery';

import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';

import { Button, Card } from 'ant-design-vue';

import { getStatsApi } from '#/api/gallery';

defineOptions({ name: 'Dashboard' });

const stats = ref<null | ImageStats>(null);
const loading = ref(true);
const router = useRouter();

function formatSize(size: number): string {
  if (size >= 1024 * 1024 * 1024) {
    return `${(size / 1024 / 1024 / 1024).toFixed(2)} GB`;
  }
  if (size >= 1024 * 1024) {
    return `${(size / 1024 / 1024).toFixed(1)} MB`;
  }
  return `${Math.max(1, Math.round(size / 1024))} KB`;
}

async function loadStats() {
  loading.value = true;
  try {
    stats.value = await getStatsApi();
  } finally {
    loading.value = false;
  }
}

const cards = [
  { accent: '#4a90d9', icon: '🖼️', key: 'images', label: '图片总数' },
  { accent: '#2ecc71', icon: '🗃️', key: 'originals', label: '原图' },
  { accent: '#f39c12', icon: '🗂️', key: 'thumbnails', label: '缩略图' },
  { accent: '#9b59b6', icon: '💾', key: 'diskUsage', label: '磁盘占用' },
] as const;

onMounted(loadStats);
</script>

<template>
  <div class="p-4 md:p-5">
    <div class="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <Card v-for="card in cards" :key="card.key" :loading="loading" class="stat-card">
        <div class="flex items-center gap-4">
          <div
            class="flex size-12 shrink-0 items-center justify-center rounded-xl text-2xl"
            :style="{ background: `${card.accent}22` }"
          >
            {{ card.icon }}
          </div>
          <div class="min-w-0">
            <div class="truncate text-2xl font-semibold">
              <template v-if="stats">
                {{
                  card.key === 'diskUsage'
                    ? formatSize(stats.diskUsage)
                    : stats[card.key]
                }}
              </template>
              <span v-else>--</span>
            </div>
            <div class="text-muted-foreground mt-1 text-xs">{{ card.label }}</div>
          </div>
        </div>
        <div
          class="mt-3 h-1 w-10 rounded"
          :style="{ background: card.accent }"
        />
      </Card>
    </div>

    <div class="mt-4 flex flex-wrap items-center gap-3">
      <Button size="small" @click="loadStats">刷新统计</Button>
      <Button size="small" @click="router.push('/upload')">去上传</Button>
      <Button size="small" @click="router.push('/gallery')">查看图库</Button>
    </div>
  </div>
</template>

<style scoped>
.stat-card :deep(.ant-card-body) {
  padding: 18px;
}
</style>
