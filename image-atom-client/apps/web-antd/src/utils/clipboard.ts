/** 图片复制到剪贴板：统一转为 PNG 格式（GIF 取首帧、SVG 栅格化），
 * 浏览器不支持时降级为复制图片链接。 */
function toPngBlob(blob: Blob): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const objectUrl = URL.createObjectURL(blob);
    const img = new Image();
    img.onload = () => {
      try {
        const width = img.naturalWidth || 300;
        const height = img.naturalHeight || 300;
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext('2d');
        if (!ctx) throw new Error('canvas 不可用');
        ctx.drawImage(img, 0, 0, width, height);
        canvas.toBlob(
          (png) => {
            URL.revokeObjectURL(objectUrl);
            png ? resolve(png) : reject(new Error('转换 PNG 失败'));
          },
          'image/png',
        );
      } catch (error) {
        URL.revokeObjectURL(objectUrl);
        reject(error);
      }
    };
    img.onerror = () => {
      URL.revokeObjectURL(objectUrl);
      reject(new Error('图片解码失败'));
    };
    img.src = objectUrl;
  });
}

export async function copyImageToClipboard(url: string): Promise<void> {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error('图片获取失败');
  const blob = await resp.blob();
  const png = blob.type === 'image/png' ? blob : await toPngBlob(blob);
  await navigator.clipboard.write([new ClipboardItem({ 'image/png': png })]);
}

export async function copyImageWithFallback(url: string): Promise<string> {
  try {
    await copyImageToClipboard(url);
    return '已复制到剪贴板';
  } catch {
    try {
      await navigator.clipboard.writeText(url);
      return '当前环境不支持复制图片，已复制图片链接';
    } catch {
      throw new Error('复制失败');
    }
  }
}
