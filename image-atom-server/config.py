"""应用配置，全部通过环境变量注入，便于 Docker 部署时覆盖。"""
import os
from datetime import timedelta

# 本地开发时自动读取 image-atom-server/.env；不覆盖已存在的环境变量，
# 因此 Docker compose 注入的变量始终优先。
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class BaseConfig:
    # Flask session 密钥
    SECRET_KEY = os.getenv('SECRET_KEY', 'change-me-please')

    # JWT 配置
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', SECRET_KEY)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        minutes=int(os.getenv('JWT_ACCESS_TOKEN_EXPIRES_MINUTES', '60'))
    )
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(
        days=int(os.getenv('JWT_REFRESH_TOKEN_EXPIRES_DAYS', '30'))
    )

    # 数据库：默认本地开发用 SQLite，生产通过 DATABASE_URL 连 PostgreSQL
    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URL', f"sqlite:///{os.path.join(BASE_DIR, 'image_atom.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {'pool_pre_ping': True}

    # 上传文件目录：本地开发默认存到后端目录的 uploads/（Windows 友好）；
    # Docker 部署时由 compose 覆盖为 /app/uploads 并挂载到宿主机磁盘
    UPLOAD_FOLDER = os.getenv(
        'UPLOAD_FOLDER', os.path.join(BASE_DIR, 'uploads')
    )
    MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH_MB', '50')) * 1024 * 1024

    # 跨域：默认关闭（生产走 Nginx 同源反代，开发走 Vite 代理）。
    # 如需跨域访问，设置 CORS_ORIGINS=https://a.com,https://b.com
    CORS_ORIGINS = os.getenv('CORS_ORIGINS', '')

    # Cookie 安全策略：站点启用 HTTPS 后设置为 true
    COOKIE_SECURE = os.getenv('COOKIE_SECURE', 'false').lower() == 'true'
    REFRESH_TOKEN_COOKIE = 'image_atom_refresh_token'

    # 初始账号：仅当数据库中没有任何用户时，首次启动会用它创建唯一用户
    ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
    ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class ProductionConfig(BaseConfig):
    DEBUG = False


CONFIGS = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
}
