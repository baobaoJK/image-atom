"""认证接口：登录 / 刷新 token / 登出 / 权限码。

响应格式与 Vben Admin 前端约定一致（见 utils/response.py）。
注意 /auth/refresh 的响应体是「裸 token 字符串」，这是 Vben 客户端
doRefreshToken 的约定（resp.data 直接就是新 token）。
"""
import os

from flask import Blueprint, current_app, make_response, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    decode_token,
    jwt_required,
)

from extensions import db
from models.user import User
from utils.response import fail, ok

auth_bp = Blueprint('auth', __name__)


def _set_refresh_cookie(response, token: str):
    cfg = current_app.config
    response.set_cookie(
        cfg['REFRESH_TOKEN_COOKIE'],
        token,
        max_age=int(cfg['JWT_REFRESH_TOKEN_EXPIRES'].total_seconds()),
        httponly=True,
        samesite='Lax',
        secure=cfg['COOKIE_SECURE'],
        path='/',
    )
    return response


@auth_bp.post('/login')
def login():
    payload = request.get_json(silent=True) or {}
    username = (payload.get('username') or '').strip()
    password = payload.get('password') or ''
    if not username or not password:
        return fail('用户名和密码不能为空')

    user = db.session.query(User).filter_by(username=username).first()
    # 用户不存在时也做一次哈希比对，保持响应时间一致，避免用户名枚举
    if user is None:
        User(username='__timing__').verify_password(password)
        return fail('用户名或密码错误', http_status=401)
    if not user.verify_password(password):
        return fail('用户名或密码错误', http_status=401)

    access_token = create_access_token(
        identity=str(user.id), additional_claims={'username': user.username}
    )
    refresh_token = create_refresh_token(
        identity=str(user.id), additional_claims={'username': user.username}
    )

    data = user.to_dict()
    data['accessToken'] = access_token
    response = make_response(ok(data))
    return _set_refresh_cookie(response, refresh_token)


@auth_bp.post('/refresh')
def refresh():
    """用 HttpOnly Cookie 中的 refresh token 换取新的 access token。

    响应体为裸 token 字符串（Vben 前端约定），不是统一 JSON 格式。
    """
    refresh_token = request.cookies.get(current_app.config['REFRESH_TOKEN_COOKIE'])
    if not refresh_token:
        return fail('未登录', http_status=401)

    try:
        claims = decode_token(refresh_token)
    except Exception:
        return fail('登录已过期，请重新登录', http_status=401)
    if claims.get('type') != 'refresh':
        return fail('无效的登录凭证', http_status=401)

    user = db.session.get(User, int(claims['sub']))
    if user is None:
        return fail('用户不存在，请重新登录', http_status=401)

    access_token = create_access_token(
        identity=str(user.id), additional_claims={'username': user.username}
    )
    response = make_response(access_token, 200)
    response.mimetype = 'text/plain'
    return _set_refresh_cookie(response, refresh_token)


@auth_bp.post('/logout')
def logout():
    """登出：清除 refresh cookie。幂等操作，无需携带 token。"""
    response = make_response(ok(message='已退出登录'))
    response.delete_cookie(
        current_app.config['REFRESH_TOKEN_COOKIE'],
        httponly=True,
        samesite='Lax',
        secure=current_app.config['COOKIE_SECURE'],
        path='/',
    )
    return response


@auth_bp.get('/codes')
@jwt_required()
def codes():
    """权限码。单用户系统拥有全部权限，返回空数组即可。"""
    return ok([])
