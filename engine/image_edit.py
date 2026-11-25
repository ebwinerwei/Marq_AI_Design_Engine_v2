"""Encode a registered site composite, its protection mask and depth reference."""
import base64
import secrets
import struct


def png(body, field):
    value = body.get(field, '')
    if not isinstance(value, str) or not value.startswith('data:image/png;base64,'):
        raise ValueError(field + ' のPNG画像が必要です')
    raw = base64.b64decode(value.split(',', 1)[1], validate=True)
    if raw[:16] != bytes.fromhex('89504e470d0a1a0a0000000d49484452') or len(raw) < 33:
        raise ValueError('PNGヘッダーが不正です')
    return raw, struct.unpack('>II', raw[16:24])


def edit_request(model, body):
    boundary = secrets.token_hex(18)
    parts = []

    def append(name, value, filename=None):
        header = f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"'
        if filename:
            header += f'; filename="{filename}"\r\nContent-Type: image/png'
        parts.extend([(header+'\r\n\r\n').encode(), value, b'\r\n'])

    append('model', model.encode())
    append('size', b'1536x1024')
    prompt = ('画像1は配置確定済みの建物と現況写真、画像2は元の現況、画像3は同視点の深度。'
              '画像1の構図、余白と建物を維持。道路・周辺既存建物を維持し、指定された時間帯の光、'
              '地面の接触影、植栽と環境を統合する。深度画像を完成画に描かない。'
              + str(body.get('environment','')) + ' ' + str(body.get('intent',''))[:1500])
    append('prompt', prompt.encode())
    for field in ('composite','background','depth','mask'):
        raw, size = png(body, field)
        if size != (1536, 1024) or (field == 'mask' and raw[25] != 6):
            raise ValueError('位置合わせ済みの1536×1024 PNGと透過マスクが必要です')
        append('mask' if field=='mask' else 'image[]', raw, field+'.png')
    parts.append(f'--{boundary}--\r\n'.encode())
    return b''.join(parts), 'multipart/form-data; boundary='+boundary
