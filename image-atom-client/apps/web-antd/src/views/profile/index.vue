<script lang="ts" setup>
import { computed, reactive, ref } from 'vue';

import { useUserStore } from '@vben/stores';
import { preferences } from '@vben/preferences';

import { Button, Card, Input, Upload, message } from 'ant-design-vue';

import { changePasswordApi, uploadAvatarApi } from '#/api/user';
import { useAuthStore } from '#/store';

defineOptions({ name: 'Profile' });

const InputPassword = Input.Password;

const userStore = useUserStore();
const authStore = useAuthStore();

const avatar = computed(
  () => userStore.userInfo?.avatar || preferences.app.defaultAvatar,
);
const uploading = ref(false);

// 密码表单
const passwordForm = reactive({
  confirm: '',
  newPassword: '',
  oldPassword: '',
});
const passwordSaving = ref(false);

async function beforeAvatarUpload(file: File): Promise<boolean> {
  const extOk = ['gif', 'jpeg', 'jpg', 'png', 'webp'].includes(
    file.name.split('.').pop()?.toLowerCase() ?? '',
  );
  if (!extOk) {
    message.warning('仅支持 JPG / PNG / WEBP / GIF 格式头像');
    return false;
  }
  if (file.size > 5 * 1024 * 1024) {
    message.warning('头像图片不能超过 5MB');
    return false;
  }

  uploading.value = true;
  try {
    const form = new FormData();
    form.append('file', file);
    await uploadAvatarApi(form);
    // 重新拉取用户信息，右上角头像即时更新
    await authStore.fetchUserInfo();
    message.success('头像已更新');
  } catch {
    message.error('头像上传失败');
  } finally {
    uploading.value = false;
  }
  return false; // 关闭 antd 默认上传
}

async function handleChangePassword() {
  const { confirm: confirmPwd, newPassword, oldPassword } = passwordForm;
  if (!oldPassword || !newPassword || !confirmPwd) {
    message.warning('请填写完整');
    return;
  }
  if (newPassword.length < 6) {
    message.warning('新密码至少 6 位');
    return;
  }
  if (newPassword !== confirmPwd) {
    message.warning('两次输入的新密码不一致');
    return;
  }

  passwordSaving.value = true;
  try {
    await changePasswordApi({ newPassword, oldPassword });
    message.success('密码已修改');
    passwordForm.oldPassword = '';
    passwordForm.newPassword = '';
    passwordForm.confirm = '';
  } catch {
    // 错误信息由请求拦截器统一提示（如"原密码错误"）
  } finally {
    passwordSaving.value = false;
  }
}
</script>

<template>
  <div class="mx-auto max-w-2xl p-4 md:p-5">
    <!-- 账号信息 -->
    <Card title="账号信息">
      <div class="flex items-center gap-5">
        <div class="flex flex-col items-center gap-2">
          <img
            :alt="userStore.userInfo?.realName"
            class="size-20 rounded-full border object-cover"
            :src="avatar"
          />
          <Upload
            :before-upload="beforeAvatarUpload"
            :disabled="uploading"
            :show-upload-list="false"
            accept=".gif,.jpeg,.jpg,.png,.webp"
          >
            <Button :loading="uploading" size="small">
              {{ uploading ? '上传中' : '更换头像' }}
            </Button>
          </Upload>
        </div>
        <div class="flex flex-col gap-1">
          <div class="text-lg font-medium">
            {{ userStore.userInfo?.realName }}
          </div>
          <div class="text-muted-foreground text-sm">
            用户名：{{ userStore.userInfo?.username }}
          </div>
          <div class="text-muted-foreground text-xs">
            {{
              userStore.userInfo?.createdAt
                ? `创建于 ${userStore.userInfo.createdAt.slice(0, 10)}`
                : ''
            }}
          </div>
        </div>
      </div>
      <div class="text-muted-foreground mt-3 text-xs">
        头像支持 JPG / PNG / WEBP / GIF，最大 5MB；上传后自动压缩到 512px，单独存放在
        server 的 uploads/avatars 目录
      </div>
    </Card>

    <!-- 修改密码 -->
    <Card class="mt-4" title="修改密码">
      <div class="flex max-w-sm flex-col gap-3">
        <div class="flex flex-col gap-1">
          <span class="text-sm">原密码</span>
          <InputPassword
            v-model:value="passwordForm.oldPassword"
            autocomplete="current-password"
            placeholder="请输入原密码"
          />
        </div>
        <div class="flex flex-col gap-1">
          <span class="text-sm">新密码（至少 6 位）</span>
          <InputPassword
            v-model:value="passwordForm.newPassword"
            autocomplete="new-password"
            placeholder="请输入新密码"
          />
        </div>
        <div class="flex flex-col gap-1">
          <span class="text-sm">确认新密码</span>
          <InputPassword
            v-model:value="passwordForm.confirm"
            autocomplete="new-password"
            placeholder="请再次输入新密码"
          />
        </div>
        <Button
          :loading="passwordSaving"
          class="mt-1 self-start"
          type="primary"
          @click="handleChangePassword"
        >
          保存新密码
        </Button>
      </div>
    </Card>
  </div>
</template>
