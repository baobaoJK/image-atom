# 图元 (Image-Atom) 部署指南

个人表情包收集应用，由三个容器组成：

| 服务 | 说明 | 数据落盘位置 |
| --- | --- | --- |
| `client` | Nginx 托管 Vben 构建产物，并反向代理 `/api` | 无状态 |
| `server` | Flask + Gunicorn 后端（认证 / 业务接口） | `./data/uploads`（表情包图片） |
| `postgres` | PostgreSQL 18 数据库 | `./data/postgres` |

所有数据都保存在自己的服务器磁盘上，不依赖任何第三方 OSS。

---

## 一、快速开始（服务器部署）

```bash
# 1. 进入项目根目录（docker-compose.yml 所在目录）
cd Image-Atom

# 2. 按需修改 .env（初始账号 KSaMar / 123456，部署后请修改密码）
#    密钥（SECRET_KEY / JWT_SECRET_KEY / POSTGRES_PASSWORD）已随机生成，可直接用
vim .env

# 3. 构建并启动
docker compose up -d --build

# 4. 查看状态与日志
docker compose ps
docker compose logs -f server
```

启动完成后访问 `http://服务器IP:8000`（端口由 `.env` 中 `WEB_PORT` 控制）。

首次启动时后端检测到数据库为空，会用 `ADMIN_USERNAME` / `ADMIN_PASSWORD`
自动创建唯一账号（默认 KSaMar / 123456），直接登录即可。

## 二、1Panel 面板部署

1. 把整个 `Image-Atom` 项目目录上传到服务器，例如 `/opt/image-atom`。
2. 1Panel → **容器 → 编排** → **创建编排**：
   - 路径选择 `/opt/image-atom`（即包含 `docker-compose.yml` 的目录）；
   - 或直接粘贴 `docker-compose.yml` 内容，但必须保证
     `image-atom-client/`、`image-atom-server/` 两个目录也在服务器上。
3. 编辑 `.env` 确认初始账号后点击部署。
4. 部署完成后，在 **网站** 中新建一个「反向代理」站点指向
   `http://127.0.0.1:8000`，并在 1Panel 中为该站点申请 HTTPS 证书。
5. 启用 HTTPS 后，把 `.env` 中 `COOKIE_SECURE` 改为 `true` 并执行
   `docker compose up -d` 重建后端，refresh cookie 会自动带上 Secure 标记。

## 三、本地开发

前端（image-atom-client 目录）：

```bash
pnpm install
pnpm dev:antd   # http://localhost:5666，/api 已通过 Vite 代理到本地后端
```

后端（image-atom-server 目录）：

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # Windows
# Linux/Mac: .venv/bin/pip install -r requirements.txt
.venv/Scripts/python app.py                     # 读取同目录 .env 配置
```

本地开发默认连接你已有的 PostgreSQL：`127.0.0.1:5433`
（配置在 `image-atom-server/.env` 中，可自行修改）。

## 四、账号与密码

- 全站只有一个账号（单用户系统），没有公开注册入口。
- **修改密码**（推荐部署后立即执行）：

  ```bash
  docker compose exec server flask reset-password
  ```

  按提示输入两次新密码即可。密码以 scrypt 加盐哈希存储在数据库中，
  无法从库中还原明文。

- 本地开发环境重置密码：`cd image-atom-server && .venv/Scripts/flask reset-password`

## 五、表情包图片存储方案（本机磁盘，无 OSS）

- 图片统一存放在 `./data/uploads`（容器内 `/app/uploads`），按
  `年/月/uuid.扩展名` 分目录，避免重名与路径穿越。
- 数据库只保存元数据（文件名、相对路径、分类、标签、宽高、大小），
  迁移服务器时拷贝 `data/` 目录 + 一份 `pg_dump` 即可全部带走。
- GIF / SVG 保持原样存储；JPG / PNG / WebP 上传时用 Pillow 压缩并生成
  缩略图（后续版本实现）。
- 读取鉴权：图片统一通过后端接口（携带 JWT）读取，而不是 Nginx 静态
  直出，未登录用户访问一律 401，防止盗链。

## 六、备份与恢复

```bash
# 备份数据库
docker compose exec postgres pg_dump -U image_atom image_atom > backup.sql

# 备份图片目录
tar czf uploads.tar.gz ./data/uploads

# 恢复数据库
cat backup.sql | docker compose exec -T postgres psql -U image_atom -d image_atom
```

## 七、常见问题

- **端口冲突**：修改 `.env` 中的 `WEB_PORT` 后 `docker compose up -d` 重建。
- **PostgreSQL 密码修改**：`data/postgres` 中的旧集群不会因改 `.env`
  而生效；如需更换密码，停止服务后清空 `./data/postgres` 再重新启动
  （会删除库内数据，先备份）。
- **登录后一直提示重新登录**：HTTPS 站点未设置 `COOKIE_SECURE=true`，
  或反代未把 `Authorization` 头透传给后端（本项目自带 nginx.conf 已透传）。
- **忘记密码**：见第四节的重置命令，无需邮箱验证。
- **本地已有 PostgreSQL**（如 `127.0.0.1:5433`）：开发时后端走
  `image-atom-server/.env` 的 `DATABASE_URL`；生产 compose 中的
  `postgres` 服务与其互不影响。
