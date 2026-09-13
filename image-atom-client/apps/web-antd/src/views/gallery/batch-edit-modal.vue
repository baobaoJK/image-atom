<script lang="ts" setup>
import type { CategoryItem } from '#/api/gallery';

import { computed, ref, watch } from 'vue';

import { AutoComplete, Modal, Select, message } from 'ant-design-vue';

import { batchUpdateImageApi } from '#/api/gallery';

defineOptions({ name: 'BatchEditModal' });

const props = defineProps<{
  categories: CategoryItem[];
  open: boolean;
  selectedCount: number;
  selectedIds: number[];
}>();

const emit = defineEmits<{
  'update:open': [open: boolean];
  updated: [];
}>();

const saving = ref(false);
const form = ref({ category: '', tags: [] as string[] });

const categoryOptions = computed(() =>
  props.categories.map((c) => ({
    label: `${c.name} (${c.count})`,
    value: c.name,
  })),
);

watch(
  () => props.open,
  (open) => {
    if (open) {
      form.value = { category: '', tags: [] };
    }
  },
);

function close() {
  emit('update:open', false);
}

async function handleSave() {
  const { category, tags } = form.value;
  // 两项都为空 = 没有要改的内容
  if (!category.trim() && tags.length === 0) {
    message.warning('请选择新分类或输入要添加的标签');
    return;
  }
  saving.value = true;
  try {
    await batchUpdateImageApi({
      addTags: tags.map((tag) => tag.trim()).filter(Boolean),
      category: category.trim() || undefined,
      ids: props.selectedIds,
    });
    message.success(`已更新所选图片`);
    emit('updated');
    close();
  } catch {
    message.error('批量编辑失败');
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <Modal
    :confirm-loading="saving"
    ok-text="应用到所选图片"
    :open="open"
    title="批量编辑"
    @cancel="close"
    @ok="handleSave"
  >
    <div class="flex flex-col gap-4">
      <div class="text-muted-foreground text-sm">
        将对选中的 <b>{{ selectedCount }}</b> 张图片执行以下操作：
      </div>
      <div class="flex flex-col gap-1">
        <span class="text-sm">分类文件夹（留空则不修改分类）</span>
        <AutoComplete
          v-model:value="form.category"
          :options="categoryOptions"
          allow-clear
          placeholder="选择已有分类，或输入新建"
        />
      </div>
      <div class="flex flex-col gap-1">
        <span class="text-sm">添加标签（追加到每张图的已有标签上）</span>
        <Select
          v-model:value="form.tags"
          mode="tags"
          placeholder="例如：搞笑、吃东西"
        />
      </div>
      <div class="text-muted-foreground text-xs">
        · 分类会直接覆盖为所选值 · 标签是追加，不会移除图片已有的标签
      </div>
    </div>
  </Modal>
</template>
