"""图片真实格式检测。

仅凭后缀名不可靠（gif 可能被命名为 jpg/png），统一通过
magic bytes 判断真实格式；SVG 通过文本特征识别。
"""
SUPPORTED_FORMATS = ('gif', 'jpeg', 'png', 'webp', 'svg')

_PNG = b'\x89PNG\r\n\x1a\n'
_JPEG = b'\xff\xd8\xff'
_WEBP = b'RIFF'


def detect_format(head: bytes, full: bytes | None = None) -> str | None:
    """返回真实格式（gif/jpeg/png/webp/svg），不支持返回 None。"""
    if head.startswith(b'GIF87a') or head.startswith(b'GIF89a'):
        return 'gif'
    if head.startswith(_PNG):
        return 'png'
    if head.startswith(_JPEG):
        return 'jpeg'
    if head.startswith(_WEBP) and head[8:12] == b'WEBP':
        return 'webp'
    # SVG：可能是文本或 gzip 压缩的文本
    sample = full if full is not None else head
    if _looks_like_svg(sample):
        return 'svg'
    return None


def _looks_like_svg(data: bytes) -> bool:
    if not data:
        return False
    if data[:2] == b'\x1f\x8b':
        try:
            import gzip

            data = gzip.decompress(data)
        except OSError:
            return False
    text = data[:4096].decode('utf-8', errors='ignore').lstrip()
    return text.startswith('<?xml') and '<svg' in text[:4096] or text.startswith('<svg')


def format_extension(fmt: str) -> str:
    return 'jpg' if fmt == 'jpeg' else fmt


# 供 Pillow 打开后的格式名 -> 内部格式名
PILLOW_FORMAT_MAP = {'GIF': 'gif', 'JPEG': 'jpeg', 'PNG': 'png', 'WEBP': 'webp'}


def head_bytes(file_storage, read_size: int = 32) -> bytes:
    pos = file_storage.tell()
    head = file_storage.read(read_size)
    file_storage.seek(pos)
    return head
