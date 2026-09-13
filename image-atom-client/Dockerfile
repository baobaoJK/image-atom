# ---------- 构建阶段 ----------
FROM node:22-slim AS builder

ENV PNPM_HOME="/pnpm" \
    PATH="$PNPM_HOME:$PATH" \
    NODE_OPTIONS=--max-old-space-size=8192 \
    TZ=Asia/Shanghai \
    CI=true \
    COREPACK_ENABLE_DOWNLOAD_PROMPT=0 \
    COREPACK_NPM_REGISTRY=https://registry.npmmirror.com

RUN npm i -g corepack

WORKDIR /app

# 复制整个 monorepo（.dockerignore 已排除 node_modules/dist 等）
COPY . /app

# 安装依赖并构建 web-antd 应用（国内用 npmmirror 加速）
RUN --mount=type=cache,id=pnpm,target=/pnpm/store \
    pnpm config set registry https://registry.npmmirror.com && \
    pnpm install --frozen-lockfile && \
    pnpm --filter @vben/web-antd run build

# ---------- 运行阶段 ----------
FROM nginx:stable-alpine AS production

ENV TZ=Asia/Shanghai

# 静态资源
COPY --from=builder /app/apps/web-antd/dist /usr/share/nginx/html

# nginx 配置：SPA + /api 反向代理到后端容器
COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
