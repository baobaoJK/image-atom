<script lang="ts" setup>
import type { CategoryItem, ImageItem } from '#/api/gallery';

import { computed, ref, watch } from 'vue';

import {
  AutoComplete,
  Button,
  Input,
  Modal,
  Select,
  message,
} from 'ant-design-vue';

import { deleteImageApi, updateImageApi } from '#/api/gallery';

defineOptions({ name: 'EditImageModal' });

const props = defineProps<{
  categories: CategoryItem[];
  image: null | ImageItem;
  open: boolean;
}>();

const emit = defineEmits<{
  deleted: [id: number];
  saved: [image: ImageItem];
  'update:open': [open: boolean];
}>();

const saving = ref(false);
const form = ref({ category: '', name: '', tags: [] as string[] });

const categoryOptions = computed(() =>
  props.categories.map((c) => ({
    label: `${c.name} (${c.count})`,
    value: c.name,
  })),
);

watch(
  () => props.open,
  (open) => {
    if (open && props.image) {
      form.value = {
        category: props.image.category === '未分类' ? '' : props.image.category,
        name: props.image.originalName,
        tags: [...props.image.tags],
      };
    }
  },
);

function close() {
  emit('update:open', false);
}

async function handleSave() {
  if (!props.image) return;
  const name = form.value.name.trim();
  if (!name) {
    message.warning('名字不能为空');
    return;
  }
  saving.value = true;
  try {
    const updated = await updateImageApi(props.image.id, {
      category: form.value.category.trim(),
      name,
      tags: form.value.tags.map((tag) => tag.trim()).filter(Boolean),
    });
    emit('saved', updated);
    message.success('已保存');
    close();
  } catch {
    message.error('保存失败');
  } finally {
    saving.value = false;
  }
}

function handleDelete() {
  const image = props.image;
  if (!image) return;
  Modal.confirm({
    content: '将同时删除原图和缩略图文件，且不可恢复。',
    okText: '删除',
    okType: 'danger',
    title: `确认删除「${image.originalName}」？`,
    async onOk() {
      try {
        await deleteImageApi(image.id);
        emit('deleted', image.id);
        message.success('已删除');
        close();
      } catch {
        message.error('删除失败');
      }
    },
  });
}
</script>

<template>
  <Modal
    :confirm-loading="saving"
    ok-text="保存"
    :open="open"
    title="编辑表情包"
    @cancel="close"
    @ok="handleSave"
  >
    <div v-if="image" class="flex flex-col gap-3">
      <div class="flex justify-center rounded bg-accent p-2">
        <img
          :alt="image.originalName"
          class="max-h-40 object-contain"
          :src="image.thumbUrl"
        />
      </div>
      <div class="flex flex-col gap-1">
        <span class="text-sm">名字</span>
        <Input v-model:value="form.name" placeholder="显示名称" />
      </div>
      <div class="flex flex-col gap-1">
        <span class="text-sm">分类文件夹（可选已有或输入新建）</span>
        <AutoComplete
          v-model:value="form.category"
          :options="categoryOptions"
          allow-clear
          placeholder="例如：猫和老鼠 / Doro"
        />
      </div>
      <div class="flex flex-col gap-1">
        <span class="text-sm">标签（可多个）</span>
        <Select
          v-model:value="form.tags"
          mode="tags"
          placeholder="例如：汤姆猫、搞笑、吃东西"
        />
      </div>
      <div class="text-muted-foreground text-xs">
        原格式 {{ image.format.toUpperCase() }} · {{ image.width }}×{{
          image.height
        }}
        · 上传于 {{ image.createdAt.slice(0, 10) }}
      </div>
    </div>
    <template #footer>
      <Button :danger="true" class="float-left" @click="handleDelete">
        删除
      </Button>
      <Button @click="close">取消</Button>
      <Button :loading="saving" type="primary" @click="handleSave">
        保存
      </Button>
    </template>
  </Modal>
</template>
