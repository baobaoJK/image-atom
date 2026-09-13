/** 移动端分享：优先调起系统分享面板（微信 / QQ 在面板里），把图片作为
 * 文件直接分享进聊天；内置浏览器等不支持 Web Share API 时返回
 * unsupported，由调用方展示"长按图片保存"的预览兜底。 */

interface ShareOptions {
  files?: File[];
  text?: string;
  title?: string;
  url?: string;
}

interface ShareApi {
  canShare?: (data: ShareOptions) => boolean;
  share?: (data: ShareOptions) => Promise<void>;
}

const EXT_BY_MIME: Record<string, string> = {
  'image/gif': 'gif',
  'image/jpeg': 'jpg',
  'image/png': 'png',
  'image/svg+xml': 'svg',
  'image/webp': 'webp',
};

/** 标准类型里 share 是必有方法，但 Electron / 微信内置浏览器运行时可能不存在，
 * 这里统一收口做能力检测。 */
function getShareApi(): ShareApi {
  return navigator as unknown as ShareApi;
}

/** 当前浏览器的分享环境 */
export type ShareEnv = 'qq' | 'unsupported' | 'webshare' | 'wechat';

export function detectShareEnv(): ShareEnv {
  const ua = navigator.userAgent;
  // 微信 / QQ 内置浏览器会禁用 Web Share API，只能走长按/保存
  if (/MicroMessenger/i.test(ua)) return 'wechat';
  if (/QQ\//i.test(ua)) return 'qq';
  if (getShareApi().share) return 'webshare';
  return 'unsupported';
}

async function fetchImageFile(url: string, name: string): Promise<File> {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error('图片获取失败');
  const blob = await resp.blob();
  const ext = EXT_BY_MIME[blob.type] ?? 'png';
  const fileName = name.toLowerCase().endsWith(`.${ext}`)
    ? name
    : `${name || 'meme'}.${ext}`;
  return new File([blob], fileName, { type: blob.type || 'image/png' });
}

/** 保存图片到手机（触发浏览器下载） */
export async function saveImageToPhone(url: string, name: string) {
  const file = await fetchImageFile(url, name);
  const objectUrl = URL.createObjectURL(file);
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = file.name;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(objectUrl), 3000);
}

export type ShareResult = 'file-shared' | 'link-shared' | 'unsupported';

/** 返回 unsupported 时调用方应展示长按保存的预览兜底 */
export async function shareImage(
  url: string,
  name: string,
  title: string,
): Promise<ShareResult> {
  const api = getShareApi();
  if (!api.share) return 'unsupported';

  const file = await fetchImageFile(url, name);

  // 系统分享面板支持图片文件：直接把图片分享到微信 / QQ
  if (api.canShare?.({ files: [file] })) {
    await api.share({ files: [file], title });
    return 'file-shared';
  }

  // 面板不支持文件时退化为分享链接
  const linkData: ShareOptions = {
    text: title,
    title,
    url: `${location.origin}${url}`,
  };
  if (api.canShare?.(linkData) !== false) {
    await api.share(linkData);
    return 'link-shared';
  }
  return 'unsupported';
}
