"""表情包、分类与标签模型。

图片文件本体存放在磁盘（UPLOAD_FOLDER/年/月/uuid.扩展名），
数据库只保存元数据；md5 用于秒传去重和断点续传定位。

- Category：分类文件夹（如 猫和老鼠 / Doro / 柴郡），一张图属于一个分类
- Tag：标签（如 汤姆猫 / 搞笑 / 吃东西），一张图可打多个标签
- imageType 由格式推导：gif 为动态图，其余为静态图
"""
from datetime import datetime, timezone

from extensions import db


class Category(db.Model):
    __tablename__ = 'categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False, index=True)

    def to_dict(self, count: int | None = None) -> dict:
        data = {'id': self.id, 'name': self.name}
        if count is not None:
            data['count'] = count
        return data

    def __repr__(self) -> str:
        return f'<Category {self.name}>'


class Tag(db.Model):
    __tablename__ = 'tags'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), unique=True, nullable=False, index=True)

    def to_dict(self, count: int | None = None) -> dict:
        data = {'id': self.id, 'name': self.name}
        if count is not None:
            data['count'] = count
        return data


# 多对多关联表
image_tags = db.Table(
    'image_tags',
    db.Column('image_id', db.Integer, db.ForeignKey('images.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tags.id'), primary_key=True),
)


def get_or_create_tags(names: list[str]) -> list[Tag]:
    """按名称取已有标签或创建新标签，空名字跳过。"""
    tags = []
    for raw in names:
        name = (raw or '').strip()[:32]
        if not name:
            continue
        tag = db.session.query(Tag).filter_by(name=name).first()
        if tag is None:
            tag = Tag(name=name)
            db.session.add(tag)
        tags.append(tag)
    return tags


def get_or_create_category(name: str) -> Category | None:
    """按名称取已有分类或创建新分类；空值/'未分类' 返回 None。"""
    name = (name or '').strip()[:64]
    if not name or name == '未分类':
        return None
    category = db.session.query(Category).filter_by(name=name).first()
    if category is None:
        category = Category(name=name)
        db.session.add(category)
    return category


def remove_orphan_meta() -> None:
    """删除不再被任何图片引用的标签和分类（图片删除后调用）。"""
    db.session.query(Tag).filter(~Tag.images.any()).delete(
        synchronize_session=False
    )
    db.session.query(Category).filter(~Category.images.any()).delete(
        synchronize_session=False
    )


class Image(db.Model):
    __tablename__ = 'images'

    id = db.Column(db.Integer, primary_key=True)
    # 磁盘上的相对路径，如 2026/09/3f2a...c1.gif
    path = db.Column(db.String(256), unique=True, nullable=False, index=True)
    # 缩略图相对路径（gif/svg 为空，直接用原图）
    thumb_path = db.Column(db.String(256), nullable=False, default='')
    original_name = db.Column(db.String(255), nullable=False, default='')
    # 检测出的真实格式：gif/jpeg/png/webp/svg
    format = db.Column(db.String(16), nullable=False)
    size = db.Column(db.Integer, nullable=False, default=0)
    width = db.Column(db.Integer, nullable=False, default=0)
    height = db.Column(db.Integer, nullable=False, default=0)
    md5 = db.Column(db.String(32), unique=True, nullable=False, index=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # 分类文件夹（可选，未设置时前端显示"未分类"）
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    category = db.relationship('Category', backref='images')

    tags = db.relationship(
        'Tag', secondary=image_tags, backref=db.backref('images', lazy='dynamic'),
        lazy='select',
    )

    def to_dict(self) -> dict:
        from utils.signing import signed_image_url

        return {
            'id': self.id,
            'originalName': self.original_name,
            'format': self.format,
            'imageType': 'animated' if self.format == 'gif' else 'static',
            'category': self.category.name if self.category else '未分类',
            'size': self.size,
            'width': self.width,
            'height': self.height,
            'md5': self.md5,
            'createdAt': self.created_at.isoformat(),
            'tags': [t.name for t in self.tags],
            # 签名 URL：携带 HMAC，有效期 30 天；未登录用户拿不到该 URL
            'url': signed_image_url(self.path),
            'thumbUrl': signed_image_url(self.thumb_path) if self.thumb_path else signed_image_url(self.path),
        }

    def __repr__(self) -> str:
        return f'<Image {self.path}>'
