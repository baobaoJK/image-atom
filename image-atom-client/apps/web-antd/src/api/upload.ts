import type { ImageItem } from '#/api/gallery';

import { requestClient } from '#/api/request';

export interface UploadInitResult {
  instant: boolean;
  image?: ImageItem;
  chunkSize?: number;
  uploadId?: string;
  uploadedChunks?: number[];
}

export interface UploadCompleteResult {
  instant: boolean;
  image: ImageItem;
}

/**
 * 初始化上传：命中 md5 直接秒传；否则返回服务端已有分片（断点续传）
 */
export async function initUploadApi(data: {
  filename: string;
  md5: string;
  size: number;
  totalChunks: number;
}) {
  return requestClient.post<UploadInitResult>('/upload/init', data);
}

/**
 * 上传单个分片（multipart）。
 * 必须显式声明 multipart：requestClient 默认 application/json，
 * axios 会把 FormData 序列化成 JSON，导致后端取不到表单字段。
 */
export async function uploadChunkApi(data: FormData) {
  return requestClient.post<{ index: number; uploadedChunks: number[] }>(
    '/upload/chunk',
    data,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  );
}

/**
 * 合并分片入库（每张图可带自己的分类与标签）
 */
export async function completeUploadApi(data: {
  category: string;
  filename: string;
  md5: string;
  size: number;
  tags: string[];
}) {
  return requestClient.post<UploadCompleteResult>('/upload/complete', data);
}

/**
 * 取消上传，清理临时分片
 */
export async function abortUploadApi(md5: string) {
  return requestClient.post('/upload/abort', { md5 });
}
