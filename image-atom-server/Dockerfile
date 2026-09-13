FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai \
    FLASK_APP=app.py

WORKDIR /app

COPY requirements.txt .
# 使用清华 PyPI 镜像加速国内构建；海外构建可删除 -i 参数
RUN pip install --no-cache-dir -r requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY . .

RUN mkdir -p /app/uploads

EXPOSE 5000

# gunicorn：2 进程 x 4 线程，足够个人使用
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "4", "--timeout", "120", "--access-logfile", "-", "app:app"]
