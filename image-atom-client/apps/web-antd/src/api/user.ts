import type { UserInfo } from '@vben/types';

import { requestClient } from '#/api/request';

/**
 * 获取用户信息
 */
export async function getUserInfoApi() {
  return requestClient.get<UserInfo>('/user/info');
}

/**
 * 上传头像（multipart，服务端压缩后存 uploads/avatars/）
 */
export async function uploadAvatarApi(data: FormData) {
  return requestClient.post<{ avatar: string }>('/user/avatar', data, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
}

/**
 * 修改密码
 */
export async function changePasswordApi(data: {
  newPassword: string;
  oldPassword: string;
}) {
  return requestClient.put('/user/password', data);
}
