import { requestClient } from '#/api/request';

/** 表情包条目 */
export interface ImageItem {
  category: string;
  createdAt: string;
  format: string;
  height: number;
  id: number;
  imageType: 'animated' | 'static';
  md5: string;
  originalName: string;
  size: number;
  tags: string[];
  thumbUrl: string;
  url: string;
  width: number;
}

export interface ImageListResult {
  hasMore: boolean;
  items: ImageItem[];
  page: number;
  pageSize: number;
  supportedFormats: string[];
  total: number;
}

export interface TagItem {
  count: number;
  id: number;
  name: string;
}

export interface CategoryItem {
  count: number;
  id: number;
  name: string;
}

export interface ImageStats {
  diskUsage: number;
  images: number;
  originals: number;
  thumbnails: number;
  typeCounts: {
    animated: number;
    static: number;
  };
}

/**
 * 仪表盘统计：图片数 / 磁盘文件数 / 占用空间 / 类型分布
 */
export async function getStatsApi() {
  return requestClient.get<ImageStats>('/image/stats');
}

/**
 * 分页获取表情包列表，可按标签 / 分类 / 图片类型 / 名字关键词筛选
 */
export async function listImagesApi(params: {
  category?: string;
  page: number;
  pageSize: number;
  search?: string;
  tags?: string;
  type?: '' | 'animated' | 'static';
}) {
  return requestClient.get<ImageListResult>('/image/list', { params });
}

/**
 * 标签及使用数量；可按分类 / 图片类型级联过滤
 */
export async function listTagsApi(category?: string, type?: '' | 'animated' | 'static') {
  return requestClient.get<TagItem[]>('/image/tags', {
    params: { category: category || undefined, type: type || undefined },
  });
}

/**
 * 全部分类及数量（用于上传时选择、图库筛选）
 */
export async function listCategoriesApi() {
  return requestClient.get<CategoryItem[]>('/image/categories');
}

/**
 * 编辑图片：名字 / 分类 / 标签（可只传其中一部分）
 */
export async function updateImageApi(
  id: number,
  data: { category?: string; name?: string; tags?: string[] },
) {
  return requestClient.put<ImageItem>(`/image/${id}`, data);
}

/**
 * 删除图片（同时删除原图和缩略图文件）
 */
export async function deleteImageApi(id: number) {
  return requestClient.delete(`/image/${id}`);
}

/**
 * 批量编辑：设置分类 / 追加标签
 */
export async function batchUpdateImageApi(data: {
  addTags?: string[];
  category?: string;
  ids: number[];
}) {
  return requestClient.put<{ updated: number }>('/image/batch', data);
}

/**
 * 批量删除（同时删除原图和缩略图文件）
 */
export async function batchDeleteImageApi(ids: number[]) {
  return requestClient.post<{ deleted: number }>('/image/batch-delete', { ids });
}
