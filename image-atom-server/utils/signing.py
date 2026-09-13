"""图片 URL 签名。

图库中的 <img> 标签无法携带 Authorization 请求头，因此图片文件
URL 采用 HMAC 签名（类似 S3 预签名 URL）：

- 签名 URL 只会通过需要 JWT 鉴权的列表接口下发，未登录用户拿不到；
- 直接访问 /api/image/file/... 需要携带有效签名，否则一律 401；
- 签名绑定具体文件路径 + 过期时间，无法伪造或越权访问其他文件。
"""
import hashlib
import hmac
import time
from urllib.parse import quote

from flask import current_app

# 签名有效期：30 天，兼顾浏览器长缓存与泄露链接的失效时间
SIGN_EXPIRES_SECONDS = 30 * 24 * 3600


def _secret() -> str:
    return current_app.config['SECRET_KEY']


def _sign(path: str, expires: int) -> str:
    msg = f'{path}:{expires}'.encode('utf-8')
    return hmac.new(_secret().encode('utf-8'), msg, hashlib.sha256).hexdigest()


def signed_image_url(path: str, expires_seconds: int = SIGN_EXPIRES_SECONDS) -> str:
    expires = int(time.time()) + expires_seconds
    signature = _sign(path, expires)
    quoted = quote(path)
    return f'/api/image/file/{quoted}?e={expires}&s={signature}'


def verify_image_signature(path: str, expires: str | int, signature: str) -> bool:
    try:
        expires_int = int(expires)
    except (TypeError, ValueError):
        return False
    if expires_int < int(time.time()):
        return False
    expected = _sign(path, expires_int)
    return hmac.compare_digest(expected, signature or '')
