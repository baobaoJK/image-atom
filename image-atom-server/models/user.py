"""用户模型。

本应用为单用户系统（个人表情包收集），全库最多只有一条用户记录。
密码使用 Werkzeug 的 salted hash 存储（默认 scrypt / pbkdf2），数据库中
永远不保存明文密码。
"""
from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(512), nullable=False)
    nickname = db.Column(db.String(64), nullable=False, default='')
    avatar = db.Column(db.String(512), nullable=False, default='')
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password)

    def verify_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)

    def to_dict(self) -> dict:
        """返回前端 Vben Admin `UserInfo` 结构需要的字段。"""
        from utils.signing import signed_image_url

        return {
            'userId': self.id,
            'username': self.username,
            'realName': self.nickname or self.username,
            'avatar': signed_image_url(self.avatar) if self.avatar else '',
            'desc': '图元管理员',
            'homePath': '/gallery',
            'roles': ['super', 'admin'],
            'token': '',
            'createdAt': self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f'<User {self.username}>'
