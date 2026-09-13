FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai \
    FLASK_APP=app.py

WORKDIR /app

COPY requirements.txt .
# 依赖安装：清华源失败自动切阿里云源，再失败用官方 PyPI（海外服务器适用）
RUN pip install --no-cache-dir --retries 3 --timeout 30 \
      -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple \
    || pip install --no-cache-dir --retries 3 --timeout 30 \
      -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ \
    || pip install --no-cache-dir --retries 3 --timeout 30 \
      -r requirements.txt

COPY . .

RUN mkdir -p /app/uploads

EXPOSE 5000

# gunicorn：2 进程 x 4 线程，足够个人使用
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "4", "--timeout", "120", "--access-logfile", "-", "app:app"]
