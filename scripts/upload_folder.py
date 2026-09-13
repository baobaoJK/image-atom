"""批量上传本地文件夹中的表情包。

目录约定（与图库的"分类文件夹"对应）：
    TestImg/
        猫和老鼠/
            xxx.gif
            yyy.jpg
        Doro/
            ...

- 每个子目录名 = 上传后的分类名称；根目录下的散图归入"未分类"
- 按内容 md5 分片上传：重复内容自动秒传；中断后重跑脚本自动续传
- 仅支持 jpg / jpeg / png / webp / gif / svg

用法（在项目根目录）：
    python scripts/upload_folder.py
    python scripts/upload_folder.py --folder TestImg --base http://127.0.0.1:8000
    python scripts/upload_folder.py --username KSaMar --password 123456
"""
import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = 'http://127.0.0.1:8000'
CHUNK_SIZE = 4 * 1024 * 1024
ALLOWED_EXTENSIONS = {'gif', 'jpeg', 'jpg', 'png', 'svg', 'webp'}
BOUNDARY = '----image-atom-upload'


def request_json(method: str, url: str, payload=None, token: str | None = None,
                 raw_body: bytes | None = None, headers: dict | None = None):
    data = None
    req_headers = dict(headers or {})
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
        req_headers['Content-Type'] = 'application/json'
    if raw_body is not None:
        data = raw_body
    if token:
        req_headers['Authorization'] = f'Bearer {token}'
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as err:
        body = err.read()
        try:
            return err.code, json.loads(body)
        except json.JSONDecodeError:
            return err.code, {'message': body.decode('utf-8', errors='ignore')}


def login(base: str, username: str, password: str) -> str:
    status, result = request_json(
        'POST', f'{base}/api/auth/login',
        {'username': username, 'password': password},
    )
    if status != 200 or result.get('code') != 0:
        raise SystemExit(f"登录失败: {result.get('message')}")
    return result['data']['accessToken']


def md5_of_file(path: Path) -> str:
    digest = hashlib.md5()
    with open(path, 'rb') as f:
        while chunk := f.read(2 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def upload_chunk(base_url: str, token: str, md5: str, index: int, data: bytes):
    body = (
        f'--{BOUNDARY}\r\n'
        f'Content-Disposition: form-data; name="md5"\r\n\r\n{md5}\r\n'
        f'--{BOUNDARY}\r\n'
        f'Content-Disposition: form-data; name="index"\r\n\r\n{index}\r\n'
        f'--{BOUNDARY}\r\n'
        f'Content-Disposition: form-data; name="file"; filename="chunk-{index}"\r\n'
        f'Content-Type: application/octet-stream\r\n\r\n'
    ).encode('utf-8') + data + f'\r\n--{BOUNDARY}--\r\n'.encode('utf-8')
    return request_json(
        'POST', f'{base_url}/api/upload/chunk', raw_body=body, token=token,
        headers={'Content-Type': f'multipart/form-data; boundary={BOUNDARY}'},
    )


def upload_file(token: str, path: Path, category: str, base_url: str) -> str:
    content = path.read_bytes()
    md5 = hashlib.md5(content).hexdigest()
    size = len(content)
    total_chunks = max(1, -(-size // CHUNK_SIZE))

    _, init_result = request_json(
        'POST', f'{base_url}/api/upload/init',
        {'md5': md5, 'filename': path.name, 'size': size, 'totalChunks': total_chunks},
        token=token,
    )
    if init_result.get('code') != 0:
        return f"跳过: {init_result.get('message')}"
    if init_result['data']['instant']:
        return '秒传（内容已存在）'

    uploaded = set(init_result['data'].get('uploadedChunks') or [])
    for index in range(total_chunks):
        if index in uploaded:
            continue
        chunk = content[index * CHUNK_SIZE:(index + 1) * CHUNK_SIZE]
        status, chunk_result = upload_chunk(base_url, token, md5, index, chunk)
        if status != 200 or chunk_result.get('code') != 0:
            return f"失败: 分片 {index} -> {chunk_result.get('message')}"

    _, complete_result = request_json(
        'POST', f'{base_url}/api/upload/complete',
        {'md5': md5, 'filename': path.name, 'size': size,
         'tags': [], 'category': category},
        token=token,
    )
    if complete_result.get('code') != 0:
        return f"失败: {complete_result.get('message')}"
    image = complete_result['data']['image']
    return f"完成: {image['format']} {image['width']}x{image['height']} -> {image['category']}"


def main() -> None:
    parser = argparse.ArgumentParser(description='批量上传表情包（子目录名=分类）')
    parser.add_argument('--base', default=BASE, help='服务地址，默认 http://127.0.0.1:8000')
    parser.add_argument('--folder', default='TestImg', help='图片根目录，默认 TestImg')
    parser.add_argument('--username', default='KSaMar', help='登录用户名')
    parser.add_argument('--password', default='123456', help='登录密码')
    args = parser.parse_args()

    root = Path(args.folder)
    if not root.is_dir():
        raise SystemExit(f'目录不存在: {root.resolve()}')

    token = login(args.base, args.username, args.password)

    targets: list[tuple[Path, str]] = []
    for item in sorted(root.iterdir()):
        if item.is_dir():
            targets.extend(
                (file, item.name) for file in sorted(item.iterdir()) if file.is_file()
            )
        elif item.is_file():
            targets.append((item, ''))

    success = skipped = failed = 0
    for path, category in targets:
        if path.suffix.lower().lstrip('.') not in ALLOWED_EXTENSIONS:
            print(f'  [忽略] {path.name}（不支持的格式）')
            skipped += 1
            continue
        label = f'[{category or "未分类"}] {path.name}'
        try:
            result = upload_file(token, path, category, args.base)
        except Exception as error:  # noqa: BLE001 网络异常继续传后面的
            result = f'失败: {error}'
        print(f'  {label} => {result}')
        if result.startswith(('完成', '秒传', '跳过')):
            success += 1
        else:
            failed += 1

    print(f'\n汇总: 成功 {success}，忽略 {skipped}，失败 {failed}，共 {len(targets)} 个文件')
    if failed:
        sys.exit(1)


if __name__ == '__main__':
    main()
