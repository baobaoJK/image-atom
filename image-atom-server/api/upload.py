"""分片上传接口：断点续传 + md5 秒传。

协议：
1. POST /api/upload/init   {md5, filename, size, totalChunks}
   - md5 已存在 => {instant: true, image: {...}}（秒传，客户端跳过上传）
   - 否则返回 {uploadId, chunkSize, uploadedChunks: [...]}；
     uploadedChunks 即断点续传：客户端只需补传缺失分片
2. POST /api/upload/chunk  multipart: md5, index, file（可并发，可重试）
3. POST /api/upload/complete {md5, filename, tags: [...]}
   合并分片 -> 检测真实格式 -> 生成缩略图 -> 入库
4. POST /api/upload/abort  {md5}  清理临时分片

分片以 md5 为键存放在 UPLOAD_FOLDER/.tmp/<md5>/<index>.part，
与文件名无关，因此同名/异名但内容相同的文件都能命中续传或秒传。
"""
import json
import os
import re
import shutil
import uuid as uuid_lib
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required
from PIL import Image as PILImage

from extensions import db
from models.image import Image, get_or_create_category, get_or_create_tags
from utils.format import detect_format, format_extension
from utils.response import fail, ok

upload_bp = Blueprint('upload', __name__)

MAX_CHUNK_SIZE = 8 * 1024 * 1024          # 单分片上限 8MB
MAX_TOTAL_SIZE = 200 * 1024 * 1024        # 单文件上限 200MB
MAX_CHUNKS = 5000
MD5_RE = re.compile(r'^[a-f0-9]{32}$')
# Pillow 能处理的格式；svg/gif 特殊处理
RASTER_FORMATS = {'gif', 'jpeg', 'png', 'webp'}
THUMB_MAX_SIDE = 480


def _tmp_dir(md5: str) -> str:
    return os.path.join(current_app.config['UPLOAD_FOLDER'], '.tmp', md5)


def _uploaded_chunks(md5: str) -> list[int]:
    tmp = _tmp_dir(md5)
    if not os.path.isdir(tmp):
        return []
    chunks = []
    for name in os.listdir(tmp):
        if name.endswith('.part'):
            try:
                chunks.append(int(name[:-5]))
            except ValueError:
                continue
    return sorted(chunks)


@upload_bp.post('/init')
@jwt_required()
def init_upload():
    payload = request.get_json(silent=True) or {}
    md5 = (payload.get('md5') or '').lower()
    size = payload.get('size') or 0
    total_chunks = payload.get('totalChunks') or 0

    if not MD5_RE.match(md5):
        return fail('非法的文件校验值')
    if not isinstance(size, int) or size <= 0 or size > MAX_TOTAL_SIZE:
        return fail(f'文件大小不合法（最大 {MAX_TOTAL_SIZE // 1024 // 1024}MB）')
    if not isinstance(total_chunks, int) or total_chunks <= 0 or total_chunks > MAX_CHUNKS:
        return fail('分片数量不合法')

    # 秒传：相同内容（md5 一致）的文件已存在，直接返回记录
    existing = db.session.query(Image).filter_by(md5=md5).first()
    if existing is not None:
        return ok({'instant': True, 'image': existing.to_dict()})

    # 断点续传：返回服务端已收到的分片，客户端只补缺失部分
    os.makedirs(_tmp_dir(md5), exist_ok=True)
    return ok({
        'instant': False,
        'uploadId': md5,
        'chunkSize': 4 * 1024 * 1024,
        'uploadedChunks': _uploaded_chunks(md5),
    })


@upload_bp.post('/chunk')
@jwt_required()
def upload_chunk():
    md5 = (request.form.get('md5') or '').lower()
    index_raw = request.form.get('index') or ''
    chunk = request.files.get('file')

    if not MD5_RE.match(md5):
        return fail('非法的文件校验值')
    if not index_raw.isdigit() or int(index_raw) >= MAX_CHUNKS:
        return fail('分片序号不合法')
    if chunk is None:
        return fail('分片内容为空')
    if not chunk.filename and (chunk.content_length or 0) == 0:
        return fail('分片内容为空')
    chunk.seek(0, os.SEEK_END)
    chunk_size = chunk.tell()
    if chunk_size > MAX_CHUNK_SIZE:
        return fail('分片过大')
    chunk.seek(0)

    tmp = _tmp_dir(md5)
    if not os.path.isdir(tmp):
        # init 丢失（如服务重启清理）时自动重建，保证续传可用
        os.makedirs(tmp, exist_ok=True)
    chunk.save(os.path.join(tmp, f'{int(index_raw)}.part'))
    return ok({'index': int(index_raw), 'uploadedChunks': _uploaded_chunks(md5)})


def _assemble(md5: str, total_size: int) -> tuple[str, bytes, str]:
    """合并分片，返回 (格式, 文件头, 完整字节)。

    表情包普遍较小（几 MB），直接读入内存处理；超大文件由
    MAX_TOTAL_SIZE 限制兜底。
    """
    tmp = _tmp_dir(md5)
    chunks = _uploaded_chunks(md5)
    data = bytearray()
    for idx in chunks:
        with open(os.path.join(tmp, f'{idx}.part'), 'rb') as f:
            data.extend(f.read())
    if not data or (total_size and len(data) != total_size):
        return '', b'', b''

    head = bytes(data[:32])
    fmt = detect_format(head, bytes(data))
    if fmt is None:
        return '', head, b''
    return fmt, head, bytes(data)


def _make_thumbnail(path: str, fmt: str) -> tuple[str, int, int]:
    """为静态图片生成 webp 缩略图；gif/svg 沿用原图。

    返回 (thumb 相对路径或 '', width, height)。
    """
    rel_dir = datetime.now(timezone.utc).strftime('%Y/%m')
    if fmt == 'svg':
        return '', 0, 0
    try:
        with PILImage.open(path) as img:
            width, height = img.size
            if fmt == 'gif':
                return '', width, height
            img.thumbnail((THUMB_MAX_SIDE, THUMB_MAX_SIDE))
            if img.mode in ('P', 'LA', 'RGBA'):
                img = img.convert('RGBA')
            else:
                img = img.convert('RGB')
            thumb_name = f'{os.path.splitext(os.path.basename(path))[0]}_thumb.webp'
            thumb_rel = f'{rel_dir}/{thumb_name}'
            thumb_abs = os.path.join(current_app.config['UPLOAD_FOLDER'], thumb_rel)
            os.makedirs(os.path.dirname(thumb_abs), exist_ok=True)
            img.save(thumb_abs, 'WEBP', quality=80)
            return thumb_rel, width, height
    except Exception:
        # 缩略图生成失败不影响入库，展示时回退到原图
        return '', 0, 0


@upload_bp.post('/complete')
@jwt_required()
def complete_upload():
    payload = request.get_json(silent=True) or {}
    md5 = (payload.get('md5') or '').lower()
    filename = (payload.get('filename') or '').strip()[:255]
    total_size = payload.get('size') or 0
    tags = payload.get('tags') or []
    category_name = payload.get('category') or ''

    if not MD5_RE.match(md5):
        return fail('非法的文件校验值')
    if not isinstance(tags, list) or len(tags) > 20:
        return fail('标签数量过多')

    existing = db.session.query(Image).filter_by(md5=md5).first()
    if existing is not None:
        if tags:
            existing.tags = get_or_create_tags(tags)
        if category_name:
            existing.category = get_or_create_category(category_name)
        db.session.commit()
        return ok({'instant': True, 'image': existing.to_dict()})

    fmt, _head, data = _assemble(md5, total_size)
    if not data:
        return fail('分片不完整或文件损坏，请重新上传')

    ext = format_extension(fmt)
    stored_name = f'{uuid_lib.uuid4().hex}.{ext}'
    rel_dir = datetime.now(timezone.utc).strftime('%Y/%m')
    rel_path = f'{rel_dir}/{stored_name}'
    abs_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], rel_dir)
    os.makedirs(abs_dir, exist_ok=True)
    abs_path = os.path.join(abs_dir, stored_name)
    with open(abs_path, 'wb') as f:
        f.write(data)

    thumb_rel, width, height = _make_thumbnail(abs_path, fmt)

    image = Image(
        path=rel_path,
        thumb_path=thumb_rel,
        original_name=filename or stored_name,
        format=fmt,
        size=len(data),
        width=width,
        height=height,
        md5=md5,
    )
    image.tags = get_or_create_tags(tags)
    image.category = get_or_create_category(category_name)
    db.session.add(image)
    db.session.commit()

    shutil.rmtree(_tmp_dir(md5), ignore_errors=True)
    return ok({'instant': False, 'image': image.to_dict()})


@upload_bp.post('/abort')
@jwt_required()
def abort_upload():
    payload = request.get_json(silent=True) or {}
    md5 = (payload.get('md5') or '').lower()
    if not MD5_RE.match(md5):
        return fail('非法的文件校验值')
    shutil.rmtree(_tmp_dir(md5), ignore_errors=True)
    return ok(message='已取消')
