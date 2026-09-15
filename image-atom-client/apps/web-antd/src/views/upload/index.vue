<script lang="ts" setup>
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';

import {
  Alert,
  AutoComplete,
  Button,
  Progress,
  Select,
  UploadDragger,
  message,
} from 'ant-design-vue';
import SparkMD5 from 'spark-md5';

import type { ImageItem } from '#/api/gallery';
import { listCategoriesApi } from '#/api/gallery';
import { completeUploadApi, initUploadApi, uploadChunkApi } from '#/api/upload';

defineOptions({ name: 'UploadImage' });

const CHUNK_SIZE = 4 * 1024 * 1024; // 与后端 init 返回的分片大小一致
const HASH_SLICE = 2 * 1024 * 1024;
const CONCURRENCY = 3;
const ALLOWED_EXTENSIONS = ['gif', 'jpeg', 'jpg', 'png', 'svg', 'webp'];

type QueueStatus =
    | 'done'
    | 'exists'
    | 'failed'
    | 'hashing'
    | 'uploading'
    | 'waiting';

interface QueueItem {
  error?: string;
  file: File;
  md5?: string;
  name: string;
  /** 本地预览地址：入队即生成，未上传也能看清是哪张图 */
  previewUrl: string;
  /** 每张图自己的标签 */
  tags: string[];
  progress: number;
  result?: ImageItem;
  size: number;
  status: QueueStatus;
  uid: number;
}

const router = useRouter();
const queue = ref<QueueItem[]>([]);
const folder = ref('');
const categoryOptions = ref<{ value: string }[]>([]);
const uploading = ref(false);
let uidSeed = 1;

const doneCount = computed(
  () => queue.value.filter((item) => item.status === 'done').length,
);
const existsCount = computed(
  () => queue.value.filter((item) => item.status === 'exists').length,
);
const failedCount = computed(
  () => queue.value.filter((item) => item.status === 'failed').length,
);
const pendingCount = computed(
  () => queue.value.filter((item) => item.status === 'waiting').length,
);

onMounted(async () => {
  const categories = await listCategoriesApi();
  categoryOptions.value = categories.map((c) => ({ value: c.name }));
});

function beforeUpload(file: File): boolean {
  const ext = file.name.split('.').pop()?.toLowerCase() ?? '';
  if (!ALLOWED_EXTENSIONS.includes(ext)) {
    message.warning(
      `不支持的格式 .${ext}，仅支持 JPG / PNG / WEBP / GIF / SVG`,
    );
    return false;
  }
  if (queue.value.some((item) => item.file === file)) return false;
  queue.value.push({
    file,
    name: file.name,
    previewUrl: URL.createObjectURL(file),
    progress: 0,
    size: file.size,
    status: 'waiting',
    tags: [],
    uid: uidSeed++,
  });
  return false; // 关闭 antd 默认上传，加入队列后点"开始上传"
}

function removeItem(uid: number) {
  if (uploading.value) return;
  const item = queue.value.find((entry) => entry.uid === uid);
  if (item) URL.revokeObjectURL(item.previewUrl);
  queue.value = queue.value.filter((entry) => entry.uid !== uid);
}

async function startUpload() {
  if (uploading.value || pendingCount.value + failedCount.value === 0) return;
  uploading.value = true;
  try {
    for (const item of queue.value) {
      if (item.status === 'done' || item.status === 'exists') continue;
      await uploadItem(item).catch((error) => {
        item.status = 'failed';
        item.error = error?.message ?? '上传失败';
      });
    }
  } finally {
    uploading.value = false;
  }
}

async function md5OfFile(file: File): Promise<string> {
  const spark = new SparkMD5.ArrayBuffer();
  for (let offset = 0; offset < file.size; offset += HASH_SLICE) {
    const buffer = await file
      .slice(offset, offset + HASH_SLICE)
      .arrayBuffer();
    spark.append(buffer);
  }
  return spark.end();
}

async function runPool(
  indexes: number[],
  limit: number,
  fn: (index: number) => Promise<void>,
) {
  const pending = [...indexes];
  const workers = Array.from(
    { length: Math.min(limit, pending.length) },
    async () => {
      while (pending.length > 0) {
        const index = pending.shift();
        if (index !== undefined) await fn(index);
      }
    },
  );
  await Promise.all(workers);
}

async function uploadChunkWithRetry(
  md5: string,
  index: number,
  blob: Blob,
  retries = 2,
) {
  for (let attempt = 0; ; attempt++) {
    try {
      const form = new FormData();
      form.append('md5', md5);
      form.append('index', String(index));
      form.append('file', blob, `chunk-${index}`);
      await uploadChunkApi(form);
      return;
    } catch (error) {
      if (attempt >= retries) throw error;
      await new Promise((resolve) => setTimeout(resolve, 1000 * (attempt + 1)));
    }
  }
}

async function uploadItem(item: QueueItem) {
  item.status = 'hashing';
  if (!item.md5) item.md5 = await md5OfFile(item.file);

  const totalChunks = Math.max(1, Math.ceil(item.size / CHUNK_SIZE));
  const init = await initUploadApi({
    filename: item.name,
    md5: item.md5,
    size: item.size,
    totalChunks,
  });

  // 库里已有相同内容（md5 一致）：不重复上传，标记为已存在
  if (init.instant && init.image) {
    item.status = 'exists';
    item.result = init.image;
    item.progress = 100;
    return;
  }

  item.status = 'uploading';
  const received = new Set(init.uploadedChunks ?? []);
  const missing = [];
  for (let i = 0; i < totalChunks; i++) {
    if (!received.has(i)) missing.push(i);
  }
  let done = received.size;
  const report = () => {
    item.progress = Math.min(99, Math.round((done / totalChunks) * 100));
  };
  report();

  await runPool(missing, CONCURRENCY, async (index) => {
    const start = index * CHUNK_SIZE;
    await uploadChunkWithRetry(
      item.md5!,
      index,
      item.file.slice(start, start + CHUNK_SIZE),
    );
    done += 1;
    report();
  });

  const result = await completeUploadApi({
    category: folder.value.trim(),
    filename: item.name,
    md5: item.md5,
    size: item.size,
    tags: item.tags.map((tag) => tag.trim()).filter(Boolean),
  });
  item.progress = 100;
  item.status = 'done';
  item.result = result.image;
}

async function retryItem(item: QueueItem) {
  item.status = 'hashing';
  item.error = undefined;
  // md5 已缓存、服务端分片仍在，重试只会补传缺失部分（断点续传）
  await uploadItem(item).catch((error) => {
    item.status = 'failed';
    item.error = error?.message ?? '上传失败';
  });
}

function statusText(item: QueueItem): string {
  switch (item.status) {
    case 'done': {
      return '上传完成';
    }
    case 'failed': {
      return item.error ?? '上传失败';
    }
    case 'hashing': {
      return '正在校验文件...';
    }
    case 'exists': {
      return '图片已存在，已跳过';
    }
    case 'uploading': {
      return `上传中 ${item.progress}%`;
    }
    default: {
      return '等待上传';
    }
  }
}

const statusColor: Record<
  QueueItem['status'],
  'active' | 'exception' | 'normal' | 'success'
> = {
  done: 'success',
  // 已存在：antd Progress 无 warning 状态，用 normal 表达
  exists: 'normal',
  failed: 'exception',
  hashing: 'normal',
  uploading: 'active',
  waiting: 'normal',
} as const;
</script>

<template>
  <div class="mx-auto max-w-3xl p-4 md:p-5">
    <Alert
      class="mb-4"
      message="支持的格式：JPG / PNG / WEBP / GIF / SVG"
      type="info"
      show-icon
    >
      <template #description>
        <div class="text-xs leading-5">
          <div>· 自动检测真实格式，GIF 被误存为 .jpg / .png 也能正确识别</div>
          <div>· 相同内容自动秒传；中断后重新上传自动续传，只补缺失部分</div>
        </div>
      </template>
    </Alert>

    <!-- 分类（文件夹）：整批共用，可选已有或输入新建 -->
    <div class="mb-4 flex flex-col gap-1">
      <span class="text-muted-foreground text-sm">
        分类文件夹（整批共用，可选已有或输入新建）
      </span>
      <AutoComplete
        v-model:value="folder"
        :options="categoryOptions"
        allow-clear
        placeholder="例如：猫和老鼠 / Doro / 咕咕嘎嘎 / 柴郡"
      />
    </div>

    <UploadDragger
      :before-upload="beforeUpload"
      :show-upload-list="false"
      accept=".gif,.jpeg,.jpg,.png,.svg,.webp"
      multiple
    >
      <p class="text-4xl">🖼️</p>
      <p class="mt-2 text-base font-medium">点击选择或拖拽图片到此处</p>
      <p class="text-muted-foreground mt-1 text-xs">
        可一次选择多张，添加后可为每张图单独设置标签
      </p>
    </UploadDragger>

    <!-- 上传队列 -->
    <div v-if="queue.length" class="mt-4 flex flex-col gap-2">
      <div v-for="item in queue" :key="item.uid" class="queue-item">
        <div class="flex items-center gap-3">
          <img
            :alt="item.name"
            class="h-12 w-12 shrink-0 rounded border object-cover"
            :src="item.previewUrl"
          />
          <div class="min-w-0 flex-1">
            <div class="truncate text-sm">{{ item.name }}</div>
            <div class="text-muted-foreground text-xs">
              {{ statusText(item) }}
            </div>
          </div>
          <Select
            v-model:value="item.tags"
            :disabled="
              item.status !== 'waiting' && item.status !== 'failed'
            "
            :max-tag-count="3"
            mode="tags"
            size="small"
            class="w-44"
            placeholder="单独标签（可选）"
          />
          <template v-if="item.status === 'waiting' || item.status === 'failed'">
            <Button
              v-if="item.status === 'failed'"
              size="small"
              @click="retryItem(item)"
            >
              重试
            </Button>
            <Button danger size="small" type="text" @click="removeItem(item.uid)">
              移除
            </Button>
          </template>
        </div>
        <Progress
          v-if="item.status === 'hashing' || item.status === 'uploading'"
          :percent="item.progress"
          :show-info="false"
          size="small"
          :status="statusColor[item.status]"
          class="mt-1"
        />
      </div>
    </div>

    <!-- 操作区 -->
    <div
      v-if="queue.length"
      class="mt-4 flex flex-wrap items-center justify-between gap-2"
    >
      <div class="text-muted-foreground text-sm">
        共 {{ queue.length }} 个，成功 {{ doneCount }} 个<template
          v-if="existsCount"
        >
          ，已存在 {{ existsCount }} 个</template
        ><template v-if="failedCount">
          ，失败 {{ failedCount }} 个</template
        >
        <a v-if="doneCount > 0" class="ml-2 cursor-pointer" @click="router.push('/gallery')">
          查看图库 →
        </a>
      </div>
      <Button
        :disabled="uploading || pendingCount + failedCount === 0"
        :loading="uploading"
        type="primary"
        @click="startUpload"
      >
        {{ uploading ? '上传中...' : '开始上传' }}
      </Button>
    </div>
  </div>
</template>

<style scoped>
.queue-item {
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid hsl(var(--border));
}
</style>
