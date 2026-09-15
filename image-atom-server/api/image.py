"""图片接口：列表 / 标签 / 分类 / 编辑 / 删除 / 带签名的文件服务。"""
import os

from flask import Blueprint, Response, current_app, request, send_file
from flask_jwt_extended import jwt_required

from extensions import db
from models.image import (
    Category,
    Image,
    Tag,
    get_or_create_category,
    get_or_create_tags,
    image_tags,
    remove_orphan_meta,
)
from utils.format import SUPPORTED_FORMATS
from utils.response import fail, ok
from utils.signing import verify_image_signature

image_bp = Blueprint('image', __name__, url_prefix='/image')

DEFAULT_PAGE_SIZE = 30
MAX_PAGE_SIZE = 100


@image_bp.get('/list')
@jwt_required()
def list_images():
    """分页获取表情包，支持按标签 / 分类 / 图片类型（静态|动态）筛选。

    GET /api/image/list?page=1&pageSize=30&tags=搞笑&category=猫和老鼠&type=animated
    """
    try:
        page = max(1, int(request.args.get('page', 1)))
        page_size = min(MAX_PAGE_SIZE, max(1, int(request.args.get('pageSize', DEFAULT_PAGE_SIZE))))
    except ValueError:
        return fail('分页参数不合法')

    tags_param = request.args.get('tags', '').strip()
    tag_names = [t.strip() for t in tags_param.split(',') if t.strip()][:10]
    category_param = request.args.get('category', '').strip()
    image_type = request.args.get('type', '').strip().lower()
    search = request.args.get('search', '').strip()

    query = db.session.query(Image)
    if search:
        query = query.filter(Image.original_name.ilike(f'%{search}%'))
    if tag_names:
        # 必须同时包含所有给定标签
        query = query.filter(
            *[Image.tags.any(Tag.name == name) for name in tag_names]
        )
    if category_param:
        query = query.join(Category).filter(Category.name == category_param)
    if image_type in {'static', 'animated'}:
        if image_type == 'animated':
            query = query.filter(Image.format == 'gif')
        else:
            query = query.filter(Image.format != 'gif')

    total = query.count()
    items = (
        query.order_by(Image.created_at.desc(), Image.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return ok({
        'items': [item.to_dict() for item in items],
        'total': total,
        'page': page,
        'pageSize': page_size,
        'hasMore': page * page_size < total,
        'supportedFormats': list(SUPPORTED_FORMATS),
    })


@image_bp.get('/categories')
@jwt_required()
def list_categories():
    """全部分类及图片数量，用于上传时的选择和图库筛选。"""
    counts = (
        db.session.query(
            Category, db.func.count(Image.id).label('cnt')
        )
        .outerjoin(Image, Image.category_id == Category.id)
        .group_by(Category.id)
        .order_by(db.desc('cnt'))
        .all()
    )
    return ok([category.to_dict(count=cnt) for category, cnt in counts])


@image_bp.get('/tags')
@jwt_required()
def list_tags():
    """标签及使用数量；可按分类 / 图片类型级联过滤。

    过滤条件生效时只返回"正在使用中"的标签（数量为 0 的不显示），
    无过滤条件时返回全部标签。

    GET /api/image/tags
    GET /api/image/tags?category=猫和老鼠&type=animated
    """
    category_param = request.args.get('category', '').strip()
    image_type = request.args.get('type', '').strip().lower()
    has_type_filter = image_type in {'static', 'animated'}

    counts_query = db.session.query(
        Tag, db.func.count(image_tags.c.image_id).label('cnt')
    ).outerjoin(image_tags, image_tags.c.tag_id == Tag.id)

    # 有任一筛选时需要关联图片表；分类需再关联分类表
    if category_param or has_type_filter:
        counts_query = counts_query.join(
            Image, Image.id == image_tags.c.image_id
        )
    if category_param:
        counts_query = counts_query.join(
            Category, Image.category_id == Category.id
        ).filter(Category.name == category_param)
    if has_type_filter:
        counts_query = counts_query.filter(
            Image.format == 'gif'
            if image_type == 'animated'
            else Image.format != 'gif'
        )

    if category_param or has_type_filter:
        # 只保留筛选范围内"正在使用"的标签
        counts_query = counts_query.having(
            db.func.count(image_tags.c.image_id) > 0
        )

    counts = (
        counts_query.group_by(Tag.id)
        .order_by(db.desc(db.func.count(image_tags.c.image_id)))
        .all()
    )
    return ok([tag.to_dict(count=cnt) for tag, cnt in counts])


@image_bp.put('/<int:image_id>')
@jwt_required()
def update_image(image_id: int):
    """编辑图片信息：名字 / 分类 / 标签（可只传其中一部分）。"""
    payload = request.get_json(silent=True) or {}
    image = db.session.get(Image, image_id)
    if image is None:
        return fail('图片不存在', http_status=404)

    if 'name' in payload:
        name = (payload.get('name') or '').strip()[:255]
        if not name:
            return fail('名字不能为空')
        image.original_name = name

    if 'category' in payload:
        image.category = get_or_create_category(payload.get('category') or '')

    if 'tags' in payload:
        tags = payload.get('tags')
        if not isinstance(tags, list) or len(tags) > 20:
            return fail('标签数量过多')
        image.tags = get_or_create_tags(tags)

    db.session.commit()
    remove_orphan_meta()
    db.session.commit()
    return ok(image.to_dict())


@image_bp.delete('/<int:image_id>')
@jwt_required()
def delete_image(image_id: int):
    """删除图片：同时删除原图和缩略图文件，并清理孤儿标签/分类。"""
    image = db.session.get(Image, image_id)
    if image is None:
        return fail('图片不存在', http_status=404)

    upload_root = os.path.abspath(current_app.config['UPLOAD_FOLDER'])
    for rel in (image.thumb_path, image.path):
        if not rel:
            continue
        file_path = os.path.abspath(os.path.join(upload_root, rel))
        if file_path.startswith(upload_root + os.sep) and os.path.isfile(file_path):
            os.remove(file_path)

    db.session.delete(image)
    db.session.commit()
    remove_orphan_meta()
    db.session.commit()
    return ok(message='已删除')


@image_bp.get('/stats')
@jwt_required()
def image_stats():
    """仪表盘统计：图片数 / 磁盘文件数 / 占用空间 / 类型分布。"""
    total = db.session.query(Image).count()
    static_count = (
        db.session.query(Image).filter(Image.format != 'gif').count()
    )

    upload_root = os.path.abspath(current_app.config['UPLOAD_FOLDER'])
    originals = thumbnails = 0
    disk_bytes = 0
    for dirpath, dirnames, filenames in os.walk(upload_root):
        # 头像与临时分片不计入图片统计
        dirnames[:] = [d for d in dirnames if d not in {'.tmp', 'avatars'}]
        for fn in filenames:
            file_path = os.path.join(dirpath, fn)
            if not os.path.isfile(file_path):
                continue
            disk_bytes += os.path.getsize(file_path)
            if fn.endswith('_thumb.webp'):
                thumbnails += 1
            else:
                originals += 1

    return ok({
        'images': total,                      # 图片总数（数据库记录）
        'originals': originals,               # 磁盘原图文件数
        'thumbnails': thumbnails,             # 磁盘缩略图文件数
        'diskUsage': disk_bytes,              # 原图 + 缩略图占用字节数
        'typeCounts': {
            'static': static_count,
            'animated': total - static_count,
        },
    })


@image_bp.put('/batch')
@jwt_required()
def batch_update():
    """批量编辑：设置分类 / 追加标签。

    { ids: [1,2,3], category?: '猫和老鼠', addTags?: ['搞笑'] }
    category 不传或为空则不修改分类；addTags 追加到每张图的已有标签。
    """
    payload = request.get_json(silent=True) or {}
    ids = payload.get('ids')
    category = payload.get('category')
    add_tags = payload.get('addTags')

    if (
        not isinstance(ids, list)
        or not ids
        or not all(isinstance(i, int) for i in ids)
        or len(ids) > 200
    ):
        return fail('请选择要编辑的图片（单次最多 200 张）')
    if category is not None and not isinstance(category, str):
        return fail('分类参数不合法')
    if add_tags is not None and (
        not isinstance(add_tags, list) or len(add_tags) > 20
    ):
        return fail('标签数量过多')

    images = db.session.query(Image).filter(Image.id.in_(ids)).all()
    if not images:
        return fail('图片不存在', http_status=404)

    category_obj = (
        get_or_create_category(category) if category and category.strip() else None
    )
    tag_objs = get_or_create_tags(add_tags) if add_tags else []

    for image in images:
        if category_obj is not None:
            image.category = category_obj
        for tag in tag_objs:
            if tag not in image.tags:
                image.tags.append(tag)

    db.session.commit()
    remove_orphan_meta()
    db.session.commit()
    return ok({'updated': len(images)})


@image_bp.post('/batch-delete')
@jwt_required()
def batch_delete():
    """批量删除：同步删除原图和缩略图文件，并清理孤儿标签/分类。"""
    payload = request.get_json(silent=True) or {}
    ids = payload.get('ids')

    if (
        not isinstance(ids, list)
        or not ids
        or not all(isinstance(i, int) for i in ids)
        or len(ids) > 200
    ):
        return fail('请选择要删除的图片（单次最多 200 张）')

    images = db.session.query(Image).filter(Image.id.in_(ids)).all()
    if not images:
        return fail('图片不存在', http_status=404)

    upload_root = os.path.abspath(current_app.config['UPLOAD_FOLDER'])
    for image in images:
        for rel in (image.thumb_path, image.path):
            if not rel:
                continue
            file_path = os.path.abspath(os.path.join(upload_root, rel))
            if file_path.startswith(upload_root + os.sep) and os.path.isfile(
                file_path
            ):
                os.remove(file_path)

    # 批量删除不走 ORM 级联，先清关联表再删记录
    db.session.execute(
        image_tags.delete().where(image_tags.c.image_id.in_([i.id for i in images]))
    )
    deleted = (
        db.session.query(Image)
        .filter(Image.id.in_([i.id for i in images]))
        .delete(synchronize_session=False)
    )
    db.session.commit()
    remove_orphan_meta()
    db.session.commit()
    return ok({'deleted': deleted})


@image_bp.get('/file/<path:rel_path>')
def serve_file(rel_path: str):
    """图片文件服务。

    <img> 标签无法携带 Authorization 头，改用 HMAC 签名参数鉴权：
    签名 URL 仅通过需要登录的列表接口下发，未登录用户无法获得；
    无效或过期签名返回 401。URL 稳定且文件名含 uuid，
    配合 Cache-Control 长缓存。
    """
    expires = request.args.get('e', '')
    signature = request.args.get('s', '')
    if not verify_image_signature(rel_path, expires, signature):
        return fail('未登录或链接已失效', http_status=401)

    upload_root = os.path.abspath(current_app.config['UPLOAD_FOLDER'])
    file_path = os.path.abspath(os.path.join(upload_root, rel_path))
    # 防目录穿越：解析后的路径必须仍在上传目录内
    if not file_path.startswith(upload_root + os.sep):
        return fail('非法路径', http_status=400)
    if not os.path.isfile(file_path):
        return fail('文件不存在', http_status=404)

    response = send_file(file_path, conditional=True)
    # uuid 文件名内容永不变化：允许浏览器与中间层长时间缓存
    response.headers['Cache-Control'] = 'private, max-age=2592000, immutable'
    return response
