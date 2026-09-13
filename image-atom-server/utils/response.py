"""统一响应格式，与前端 Vben Admin 的约定保持一致：

成功: { code: 0,  data: {...}, message: 'ok' }
失败: { code: -1, data: null, message: '错误信息' }
前端拦截器以 code === 0 判定成功，并以 HTTP 401 触发重新认证。
"""
from flask import jsonify


def ok(data=None, message='ok'):
    return jsonify({'code': 0, 'data': data, 'message': message}), 200


def fail(message='error', http_status=400):
    return jsonify({'code': -1, 'data': None, 'message': message}), http_status
