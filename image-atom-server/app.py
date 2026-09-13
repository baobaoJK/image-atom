"""图元 (Image-Atom) 后端服务入口。

单用户系统的账号创建策略：
1. 首次启动时，若数据库中没有任何用户，则使用环境变量
   ADMIN_USERNAME / ADMIN_PASSWORD 自动创建唯一账号（Docker 一键部署场景）。
2. 忘记密码时通过命令行重置：
   docker compose exec server flask reset-password

不提供公开注册接口：注册页已从客户端移除，公开注册会带来被抢占注册的
安全风险。
"""
import getpass
import os

import click
from flask import Flask, current_app, jsonify, request
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from api.auth import auth_bp
from api.image import image_bp
from api.user import user_bp
from api.upload import upload_bp
from config import CONFIGS
from extensions import cors, db, jwt
from models.user import User
from utils.response import fail


def create_app() -> Flask:
    app = Flask(__name__)
    env = os.getenv('FLASK_ENV', 'production')
    app.config.from_object(CONFIGS.get(env, CONFIGS['production']))
    app.json.ensure_ascii = False

    db.init_app(app)
    jwt.init_app(app)

    if app.config['CORS_ORIGINS']:
        cors.init_app(
            app,
            origins=[o.strip() for o in app.config['CORS_ORIGINS'].split(',') if o.strip()],
            supports_credentials=True,
        )

    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(user_bp, url_prefix='/api/user')
    app.register_blueprint(upload_bp, url_prefix='/api/upload')
    app.register_blueprint(image_bp, url_prefix='/api/image')
    _register_error_handlers(app)
    _register_cli(app)

    with app.app_context():
        db.create_all()
        _patch_schema()
        _ensure_single_user(app)
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    return app


def _patch_schema() -> None:
    """轻量迁移：db.create_all 只建新表不加列，这里为旧库补缺失列。

    当前需要：images.category_id（分类功能引入）。
    SQLite 不支持 ADD CONSTRAINT，只加普通列。
    """
    inspector = db.inspect(db.engine)
    columns = [col['name'] for col in inspector.get_columns('images')]
    if 'category_id' in columns:
        return

    if db.engine.dialect.name == 'sqlite':
        db.session.execute(
            db.text('ALTER TABLE images ADD COLUMN category_id INTEGER')
        )
    else:
        db.session.execute(
            db.text('ALTER TABLE images ADD COLUMN category_id INTEGER')
        )
        db.session.execute(
            db.text(
                'ALTER TABLE images '
                'ADD CONSTRAINT fk_images_category '
                'FOREIGN KEY (category_id) REFERENCES categories (id)'
            )
        )
    db.session.commit()
    current_app.logger.info('已为 images 表补充 category_id 列')


def _ensure_single_user(app: Flask) -> None:
    """数据库中没有任何用户时，根据环境变量创建唯一初始账号。"""
    if db.session.query(User).count() > 0:
        return

    username = (app.config.get('ADMIN_USERNAME') or 'admin').strip()
    password = app.config.get('ADMIN_PASSWORD') or ''
    if not password:
        app.logger.warning('未设置 ADMIN_PASSWORD，跳过初始用户创建')
        return

    user = User(username=username, nickname=username)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    if password in {'admin', 'admin123', '123456', 'password'}:
        app.logger.warning(
            '已使用默认弱密码创建初始用户 %s，请尽快修改：\n'
            '  docker compose exec server flask reset-password',
            username,
        )
    else:
        app.logger.info('已创建初始用户 %s', username)


def _register_error_handlers(app: Flask) -> None:
    # JWT 相关错误统一转成前端约定的格式，HTTP 状态码保持 401，
    # 前端拦截器据此走刷新 token / 重新登录逻辑。
    @jwt.expired_token_loader
    def expired_token(_header, _payload):
        return fail('登录已过期，请重新登录', http_status=401)

    @jwt.invalid_token_loader
    def invalid_token(_reason):
        return fail('无效的登录凭证', http_status=401)

    @jwt.unauthorized_loader
    def unauthorized(_reason):
        return fail('请先登录', http_status=401)

    @jwt.revoked_token_loader
    def revoked_token(_header, _payload):
        return fail('登录凭证已失效，请重新登录', http_status=401)

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(_error):
        limit_mb = app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)
        return fail(f'文件过大，单个文件不能超过 {limit_mb}MB', http_status=413)

    @app.errorhandler(HTTPException)
    def http_exception(error):
        # API 路径统一返回 JSON，避免把 HTML 错误页抛给前端
        if request.path.startswith('/api'):
            return fail(error.description or error.name, http_status=error.code or 500)
        return error

    @app.get('/api/health')
    def health():
        return jsonify({'code': 0, 'data': {'status': 'up'}, 'message': 'ok'})


def _register_cli(app: Flask) -> None:
    @app.cli.command('reset-password')
    @click.option('--username', default=None, help='要重置密码的用户名，默认为当前唯一用户')
    def reset_password(username: None | str) -> None:
        """交互式重置用户密码（密码不会出现在命令历史中）。"""
        with app.app_context():
            if username:
                user = db.session.query(User).filter_by(username=username).first()
            else:
                user = db.session.query(User).order_by(User.id).first()
            if user is None:
                click.echo('用户不存在，请用 --username 指定用户名')
                return

            click.echo(f'正在为用户 {user.username} 重置密码')
            password = getpass.getpass('请输入新密码（至少 6 位）: ')
            if len(password) < 6:
                click.echo('密码长度不足 6 位，未做修改')
                return
            confirm = getpass.getpass('请再次输入新密码: ')
            if password != confirm:
                click.echo('两次输入不一致，未做修改')
                return

            user.set_password(password)
            db.session.commit()
            click.echo(f'用户 {user.username} 的密码已重置')


app = create_app()

if __name__ == '__main__':
    # 本地开发入口；生产环境使用 gunicorn 运行（见 Dockerfile）
    app.run(host='127.0.0.1', port=5000, debug=app.config.get('DEBUG', False))
