"""用户接口：信息 / 头像 / 密码。

头像单独存放在 UPLOAD_FOLDER/avatars/ 目录（server 文件夹内），
数据库只存相对路径，展示时通过签名 URL 下发。
"""
import os
import uuid as uuid_lib
from datetime import datetime, timezone

from flask import Blueprint, current_app, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from PIL import Image as PILImage
from werkzeug.security import check_password_hash

from extensions import db
from models.user import User
from utils.format import detect_format
from utils.response import fail, ok
from utils.signing import signed_image_url

user_bp = Blueprint('user', __name__)

AVATAR_MAX_SIZE = 5 * 1024 * 1024
AVATAR_MAX_SIDE = 512
AVATAR_EXTENSIONS = {'gif', 'jpeg', 'jpg', 'png', 'webp'}


def _current_user() -> User | None:
    return db.session.get(User, int(get_jwt_identity()))


@user_bp.get('/info')
@jwt_required()
def info():
    """当前登录用户信息。未登录时由 JWT 错误处理器统一返回 401。"""
    user = _current_user()
    if user is None:
        return fail('用户不存在，请重新登录', http_status=401)
    return ok(user.to_dict())


@user_bp.put('/name')
@jwt_required()
def change_name():
    """修改显示名字（昵称，非登录账号）。"""
    user = _current_user()
    if user is None:
        return fail('用户不存在，请重新登录', http_status=401)

    payload = request.get_json(silent=True) or {}
    name = (payload.get('name') or '').strip()[:64]
    if not name:
        return fail('名字不能为空')

    user.nickname = name
    user.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return ok(user.to_dict())


@user_bp.post('/avatar')
@jwt_required()
def upload_avatar():
    """上传头像：校验格式 -> 压缩到 512px -> 存 avatars/ -> 删旧文件。"""
    user = _current_user()
    if user is None:
        return fail('用户不存在，请重新登录', http_status=401)

    file = request.files.get('file')
    if file is None or not file.filename:
        return fail('请选择头像图片')

    file.seek(0, os.SEEK_END)
    size = file.tell()
    if size > AVATAR_MAX_SIZE:
        return fail('头像图片不能超过 5MB')
    file.seek(0)

    head = file.read(64)
    file.seek(0)
    full = file.read()
    file.seek(0)
    fmt = detect_format(head, full)
    if fmt is None:
        return fail('不支持的图片格式，仅支持 JPG / PNG / WEBP / GIF')
    if fmt not in AVATAR_EXTENSIONS:
        return fail('不支持的图片格式，仅支持 JPG / PNG / WEBP / GIF')

    avatar_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'avatars')
    os.makedirs(avatar_dir, exist_ok=True)

    stored_name = f'{uuid_lib.uuid4().hex}.webp'
    stored_path = os.path.join(avatar_dir, stored_name)
    try:
        with PILImage.open(file) as img:
            img.thumbnail((AVATAR_MAX_SIDE, AVATAR_MAX_SIDE))
            if img.mode in ('P', 'LA', 'RGBA'):
                img = img.convert('RGBA')
            else:
                img = img.convert('RGB')
            img.save(stored_path, 'WEBP', quality=85)
    except Exception:
        return fail('头像图片无法解析，请换一张试试')

    # 删除旧头像文件（仅清理 avatars/ 目录内的）
    if user.avatar and user.avatar.startswith('avatars/'):
        old_path = os.path.abspath(
            os.path.join(current_app.config['UPLOAD_FOLDER'], user.avatar)
        )
        avatar_root = os.path.abspath(avatar_dir)
        if old_path.startswith(avatar_root + os.sep) and os.path.isfile(old_path):
            os.remove(old_path)

    user.avatar = f'avatars/{stored_name}'
    user.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return ok({'avatar': signed_image_url(user.avatar)})


@user_bp.put('/password')
@jwt_required()
def change_password():
    """修改密码：验证原密码后更新为新密码（scrypt 加盐哈希存储）。"""
    user = _current_user()
    if user is None:
        return fail('用户不存在，请重新登录', http_status=401)

    payload = request.get_json(silent=True) or {}
    old_password = payload.get('oldPassword') or ''
    new_password = payload.get('newPassword') or ''

    if not old_password or not new_password:
        return fail('请填写原密码和新密码')
    if len(new_password) < 6:
        return fail('新密码至少 6 位')
    if not user.verify_password(old_password):
        return fail('原密码错误', http_status=400)

    user.set_password(new_password)
    db.session.commit()
    return ok(message='密码已修改')
