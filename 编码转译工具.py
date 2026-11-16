# -*- coding: utf-8 -*-
"""
常用编码转译工具
================
离线运行的 Windows 桌面小工具：
  · 输入：粘贴文本 / 选择文件
  · 转译：Base64、URL、Hex、Unicode、HTML 实体、JSON 转义、哈希、文本编码识别
  · 输出：文本直接回显；二进制自动识别类型，按对应扩展名智能保存

只依赖 Python 3 标准库（tkinter）。不联网。
"""

import base64
import binascii
import hashlib
import html as html_lib
import io
import json
import os
import re
import sys
import time
import traceback
import zipfile
from urllib.parse import quote, quote_plus, unquote_to_bytes

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_TITLE = '常用编码转译'
APP_VER = '1.0'
DISPLAY_LIMIT = 200_000
PREVIEW_LIMIT = 128 * 1024
DETECT_LIMIT = 64 * 1024

BG = '#eef2f8'
CARD = '#ffffff'
INK = '#17213a'
INK2 = '#5a6784'
INK3 = '#8c97ad'
LINE = '#dbe3f0'
BRAND = '#2158d8'
BRAND_DARK = '#173f9e'
GREEN = '#0f8a52'
RED = '#c0392b'
AMBER = '#a56a00'

FONT = ('Microsoft YaHei UI', 10)
FONT_SM = ('Microsoft YaHei UI', 9)
FONT_BOLD = ('Microsoft YaHei UI', 10, 'bold')
MONO = ('Consolas', 10)
MONO_SM = ('Consolas', 9)

UI_SCALE = 1.0


def px(n):
    return max(1, int(round(n * UI_SCALE)))


class ToolError(Exception):
    pass


class Source:
    def __init__(self, kind='text', text='', raw=b'', filename='', path='',
                 encoding='UTF-8', is_binary=False):
        self.kind = kind
        self.text = text
        self.raw = raw
        self.filename = filename
        self.path = path
        self.encoding = encoding
        self.is_binary = is_binary

    @property
    def display_name(self):
        return self.filename or '粘贴文本'


class Result:
    def __init__(self, text=None, data=None, ext='txt', kind='文本', note='', suffix=''):
        self.text = text
        self.data = data
        self.ext = ext
        self.kind = kind
        self.note = note
        self.suffix = suffix

    @property
    def binary(self):
        return self.data is not None


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------

def human_size(n):
    if n < 1024:
        return '%d B' % n
    v = float(n)
    for unit in ('KB', 'MB', 'GB', 'TB'):
        v /= 1024.0
        if v < 1024 or unit == 'TB':
            if v < 100:
                return '%.1f %s' % (v, unit)
            return '%.0f %s' % (v, unit)
    return '%d B' % n


def text_score(s):
    """粗略判断一串字符是不是正常文本（0~1）。"""
    if not s:
        return 1.0
    n = min(len(s), 20000)
    bad = 0
    for ch in s[:n]:
        o = ord(ch)
        if o < 32 and ch not in '\r\n\t\f':
            bad += 1
        elif 0xE000 <= o <= 0xF8FF:
            bad += 1
        elif 0xFFF0 <= o <= 0xFFFF:
            bad += 1
    return 1.0 - (bad / float(n))


def decode_head(raw):
    """解码文件开头；允许结尾是半个多字节字符。"""
    for trim in range(4):
        part = raw[:len(raw) - trim] if trim else raw
        if not part:
            continue
        try:
            return detect_encoding(part)
        except ToolError:
            continue
    raise ToolError('无法识别为文本')


def detect_encoding(raw):
    if not raw:
        raise ToolError('文件是空的')
    if raw.startswith(b'\xef\xbb\xbf'):
        try:
            return raw[3:].decode('utf-8'), 'UTF-8 (BOM)'
        except UnicodeDecodeError:
            raise ToolError('UTF-8 BOM 之后不是合法的 UTF-8 内容')
    if raw.startswith(b'\xff\xfe') or raw.startswith(b'\xfe\xff'):
        try:
            return raw.decode('utf-16'), 'UTF-16'
        except UnicodeDecodeError:
            raise ToolError('UTF-16 解码失败')

    nul = raw.count(b'\x00')
    if nul > max(4, len(raw) // 200):
        raise ToolError('文件含大量空字节，看起来是二进制文件')

    for enc, label in (('utf-8', 'UTF-8'), ('gb18030', 'GB18030/GBK'), ('big5', 'Big5')):
        try:
            s = raw.decode(enc)
        except UnicodeDecodeError:
            continue
        if text_score(s) >= 0.98:
            return s, label
    raise ToolError('无法识别为 UTF-8 / GBK / Big5 文本')


def looks_binary(raw):
    if not raw:
        return False
    if raw.startswith((b'\xef\xbb\xbf', b'\xff\xfe', b'\xfe\xff')):
        return False
    chunk = raw[:DETECT_LIMIT]
    for trim in range(4):
        part = chunk[:len(chunk) - trim] if trim else chunk
        if not part:
            continue
        try:
            detect_encoding(part)
            return False
        except ToolError:
            continue
    return True


def try_decode_utf8(data):
    if not data:
        return None
    if b'\x00' in data[:8192]:
        return None
    try:
        s = data.decode('utf-8')
    except UnicodeDecodeError:
        return None
    if text_score(s) < 0.98:
        return None
    return s


def safe_text(s):
    try:
        s.encode('utf-8')
        return s
    except UnicodeEncodeError:
        return s.encode('utf-8', 'replace').decode('utf-8')


def hex_preview(data, limit=512):
    data = data[:limit]
    lines = []
    for off in range(0, len(data), 16):
        chunk = data[off:off + 16]
        hexs = ' '.join('%02X' % b for b in chunk)
        chars = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        lines.append('%08X  %-47s  %s' % (off, hexs, chars))
    return '\n'.join(lines)


MIME_BY_EXT = {
    'png': 'image/png',
    'jpg': 'image/jpeg',
    'gif': 'image/gif',
    'webp': 'image/webp',
    'bmp': 'image/bmp',
    'ico': 'image/x-icon',
    'tif': 'image/tiff',
    'pdf': 'application/pdf',
    'zip': 'application/zip',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'mp3': 'audio/mpeg',
    'mp4': 'video/mp4',
    'wav': 'audio/wav',
    'json': 'application/json',
}


def zip_office_ext(data):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = set(z.namelist())
    except Exception:
        return None
    if 'word/document.xml' in names:
        return 'docx'
    if 'xl/workbook.xml' in names:
        return 'xlsx'
    if 'ppt/presentation.xml' in names:
        return 'pptx'
    if 'AndroidManifest.xml' in names:
        return 'apk'
    if 'META-INF/MANIFEST.MF' in names:
        return 'jar'
    return None


def sniff_bytes(d):
    """按文件头识别常见格式，返回 (扩展名, 中文说明)。"""
    n = len(d)
    if n == 0:
        return 'bin', '空数据'
    if d.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png', 'PNG 图片'
    if d.startswith(b'\xff\xd8\xff'):
        return 'jpg', 'JPEG 图片'
    if d.startswith((b'GIF87a', b'GIF89a')):
        return 'gif', 'GIF 图片'
    if d.startswith(b'RIFF') and d[8:12] == b'WEBP':
        return 'webp', 'WebP 图片'
    if d.startswith(b'%PDF-'):
        return 'pdf', 'PDF 文档'
    if d.startswith(b'PK\x03\x04') or d.startswith(b'PK\x05\x06'):
        office = zip_office_ext(d)
        if office == 'docx':
            return 'docx', 'Word 文档 (docx)'
        if office == 'xlsx':
            return 'xlsx', 'Excel 工作簿 (xlsx)'
        if office == 'pptx':
            return 'pptx', 'PowerPoint 演示文稿 (pptx)'
        if office == 'apk':
            return 'apk', 'Android 安装包 (apk)'
        if office == 'jar':
            return 'jar', 'Java 包 (jar)'
        return 'zip', 'ZIP 压缩包'
    if d.startswith(b'Rar!\x1a\x07'):
        return 'rar', 'RAR 压缩包'
    if d.startswith(b'7z\xbc\xaf\x27\x1c'):
        return '7z', '7-Zip 压缩包'
    if d.startswith(b'\x1f\x8b'):
        return 'gz', 'GZip 压缩包'
    if d.startswith(b'BZh'):
        return 'bz2', 'BZip2 压缩包'
    if d.startswith(b'\xfd7zXZ\x00'):
        return 'xz', 'XZ 压缩包'
    if d.startswith(b'MZ'):
        return 'exe', 'Windows 可执行文件'
    if d.startswith(b'\x7fELF'):
        return 'elf', 'Linux 可执行文件'
    if d.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'):
        return 'doc', '旧版 Office 文档'
    if d.startswith(b'SQLite format 3\x00'):
        return 'sqlite', 'SQLite 数据库'
    if d.startswith(b'\xca\xfe\xba\xbe'):
        return 'class', 'Java Class'
    if d.startswith(b'\x00asm'):
        return 'wasm', 'WebAssembly'
    if d.startswith(b'ID3') or d[:2] in (b'\xff\xfb', b'\xff\xf3', b'\xff\xf2'):
        return 'mp3', 'MP3 音频'
    if d.startswith(b'fLaC'):
        return 'flac', 'FLAC 音频'
    if d.startswith(b'OggS'):
        return 'ogg', 'Ogg 音频'
    if d.startswith(b'RIFF') and d[8:12] == b'WAVE':
        return 'wav', 'WAV 音频'
    if d.startswith(b'RIFF') and d[8:12] == b'AVI ':
        return 'avi', 'AVI 视频'
    if n >= 12 and d[4:8] == b'ftyp':
        brand = d[8:12]
        if brand == b'avif':
            return 'avif', 'AVIF 图片'
        if brand in (b'heic', b'heix', b'mif1'):
            return 'heic', 'HEIC 图片'
        if brand in (b'M4A ', b'M4B '):
            return 'm4a', 'M4A 音频'
        if brand == b'qt  ':
            return 'mov', 'QuickTime 视频'
        return 'mp4', 'MP4 视频'
    if d.startswith(b'\x1aE\xdf\xa3'):
        return 'mkv', 'MKV/WebM 视频'
    if d.startswith(b'BM'):
        return 'bmp', 'BMP 图片'
    if d.startswith(b'\x00\x00\x01\x00'):
        return 'ico', 'ICO 图标'
    if d.startswith((b'II*\x00', b'MM\x00*')):
        return 'tif', 'TIFF 图片'
    if d.startswith(b'0\x82') or d.startswith(b'0\x81'):
        return 'der', 'DER / ASN.1 数据'

    if b'\x00' not in d[:4096]:
        try:
            t = d[:65536].decode('utf-8')
            if text_score(t) >= 0.95:
                return 'txt', 'UTF-8 文本'
        except UnicodeDecodeError:
            pass
    return 'bin', '未知二进制'


def smart_text_ext(text):
    s = text.lstrip('﻿ \t\r\n')
    if not s:
        return 'txt'
    if s[0] in '{[' and len(text) <= 5_000_000:
        try:
            json.loads(text)
            return 'json'
        except Exception:
            pass
    low = s[:200].lower()
    if low.startswith('<?xml'):
        return 'xml'
    if low.startswith('<!doctype html') or low.startswith('<html'):
        return 'html'
    return 'txt'


def bytes_result(data, kind_hint='解码结果'):
    if not data:
        raise ToolError('解码结果为空')
    t = try_decode_utf8(data)
    if t is not None:
        return Result(text=t, ext=smart_text_ext(t), kind='文本（自动识别）')
    ext, label = sniff_bytes(data)
    if label == '未知二进制':
        label = kind_hint
    return Result(data=data, ext=ext, kind=label, note=hex_preview(data, 64))


def unicode_escape(s):
    out = []
    for ch in s:
        o = ord(ch)
        if o < 0x80:
            out.append(ch)
        elif o <= 0xFFFF:
            out.append('\\u%04x' % o)
        else:
            o2 = o - 0x10000
            out.append('\\u%04x\\u%04x' % (0xD800 + (o2 >> 10), 0xDC00 + (o2 & 0x3FF)))
    return ''.join(out)


def unicode_unescape(s):
    s = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), s)
    s = re.sub(r'\\U([0-9a-fA-F]{8})', lambda m: chr(int(m.group(1), 16)), s)
    s = re.sub(r'\\x([0-9a-fA-F]{2})', lambda m: chr(int(m.group(1), 16)), s)
    try:
        s = s.encode('utf-16-le', 'surrogatepass').decode('utf-16-le')
    except Exception:
        pass
    s = s.replace('\\n', '\n').replace('\\r', '\r').replace('\\t', '\t')
    s = s.replace('\\/', '/').replace('\\\\', '\\')
    return safe_text(s)


def is_meaningful(data):
    if not data:
        return False
    if try_decode_utf8(data) is not None:
        return True
    ext, _ = sniff_bytes(data)
    return ext not in ('bin', 'txt')


# ---------------------------------------------------------------------------
# 转译操作
# ---------------------------------------------------------------------------

def op_b64_encode(src, opts):
    data = src.raw if src.kind == 'file' else src.text.encode('utf-8')
    text = base64.b64encode(data).decode('ascii')
    if opts.get('data_uri'):
        if try_decode_utf8(data) is not None:
            mime = 'text/plain;charset=utf-8'
        else:
            ext, _ = sniff_bytes(data)
            mime = MIME_BY_EXT.get(ext, 'application/octet-stream')
        text = 'data:%s;base64,%s' % (mime, text)
    return Result(text=text, ext='txt', kind='Base64 文本', suffix='.base64')


def op_b64_decode(src, opts):
    t = src.text.strip()
    t = re.sub(r'-----BEGIN [^-]+-----|-----END [^-]+-----', '', t)
    m = re.match(r'^data:([^;,]*)((?:;[^,]*)*),(.*)$', t, re.S | re.I)
    if m and 'base64' in (m.group(2) or '').lower():
        t = m.group(3)
    t = t.strip().strip('"\'')
    t = re.sub(r'\s+', '', t)
    t = t.replace('-', '+').replace('_', '/')
    if not t:
        raise ToolError('没有可解码的 Base64 内容')
    if len(t) % 4 == 1:
        raise ToolError('Base64 长度不合法，内容可能被截断')
    t += '=' * (-len(t) % 4)
    try:
        data = base64.b64decode(t, validate=True)
    except (binascii.Error, ValueError) as e:
        raise ToolError('Base64 解码失败：%s' % e)
    return bytes_result(data, 'Base64 解码结果')


def op_url_encode(src, opts):
    if opts.get('form_url'):
        text = quote_plus(src.text, safe='')
        return Result(text=text, ext='txt', kind='URL 表单编码', suffix='.url')
    text = quote(src.text, safe='')
    return Result(text=text, ext='txt', kind='URL 编码文本', suffix='.url')


def op_url_decode(src, opts):
    t = src.text
    if opts.get('form_url'):
        t = t.replace('+', ' ')
    if re.search(r'%u[0-9a-fA-F]{4}', t):
        t = re.sub(r'%u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), t)
    try:
        data = unquote_to_bytes(t)
    except Exception as e:
        raise ToolError('URL 解码失败：%s' % e)
    return bytes_result(data, 'URL 解码结果')


def op_hex_encode(src, opts):
    data = src.raw if src.kind == 'file' else src.text.encode('utf-8')
    return Result(text=binascii.hexlify(data).decode('ascii'),
                  ext='txt', kind='Hex 文本', suffix='.hex')


def op_hex_decode(src, opts):
    t = src.text.strip()
    t = re.sub(r'\\x', '', t)
    t = re.sub(r'0[xX]', '', t)
    t = re.sub(r'[\s,;:|]+', '', t)
    if not t:
        raise ToolError('没有可解码的十六进制内容')
    if re.search(r'[^0-9a-fA-F]', t):
        raise ToolError('含有非十六进制字符，请检查输入')
    if len(t) % 2:
        raise ToolError('十六进制字符数为奇数，无法按字节解码')
    try:
        data = bytes.fromhex(t)
    except ValueError as e:
        raise ToolError('Hex 解码失败：%s' % e)
    return bytes_result(data, 'Hex 解码结果')


def op_unicode_encode(src, opts):
    return Result(text=unicode_escape(src.text), ext='txt',
                  kind='Unicode 转义文本', suffix='.unicode')


def op_unicode_decode(src, opts):
    return Result(text=unicode_unescape(src.text), ext='txt',
                  kind='文本（Unicode 还原）')


def op_html_encode(src, opts):
    return Result(text=html_lib.escape(src.text, quote=True), ext='html',
                  kind='HTML 实体文本', suffix='.html')


def op_html_decode(src, opts):
    return Result(text=html_lib.unescape(src.text), ext='txt',
                  kind='文本（HTML 实体还原）')


def op_json_escape(src, opts):
    text = json.dumps(src.text, ensure_ascii=False)[1:-1]
    return Result(text=text, ext='txt', kind='JSON 转义文本', suffix='.json')


def op_json_unescape(src, opts):
    t = src.text.strip()
    try:
        if len(t) >= 2 and t[0] == '"' and t[-1] == '"':
            out = json.loads(t)
        else:
            out = json.loads('"' + t + '"')
        if not isinstance(out, str):
            out = json.dumps(out, ensure_ascii=False)
    except Exception:
        out = unicode_unescape(t)
    return Result(text=safe_text(out), ext='txt', kind='文本（JSON 反转义）')


def op_hash(src, algo):
    data = src.raw if src.kind == 'file' else src.text.encode('utf-8')
    digest = hashlib.new(algo, data).hexdigest()
    return Result(text=digest, ext='txt', kind=algo.upper() + ' 摘要', suffix='.' + algo)


def op_decode_text_file(src, opts):
    if src.kind != 'file':
        raise ToolError('这个操作需要选择文件；粘贴文本本身就是 Unicode 文本')
    text, label = detect_encoding(src.raw)
    return Result(text=text, ext=smart_text_ext(text),
                  kind='文本（%s → UTF-8）' % label, suffix='.utf8')


def op_encode_gbk(src, opts):
    if src.kind != 'text':
        raise ToolError('这个操作针对粘贴文本，请切换到「粘贴文本」页')
    try:
        data = src.text.encode('gb18030')
    except UnicodeEncodeError as e:
        raise ToolError('有字符无法用 GBK/GB18030 表示：%s' % e)
    return Result(data=data, ext='txt', kind='GBK/GB18030 编码字节',
                  note=hex_preview(data), suffix='.gbk')


# 哈希摘要的字节长度 → 算法名；智能识别命中后直接说明「不可解码」，不再吐 .bin
HASH_BY_LEN = {16: 'MD5', 20: 'SHA-1', 32: 'SHA-256', 64: 'SHA-512'}


def detect_hash(h, t):
    """h 是去掉 0x 前缀的纯 hex，t 是原始输入。像摘要就返回算法名，否则空串。

    只有「整串不带空格/换行/0x、长度对得上、解出来也不像文本或已知文件头」
    才算摘要；带分隔符的更像 hex dump，交给正常 Hex 解码。
    """
    if len(h) != len(t) or len(h) % 2:
        return ''
    name = HASH_BY_LEN.get(len(h) // 2)
    if not name:
        return ''
    try:
        data = bytes.fromhex(h)
    except ValueError:
        return ''
    if is_meaningful(data):
        return ''
    return name


# 常见弱口令底座。运行时再拼数字/符号后缀与大小写变体，不必把哈希写死进文件。
COMMON_PASSWORDS = """
123456 password 12345678 qwerty 123456789 12345 1234 111111 1234567 dragon
123123 baseball abc123 football monkey letmein shadow master 666666 qwertyuiop
123321 mustang 1234567890 michael 654321 superman 1qaz2wsx 7777777 121212
000000 qazwsx 123qwe killer trustno1 jordan jennifer zxcvbnm asdfgh hunter
buster soccer harley batman andrew tigger sunshine iloveyou 2000 charlie
robert thomas hockey ranger daniel starwars klaster 112233 george computer
michelle jessica pepper 1111 zxcvbn 555555 11111111 131313 freedom 777777
pass maggie 159753 aaaaaa ginger princess joshua cheese amanda summer love
ashley nicole chelsea biteme matthew access yankees 987654321 dallas austin
thunder taylor matrix william corvette hello martin heather secret merlin
diamond 1234qwer gfhjkm hammer silver 222222 88888888 anthony justin test
bailey q1w2e3r4t5 patrick internet scooter orange 11111 golfer cookie richard
samantha bigdog guitar jackson whatever mickey chicken sparky snoopy maverick
phoenix camaro sexy peanut morgan welcome falcon cowboy ferrari samsung andrea
smokey steelers joseph mercedes dakota arsenal eagles melissa boomer spider
nascar monster tigers yellow admin root toor passw0rd password1 p@ssw0rd
1q2w3e4r 1qazxsw2 qwerty123 qwerty1 password123 admin123 root123 test123
abc12345 iloveyou1 princess1 sunshine1 football1 baseball1 superman1 starwars1
abcdef abcdefg abcdefgh abcd1234 1qaz@wsx qweasdzxc zaq12wsx 12344321
1234554321 11223344 5201314 woaini woaini1314 520520 1314520 7758521 31415926
123456a a123456 a123456789 1a2b3c qazwsxedc asdfghjkl zxcvbnm123 9876543210
102030 123654 456789 789456 159357 147258 258258 369369 741852963 963852741
987654 qwe123asd asd123qwe 123qweasd zxc123asd 1qaz2wsx3edc chocolate jasmine
chicken barbie flower lovely babygirl angel hello123 welcome1 welcome123
master123 shadow123 monkey123 dragon123 service support backup temp default
guest user administrator operator letmein123 changeme changeme123 123abc
abc1234 1111111 0000000 qwertyui qwerty12 asdf1234 zxcv1234 1q2w3e
password12 admin888 adminadmin rootroot testtest 123456789a abcabc abcd1234
"""

_CRACK_CACHE = {}


def _crack_candidates():
    """底座词 + 常见后缀 / 大小写变体，去重后产出。"""
    seen = set()
    suffixes = ('', '1', '12', '123', '1234', '12345', '123456', '!', '@', '2024', '2025', '2026')
    for w in COMMON_PASSWORDS.split():
        for form in (w, w.capitalize(), w.upper()):
            for s in suffixes:
                c = form + s
                if c not in seen:
                    seen.add(c)
                    yield c


def crack_hash(target_hex, algo, max_digits=6):
    """本地反查：常见弱口令字典 + 位数以内的纯数字。命中返回原文，否则 None。"""
    key = (algo, target_hex, max_digits)
    if key in _CRACK_CACHE:
        return _CRACK_CACHE[key]
    target = target_hex.lower()
    try:
        func = getattr(hashlib, algo.lower().replace('-', ''))
    except AttributeError:
        return None

    def hit(s):
        return func(s.encode('utf-8')).hexdigest() == target

    found = None
    for cand in _crack_candidates():
        if hit(cand):
            found = cand
            break
    if found is None:
        limit = 10 ** max_digits
        for i in range(limit):
            s = str(i)
            if hit(s):
                found = s
                break
            padded = s.zfill(max_digits)
            if padded != s and hit(padded):
                found = padded
                break
    _CRACK_CACHE[key] = found
    return found


def hash_result(h, name):
    plain = crack_hash(h, name)
    if plain is not None:
        text = (
            '%s 摘要 · %d 字节 · 本地反查命中\n'
            '%s\n\n'
            '原文是：%s\n\n'
            '哈希是单向的，没法像 Base64 那样直接还原；这条是从本地字典'
            '（常见弱口令 + 6 位以内数字）里算出来对上的，全程离线。\n'
            '要拿这 %d 字节原始数据：手动选「Hex 解码」。'
            % (name, len(h) // 2, h.upper(), plain, len(h) // 2)
        )
        return Result(text=text, ext='txt', kind='%s · 已还原原文' % name)

    text = (
        '%s 摘要 · %d 字节\n'
        '%s\n\n'
        '本地字典（常见弱口令 + 6 位以内数字）没查到原文。\n'
        '哈希是单向的，没法直接还原——查不到只说明原文不在这范围内，'
        '不代表它没有原文。\n\n'
        '想验证猜到原文：切到「%s 摘要」模式输入它，'
        '算出来一致就说明是它。\n'
        '要拿这 %d 字节原始数据：手动选「Hex 解码」。'
        % (name, len(h) // 2, h.upper(), name, len(h) // 2)
    )
    return Result(text=text, ext='txt', kind='%s 摘要（未反查到）' % name)


def op_hash_crack(src, opts):
    if src.kind != 'text':
        raise ToolError('这个操作针对粘贴的哈希值，请切换到「粘贴文本」页')
    t = re.sub(r'\s+', '', src.text.strip()).lower()
    t = re.sub(r'^0x', '', t)
    if not t or not re.fullmatch(r'[0-9a-f]+', t):
        raise ToolError('请粘贴一串十六进制哈希值')
    name = HASH_BY_LEN.get(len(t) // 2)
    if not name:
        raise ToolError('长度 %d 位对不上已知摘要（MD5 32 位 / SHA-1 40 位 / '
                        'SHA-256 64 位 / SHA-512 128 位）' % len(t))
    return hash_result(t, name)


def op_smart(src, opts):
    t = src.text.strip()
    if not t:
        raise ToolError('内容为空')

    if re.match(r'^data:[^,]*,', t, re.I):
        try:
            return op_b64_decode(src, opts)
        except ToolError:
            pass

    if re.search(r'\\u[0-9a-fA-F]{4}', t):
        out = unicode_unescape(t)
        if out != t:
            return Result(text=out, ext='txt', kind='文本（Unicode 还原）')

    if len(re.findall(r'%[0-9a-fA-F]{2}', t)) >= 2 or re.search(r'%u[0-9a-fA-F]{4}', t):
        try:
            return op_url_decode(src, opts)
        except ToolError:
            pass

    if re.search(r'&(?:#\d+|#x[0-9a-fA-F]+|[a-zA-Z]+);', t):
        out = html_lib.unescape(t)
        if out != t:
            return Result(text=out, ext='txt', kind='文本（HTML 实体还原）')

    compact = re.sub(r'\s+', '', t)
    h = re.sub(r'(?:0[xX])', '', compact)
    if len(h) >= 8 and len(h) % 2 == 0 and re.fullmatch(r'[0-9a-fA-F]+', h):
        name = detect_hash(h, t)
        if name:
            return hash_result(h, name)
        try:
            data = bytes.fromhex(h)
            if is_meaningful(data) or len(h) >= 16:
                return bytes_result(data, 'Hex 解码结果')
        except Exception:
            pass

    b = compact.strip('"\'')
    b = b.replace('-', '+').replace('_', '/')
    if len(b) >= 8 and re.fullmatch(r'[A-Za-z0-9+/]+={0,2}', b):
        try:
            data = base64.b64decode(b + '=' * (-len(b) % 4), validate=True)
            if is_meaningful(data):
                return bytes_result(data, 'Base64 解码结果')
        except Exception:
            pass

    raise ToolError('未能自动识别编码类型，请手动选择具体操作')


TEXT_OPS = {
    'url_enc', 'url_dec', 'uni_enc', 'uni_dec',
    'html_enc', 'html_dec', 'json_enc', 'json_dec', 'smart',
}


def run_op(op, src, opts):
    if src.kind == 'file' and src.is_binary and op in TEXT_OPS:
        raise ToolError('这个操作只适用于文本，但所选文件看起来是二进制。'
                        '请改用 Base64 / Hex / 哈希，或选择文本文件。')

    if op == 'b64_enc':
        return op_b64_encode(src, opts)
    if op == 'b64_dec':
        return op_b64_decode(src, opts)
    if op == 'url_enc':
        return op_url_encode(src, opts)
    if op == 'url_dec':
        return op_url_decode(src, opts)
    if op == 'hex_enc':
        return op_hex_encode(src, opts)
    if op == 'hex_dec':
        return op_hex_decode(src, opts)
    if op == 'uni_enc':
        return op_unicode_encode(src, opts)
    if op == 'uni_dec':
        return op_unicode_decode(src, opts)
    if op == 'html_enc':
        return op_html_encode(src, opts)
    if op == 'html_dec':
        return op_html_decode(src, opts)
    if op == 'json_enc':
        return op_json_escape(src, opts)
    if op == 'json_dec':
        return op_json_unescape(src, opts)
    if op in ('md5', 'sha1', 'sha256', 'sha512'):
        return op_hash(src, op)
    if op == 'hash_crack':
        return op_hash_crack(src, opts)
    if op == 'gbk_dec':
        return op_decode_text_file(src, opts)
    if op == 'gbk_enc':
        return op_encode_gbk(src, opts)
    if op == 'smart':
        return op_smart(src, opts)
    raise ToolError('未知操作：%s' % op)


OP_ITEMS = [
    ('smart', '智能识别（自动解码）',
     '自动识别 Data URI / Unicode / URL / HTML / Hex / Base64 并解码，识别不了会提示手动选择。'),
    ('b64_enc', 'Base64 编码',
     '文本按 UTF-8、文件按原始字节编码；可勾选生成 Data URI 前缀。'),
    ('b64_dec', 'Base64 解码',
     '支持标准 / URL-safe Base64、data:...;base64, 前缀、PEM 头尾和缺失填充。'),
    ('url_enc', 'URL 编码',
     '把文本编码成 %XX 形式；勾选表单模式时空格变成 +。'),
    ('url_dec', 'URL 解码',
     '还原 %XX 与 %uXXXX；勾选表单模式时 + 还原成空格。'),
    ('hex_enc', 'Hex 编码',
     '文本按 UTF-8、文件按原始字节转成十六进制文本。'),
    ('hex_dec', 'Hex 解码',
     '支持空格、换行、逗号、0x 前缀和 \\x 前缀。'),
    ('uni_enc', 'Unicode 转义',
     '非 ASCII 字符转成 \\uXXXX，emoji 自动使用代理对。'),
    ('uni_dec', 'Unicode 还原',
     '还原 \\uXXXX / \\UXXXXXXXX / \\xXX 以及常见转义。'),
    ('html_enc', 'HTML 实体编码',
     '转义 & < > " \' 五个字符。'),
    ('html_dec', 'HTML 实体解码',
     '还原 &amp; &lt; &#x...; 等 HTML 实体。'),
    ('json_enc', 'JSON 字符串转义',
     '按 JSON 字符串规则转义引号、反斜杠和控制字符。'),
    ('json_dec', 'JSON 字符串反转义',
     '还原 JSON 字符串里的转义，自动去掉首尾引号。'),
    ('md5', 'MD5 摘要',
     '文本按 UTF-8、文件按原始字节计算 MD5。'),
    ('sha1', 'SHA-1 摘要',
     '文本按 UTF-8、文件按原始字节计算 SHA-1。'),
    ('sha256', 'SHA-256 摘要',
     '文本按 UTF-8、文件按原始字节计算 SHA-256。'),
    ('sha512', 'SHA-512 摘要',
     '文本按 UTF-8、文件按原始字节计算 SHA-512。'),
    ('hash_crack', '哈希反查（常见弱口令）',
     '粘一串 MD5 / SHA-1 / SHA-256 / SHA-512 哈希，用本地字典（常见弱口令 + 6 位以内数字）还原原文，全程离线。'),
    ('gbk_dec', '文本编码识别（文件）',
     '识别文件的 UTF-8 / GBK / Big5 / UTF-16 编码，输出为 UTF-8 文本。'),
    ('gbk_enc', '文本 → GBK 字节',
     '把粘贴的文本编码成 GBK/GB18030 字节，适合生成旧系统可读文件。'),
]


# ---------------------------------------------------------------------------
# 界面
# ---------------------------------------------------------------------------

def enable_dpi_awareness():
    if sys.platform != 'win32':
        return 96
    try:
        from ctypes import windll
        try:
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                windll.user32.SetProcessDPIAware()
            except Exception:
                pass
        try:
            return int(windll.user32.GetDpiForSystem())
        except Exception:
            return 96
    except Exception:
        return 96


def setup_style(root):
    style = ttk.Style(root)
    try:
        style.theme_use('clam')
    except tk.TclError:
        pass

    style.configure('.', background=BG, foreground=INK, font=FONT)
    style.configure('TFrame', background=BG)
    style.configure('TLabel', background=BG, foreground=INK)
    style.configure('TButton', font=FONT, padding=(px(14), px(7)),
                    background='#f4f7fc', foreground=INK,
                    bordercolor=LINE, lightcolor=LINE, darkcolor=LINE,
                    relief='flat', focusthickness=0)
    style.map('TButton',
              background=[('active', '#e6edfa'), ('pressed', '#dce6f8')])
    style.configure('Accent.TButton', font=('Microsoft YaHei UI', 10, 'bold'),
                    padding=(px(20), px(8)), background=BRAND,
                    foreground='#ffffff', bordercolor=BRAND,
                    lightcolor=BRAND, darkcolor=BRAND)
    style.map('Accent.TButton',
              background=[('active', BRAND_DARK), ('disabled', '#a6b9e4')],
              foreground=[('disabled', '#f2f5fb')])
    style.configure('Soft.TButton', background='#eaf1ff', foreground=BRAND,
                    padding=(px(12), px(6)), bordercolor='#c9d9f8',
                    lightcolor='#c9d9f8', darkcolor='#c9d9f8')
    style.map('Soft.TButton', background=[('active', '#dbe6ff')])
    style.configure('TNotebook', background=CARD, borderwidth=0,
                    tabmargins=(0, 0, 0, 0))
    style.configure('TNotebook.Tab', font=FONT, padding=(px(18), px(7)),
                    background='#e7edf8', foreground=INK2, borderwidth=0)
    style.map('TNotebook.Tab',
              background=[('selected', CARD)],
              foreground=[('selected', BRAND)])
    style.configure('TCombobox', padding=(px(8), px(4)),
                    fieldbackground='#fbfcff', background='#f4f7fc',
                    foreground=INK, arrowcolor=INK2,
                    bordercolor=LINE, lightcolor=LINE, darkcolor=LINE)
    style.map('TCombobox',
              fieldbackground=[('readonly', '#fbfcff')],
              selectbackground=[('readonly', '#fbfcff')],
              selectforeground=[('readonly', INK)])
    style.configure('TCheckbutton', background=CARD, foreground=INK2, font=FONT_SM)
    style.map('TCheckbutton', background=[('active', CARD)])
    root.option_add('*TCombobox*Listbox.font', FONT)
    root.option_add('*TCombobox*Listbox.background', CARD)
    root.option_add('*TCombobox*Listbox.foreground', INK)


class App:
    def __init__(self, root):
        self.root = root
        self.last_result = None
        self.last_source = None
        self.last_saved = ''
        self.file_path = ''
        self.file_size = 0
        self.data_uri_var = tk.BooleanVar(value=False)
        self.form_url_var = tk.BooleanVar(value=False)
        self._build()
        self._bind()
        self.root.report_callback_exception = self._report_callback_exception
        self.root.after(120, self.input_text.focus_set)

    # ------------------------------------------------------------------ UI
    def _build(self):
        self.root.title('%s · v%s' % (APP_TITLE, APP_VER))
        self.root.configure(bg=BG)
        setup_style(self.root)

        header = tk.Frame(self.root, bg=BRAND, height=px(78))
        header.pack(fill='x', side='top')
        header.pack_propagate(False)
        head_left = tk.Frame(header, bg=BRAND)
        head_left.pack(side='left', padx=px(22), pady=px(12))
        tk.Label(head_left, text='常用编码转译', bg=BRAND, fg='#ffffff',
                 font=('Microsoft YaHei UI', 17, 'bold')).pack(anchor='w')
        tk.Label(head_left, text='文件 / 文本  ·  编码 / 解码  ·  自动识别文件类型并保存',
                 bg=BRAND, fg='#c6d6ff', font=FONT_SM).pack(anchor='w', pady=(px(2), 0))
        tk.Label(header, text='离线运行\n不联网', bg=BRAND, fg='#d7e3ff',
                 font=FONT_SM, justify='right').pack(side='right', padx=px(22))
        tk.Frame(self.root, bg=BRAND_DARK, height=px(3)).pack(fill='x', side='top')

        self.status_bar = tk.Frame(self.root, bg='#e2e9f5', height=px(28))
        self.status_bar.pack(fill='x', side='bottom')
        self.status_bar.pack_propagate(False)
        self.status_label = tk.Label(self.status_bar, text='就绪：粘贴文本或选择文件，然后点「执行转译」。',
                                     bg='#e2e9f5', fg=INK2, font=FONT_SM, anchor='w')
        self.status_label.pack(side='left', fill='x', expand=True, padx=px(16))
        tk.Label(self.status_bar, text='Ctrl+Enter 执行 · Ctrl+S 保存',
                 bg='#e2e9f5', fg=INK3, font=FONT_SM).pack(side='right', padx=px(16))

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill='both', expand=True, padx=px(16), pady=px(12))
        body.rowconfigure(1, weight=1)
        body.columnconfigure(0, weight=1)

        self._build_toolbar(body)
        self._build_panes(body)
        self._on_op_change()

    def _build_toolbar(self, parent):
        bar = tk.Frame(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        bar.grid(row=0, column=0, sticky='ew', pady=(0, px(10)))
        inner = tk.Frame(bar, bg=CARD)
        inner.pack(fill='x', padx=px(14), pady=px(10))
        inner.columnconfigure(5, weight=1)

        tk.Label(inner, text='转译方式', bg=CARD, fg=INK, font=FONT).grid(
            row=0, column=0, sticky='w', padx=(0, px(10)))
        self.op_cb = ttk.Combobox(inner, values=[x[1] for x in OP_ITEMS],
                                  state='readonly', font=FONT, width=30)
        self.op_cb.current(0)
        self.op_cb.grid(row=0, column=1, sticky='w')
        self.op_cb.bind('<<ComboboxSelected>>', self._on_op_change)

        self.run_btn = ttk.Button(inner, text='执行转译', style='Accent.TButton',
                                  command=self.execute)
        self.run_btn.grid(row=0, column=2, padx=px(10))
        ttk.Button(inner, text='清空输入', command=self.clear_input).grid(
            row=0, column=3, padx=(0, px(6)))

        self.cb_uri = ttk.Checkbutton(inner, text='Base64 带 Data URI 前缀',
                                      variable=self.data_uri_var)
        self.cb_uri.grid(row=0, column=6, padx=(px(10), 0))
        self.cb_form = ttk.Checkbutton(inner, text='URL 表单模式（+ ↔ 空格）',
                                       variable=self.form_url_var)
        self.cb_form.grid(row=0, column=7, padx=(px(8), 0))

        self.hint_label = tk.Label(inner, text='', bg=CARD, fg=INK2, font=FONT_SM,
                                   anchor='w', justify='left', wraplength=px(760))
        self.hint_label.grid(row=1, column=1, columnspan=7, sticky='w',
                             pady=(px(6), 0))

    def _build_panes(self, parent):
        paned = ttk.Panedwindow(parent, orient='horizontal')
        paned.grid(row=1, column=0, sticky='nsew')
        self.paned = paned

        left_wrap = tk.Frame(paned, bg=LINE)
        paned.add(left_wrap, weight=1)
        left = tk.Frame(left_wrap, bg=CARD)
        left.pack(fill='both', expand=True, padx=1, pady=1)
        lp = tk.Frame(left, bg=CARD)
        lp.pack(fill='both', expand=True, padx=px(14), pady=px(12))
        lp.columnconfigure(0, weight=1)
        lp.rowconfigure(1, weight=1)

        head = tk.Frame(lp, bg=CARD)
        head.grid(row=0, column=0, sticky='ew')
        tk.Label(head, text='输入', bg=CARD, fg=INK, font=FONT_BOLD).pack(side='left')
        tk.Label(head, text='文本直接粘贴 · 文件按原始字节读取',
                 bg=CARD, fg=INK3, font=FONT_SM).pack(side='right')

        self.nb = ttk.Notebook(lp)
        self.nb.grid(row=1, column=0, sticky='nsew', pady=(px(8), 0))
        self._build_text_tab()
        self._build_file_tab()

        tk.Label(lp, text='提示：大文件只预览开头，执行转译时会读取完整文件。',
                 bg=CARD, fg=INK3, font=FONT_SM, anchor='w').grid(
            row=2, column=0, sticky='w', pady=(px(6), 0))

        right_wrap = tk.Frame(paned, bg=LINE)
        paned.add(right_wrap, weight=1)
        right = tk.Frame(right_wrap, bg=CARD)
        right.pack(fill='both', expand=True, padx=1, pady=1)
        rp = tk.Frame(right, bg=CARD)
        rp.pack(fill='both', expand=True, padx=px(14), pady=px(12))
        rp.columnconfigure(0, weight=1)
        rp.rowconfigure(2, weight=1)

        rhead = tk.Frame(rp, bg=CARD)
        rhead.grid(row=0, column=0, sticky='ew')
        tk.Label(rhead, text='转译结果', bg=CARD, fg=INK, font=FONT_BOLD).pack(side='left')
        self.meta = tk.Label(rhead, text='等待转译', bg=CARD, fg=INK3, font=FONT_SM)
        self.meta.pack(side='right')

        tk.Frame(rp, bg=LINE, height=1).grid(row=1, column=0, sticky='ew', pady=(px(8), 0))

        self.out = tk.Text(rp, wrap='word', font=MONO, bg='#fbfcff', fg=INK,
                           relief='flat', highlightthickness=1, highlightbackground=LINE,
                           highlightcolor=BRAND, padx=px(10), pady=px(8),
                           state='disabled')
        self.out.grid(row=2, column=0, sticky='nsew', pady=(px(8), 0))
        scroll = ttk.Scrollbar(rp, orient='vertical', command=self.out.yview)
        scroll.grid(row=2, column=1, sticky='ns', pady=(px(8), 0))
        self.out.configure(yscrollcommand=scroll.set)

        btnrow = tk.Frame(rp, bg=CARD)
        btnrow.grid(row=3, column=0, sticky='ew', pady=(px(10), 0))
        self.copy_btn = ttk.Button(btnrow, text='复制结果', state='disabled',
                                   command=self.copy_result)
        self.copy_btn.pack(side='left')
        self.save_btn = ttk.Button(btnrow, text='保存为文件', style='Accent.TButton',
                                   state='disabled', command=self.save_result)
        self.save_btn.pack(side='left', padx=(px(8), 0))
        self.to_input_btn = ttk.Button(btnrow, text='结果 → 输入', state='disabled',
                                       command=self.result_to_input)
        self.to_input_btn.pack(side='left', padx=(px(8), 0))
        self.open_dir_btn = ttk.Button(btnrow, text='打开目录', state='disabled',
                                       command=self.open_saved_dir)
        self.open_dir_btn.pack(side='right')

        tk.Label(rp, text='保存时按文件头自动识别扩展名：PNG / JPG / PDF / ZIP / Office / 音视频等；文本可存为 txt、json、xml、html。',
                 bg=CARD, fg=INK3, font=FONT_SM, anchor='w', justify='left',
                 wraplength=px(480)).grid(row=4, column=0, sticky='ew', pady=(px(8), 0))

        self.root.after(80, self._set_initial_sash)

    def _build_text_tab(self):
        self.text_tab = tk.Frame(self.nb, bg=CARD)
        self.nb.add(self.text_tab, text='粘贴文本')
        self.text_tab.columnconfigure(0, weight=1)
        self.text_tab.rowconfigure(0, weight=1)

        self.input_text = tk.Text(self.text_tab, wrap='word', undo=True, font=MONO,
                                  bg='#fbfcff', fg=INK, insertbackground=BRAND,
                                  relief='flat', highlightthickness=1,
                                  highlightbackground=LINE, highlightcolor=BRAND,
                                  padx=px(10), pady=px(8))
        self.input_text.grid(row=0, column=0, sticky='nsew', pady=(px(8), 0))
        scroll = ttk.Scrollbar(self.text_tab, orient='vertical',
                               command=self.input_text.yview)
        scroll.grid(row=0, column=1, sticky='ns', pady=(px(8), 0))
        self.input_text.configure(yscrollcommand=scroll.set)

    def _build_file_tab(self):
        self.file_tab = tk.Frame(self.nb, bg=CARD)
        self.nb.add(self.file_tab, text='选择文件')
        self.file_tab.columnconfigure(0, weight=1)
        self.file_tab.rowconfigure(2, weight=1)

        row = tk.Frame(self.file_tab, bg=CARD)
        row.grid(row=0, column=0, sticky='ew', pady=(px(8), 0))
        ttk.Button(row, text='选择文件…', style='Soft.TButton',
                   command=self.choose_file).pack(side='left')
        ttk.Button(row, text='重新载入', command=self.reload_file).pack(
            side='left', padx=(px(8), 0))

        self.file_info = tk.Label(self.file_tab, text='尚未选择文件',
                                  bg=CARD, fg=INK2, font=FONT_SM, anchor='w',
                                  justify='left', wraplength=px(460))
        self.file_info.grid(row=1, column=0, sticky='ew', pady=(px(8), px(6)))

        self.preview = tk.Text(self.file_tab, wrap='char', font=MONO_SM,
                               bg='#fbfcff', fg=INK2, relief='flat',
                               highlightthickness=1, highlightbackground=LINE,
                               padx=px(9), pady=px(7), state='disabled')
        self.preview.grid(row=2, column=0, sticky='nsew')
        scroll = ttk.Scrollbar(self.file_tab, orient='vertical',
                               command=self.preview.yview)
        scroll.grid(row=2, column=1, sticky='ns')
        self.preview.configure(yscrollcommand=scroll.set)

        tk.Label(self.file_tab, text='二进制文件同样可以：Base64 / Hex 编码、哈希、Base64 / Hex 解码。',
                 bg=CARD, fg=INK3, font=FONT_SM, anchor='w').grid(
            row=3, column=0, sticky='w', pady=(px(6), 0))

        self.file_tab.bind('<Configure>', self._on_file_tab_resize)

    def _set_initial_sash(self):
        try:
            width = self.paned.winfo_width()
            if width > px(700):
                self.paned.sashpos(0, width // 2)
        except Exception:
            pass

    def _on_file_tab_resize(self, event):
        try:
            self.file_info.configure(wraplength=max(px(260), event.width - px(40)))
        except Exception:
            pass

    def _bind(self):
        self.root.bind('<Control-Return>', self._key_run)
        self.input_text.bind('<Control-Return>', self._key_run)
        self.root.bind('<Control-s>', self._key_save)
        self.root.bind('<Control-S>', self._key_save)

    def _key_run(self, event=None):
        self.execute()
        return 'break'

    def _key_save(self, event=None):
        self.save_result()
        return 'break'

    # --------------------------------------------------------------- 状态
    def set_status(self, text, kind='info'):
        colors = {'info': INK2, 'ok': GREEN, 'err': RED, 'warn': AMBER}
        if len(text) > 190:
            text = text[:187] + '...'
        self.status_label.configure(text=text, fg=colors.get(kind, INK2))

    def _report_callback_exception(self, exc, val, tb):
        text = ''.join(traceback.format_exception(exc, val, tb))
        traceback.print_exc()
        try:
            messagebox.showerror('程序错误', text[-2500:], parent=self.root)
        except Exception:
            pass

    def current_op(self):
        idx = self.op_cb.current()
        if idx < 0:
            return OP_ITEMS[0][0]
        return OP_ITEMS[idx][0]

    def _on_op_change(self, event=None):
        op = self.current_op()
        self.cb_uri.configure(state='normal' if op == 'b64_enc' else 'disabled')
        self.cb_form.configure(state='normal' if op in ('url_enc', 'url_dec') else 'disabled')
        for key, _label, hint in OP_ITEMS:
            if key == op:
                self.hint_label.configure(text=hint)
                break

    # --------------------------------------------------------------- 输入
    def choose_file(self):
        path = filedialog.askopenfilename(title='选择要转译的文件',
                                          filetypes=[('所有文件', '*.*')])
        if path:
            self.load_file(path)

    def reload_file(self):
        if self.file_path:
            self.load_file(self.file_path)
        else:
            self.set_status('还没有选择文件', 'warn')

    def load_file(self, path):
        try:
            size = os.path.getsize(path)
            self.file_path = path
            self.file_size = size
            with open(path, 'rb') as f:
                head = f.read(PREVIEW_LIMIT)

            ext, label = sniff_bytes(head)
            text_info = ''
            self.preview.configure(state='normal')
            self.preview.delete('1.0', 'end')
            try:
                preview_text, enc = decode_head(head)
                text_info = '  ·  文本编码 %s' % enc
                self.preview.insert('1.0', preview_text)
                if size > len(head):
                    self.preview.insert('end', '\n\n… 预览仅显示前 %s，执行时读取完整文件。'
                                        % human_size(len(head)))
            except ToolError:
                self.preview.insert('1.0', '%s\n\n%s' % (label, hex_preview(head, 1024)))
                if size > len(head):
                    self.preview.insert('end', '\n\n… 预览仅显示前 %s。' % human_size(len(head)))
            self.preview.configure(state='disabled')

            shown = path if len(path) <= 110 else path[:48] + '…' + path[-58:]
            self.file_info.configure(
                text='%s\n大小：%s  ·  类型：%s%s' % (shown, human_size(size), label, text_info))
            if self.nb.index(self.nb.select()) != 1:
                self.nb.select(1)
            self.set_status('已载入 %s（%s）' % (os.path.basename(path), human_size(size)), 'ok')
        except Exception as e:
            self.set_status('读取文件失败：%s' % e, 'err')
            messagebox.showerror('读取文件失败', '%s\n\n%s' % (path, e), parent=self.root)

    def build_source(self):
        if self.nb.index(self.nb.select()) == 0:
            text = self.input_text.get('1.0', 'end-1c')
            if not text.strip():
                raise ToolError('请先在「粘贴文本」里输入要转译的内容')
            return Source(kind='text', text=text, raw=text.encode('utf-8'),
                          filename='', path='', encoding='UTF-8', is_binary=False)

        if not self.file_path:
            raise ToolError('请先在「选择文件」页选择一个文件')
        try:
            size = os.path.getsize(self.file_path)
        except OSError as e:
            raise ToolError('无法读取文件：%s' % e)
        if size == 0:
            raise ToolError('文件是空的')
        try:
            with open(self.file_path, 'rb') as f:
                raw = f.read()
        except OSError as e:
            raise ToolError('无法读取文件：%s' % e)

        binary = looks_binary(raw)
        if binary:
            text, enc = raw.decode('latin-1'), '二进制'
        else:
            try:
                text, enc = detect_encoding(raw)
            except ToolError:
                text, enc, binary = raw.decode('latin-1'), 'Latin-1', True

        return Source(kind='file', text=text, raw=raw,
                      filename=os.path.basename(self.file_path),
                      path=self.file_path, encoding=enc, is_binary=binary)

    def clear_input(self):
        if self.nb.index(self.nb.select()) == 0:
            self.input_text.delete('1.0', 'end')
            self.set_status('已清空文本框', 'info')
        else:
            self.file_path = ''
            self.file_size = 0
            self.file_info.configure(text='尚未选择文件')
            self.preview.configure(state='normal')
            self.preview.delete('1.0', 'end')
            self.preview.configure(state='disabled')
            self.set_status('已清除文件选择', 'info')

    # --------------------------------------------------------------- 执行
    def execute(self):
        op = self.current_op()
        opts = {
            'data_uri': self.data_uri_var.get(),
            'form_url': self.form_url_var.get(),
        }
        self.run_btn.configure(state='disabled')
        self.root.configure(cursor='watch')
        self.set_status('正在转译…', 'info')
        self.root.update_idletasks()
        t0 = time.perf_counter()
        try:
            src = self.build_source()
            res = run_op(op, src, opts)
            self.last_source = src
            self.last_result = res
            self.last_saved = ''
            self.open_dir_btn.configure(state='disabled')
            self.show_result(res)
            elapsed = time.perf_counter() - t0
            if res.binary:
                tail = '%s · %s' % (res.kind, human_size(len(res.data)))
            else:
                tail = '%s · %s 字符' % (res.kind, format(len(res.text), ','))
            self.set_status('完成（%.2f 秒）：%s' % (elapsed, tail), 'ok')
        except ToolError as e:
            self.set_status(str(e), 'err')
        except Exception as e:
            traceback.print_exc()
            self.set_status('发生错误：%s' % e, 'err')
            messagebox.showerror('转译失败', '%s\n\n%s' % (e, traceback.format_exc(limit=4)),
                                 parent=self.root)
        finally:
            self.run_btn.configure(state='normal')
            self.root.configure(cursor='')

    def show_result(self, res):
        self.out.configure(state='normal')
        self.out.delete('1.0', 'end')

        if res.binary:
            header = '二进制输出 · %s · %s\n建议保存为 .%s\n\n' % (
                res.kind, human_size(len(res.data)), res.ext)
            body = res.note or hex_preview(res.data, 64)
            self.out.insert('1.0', header + body)
            self.out.insert('end', '\n\n二进制内容不在文本区展示，请点「保存为文件」。')
            self.copy_btn.configure(state='disabled')
            self.to_input_btn.configure(state='disabled')
            self.meta.configure(text='%s · %s · .%s' % (
                res.kind, human_size(len(res.data)), res.ext), fg=INK2)
        else:
            text = res.text
            if len(text) > DISPLAY_LIMIT:
                self.out.insert('1.0', text[:DISPLAY_LIMIT])
                self.out.insert('end', '\n\n… 仅显示前 %d 字符，保存文件包含完整内容。'
                                % DISPLAY_LIMIT)
            else:
                self.out.insert('1.0', text)
            self.copy_btn.configure(state='normal')
            self.to_input_btn.configure(state='normal')
            self.meta.configure(text='%s · %s 字符 · .%s' % (
                res.kind, format(len(text), ','), res.ext), fg=INK2)

        self.out.configure(state='disabled')
        self.out.see('1.0')
        self.save_btn.configure(state='normal')

    # --------------------------------------------------------------- 输出
    def copy_result(self):
        res = self.last_result
        if not res or res.binary:
            self.set_status('当前结果不是文本，无法复制', 'warn')
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(res.text)
        self.root.update_idletasks()
        self.set_status('已复制 %s 字符到剪贴板' % format(len(res.text), ','), 'ok')

    def result_to_input(self):
        res = self.last_result
        if not res or res.binary:
            self.set_status('当前结果不是文本，不能放回输入区', 'warn')
            return
        self.input_text.delete('1.0', 'end')
        self.input_text.insert('1.0', res.text)
        self.nb.select(0)
        self.input_text.focus_set()
        self.set_status('已把结果放回输入区，可继续二次转译', 'info')

    def save_result(self):
        res = self.last_result
        if not res:
            self.set_status('还没有可保存的结果，请先执行转译', 'warn')
            return

        name = self.default_filename()
        initdir = default_output_dir()
        if self.last_source and self.last_source.path:
            d = os.path.dirname(self.last_source.path)
            if d and os.path.isdir(d):
                initdir = d

        ext = (res.ext or 'txt').lstrip('.')
        types = [('%s 文件' % ext.upper(), '*.' + ext)]
        if ext != 'txt':
            types.append(('文本文件 (*.txt)', '*.txt'))
        types.append(('所有文件', '*.*'))

        path = filedialog.asksaveasfilename(
            title='保存转译结果', initialdir=initdir, initialfile=name,
            defaultextension='.' + ext, filetypes=types, parent=self.root)
        if not path:
            return

        try:
            if res.binary:
                with open(path, 'wb') as f:
                    f.write(res.data)
                detail = human_size(len(res.data))
            else:
                with open(path, 'w', encoding='utf-8', newline='') as f:
                    f.write(res.text)
                detail = '%s 字符' % format(len(res.text), ',')
        except Exception as e:
            messagebox.showerror('保存失败', '%s\n\n%s' % (path, e), parent=self.root)
            self.set_status('保存失败：%s' % e, 'err')
            return

        self.last_saved = path
        self.open_dir_btn.configure(state='normal')
        self.set_status('已保存：%s（%s）' % (path, detail), 'ok')

    def default_filename(self):
        res = self.last_result
        src = self.last_source
        if res is None:
            return '转译结果.txt'

        stem = '转译结果'
        if src and src.filename:
            stem = os.path.splitext(src.filename)[0] or src.filename
            low = stem.lower()
            for suf in ('.base64', '.b64', '.hex', '.url', '.unicode', '.json'):
                if low.endswith(suf):
                    stem = stem[:-len(suf)]
                    break

        def with_ext(base, ext):
            if base.lower().endswith('.' + ext.lower()):
                return base
            return base + '.' + ext

        op = self.current_op()

        if res.binary:
            if op == 'gbk_enc':
                return 'GBK编码结果.txt'
            if src and src.kind == 'file' and res.ext != 'bin':
                return with_ext(stem, res.ext)
            return '解码结果.' + res.ext

        if src and src.kind == 'file':
            if res.suffix:
                return with_ext(stem, res.suffix.lstrip('.') + '.txt')
            if op.endswith('_dec') or op in ('smart', 'gbk_dec'):
                if res.ext in ('json', 'xml', 'html'):
                    return with_ext(stem, res.ext)
                return stem + '.解码.txt'
            return stem + '.txt'

        if op in ('md5', 'sha1', 'sha256', 'sha512'):
            return op.upper() + '_结果.txt'

        names = {
            'b64_enc': 'Base64编码结果',
            'b64_dec': 'Base64解码结果',
            'url_enc': 'URL编码结果',
            'url_dec': 'URL解码结果',
            'hex_enc': 'Hex编码结果',
            'hex_dec': 'Hex解码结果',
            'uni_enc': 'Unicode转义结果',
            'uni_dec': 'Unicode还原结果',
            'html_enc': 'HTML实体编码结果',
            'html_dec': 'HTML实体还原结果',
            'json_enc': 'JSON转义结果',
            'json_dec': 'JSON反转义结果',
            'smart': '智能解码结果',
            'gbk_dec': '文本编码转换结果',
            'gbk_enc': 'GBK编码结果',
        }
        out_ext = res.ext if res.ext in ('json', 'xml', 'html') else 'txt'
        return names.get(op, '转译结果') + '.' + out_ext

    def open_saved_dir(self):
        if not self.last_saved:
            return
        folder = os.path.dirname(self.last_saved)
        try:
            if sys.platform.startswith('win'):
                os.startfile(folder)
            else:
                self.set_status('当前系统不支持自动打开目录：%s' % folder, 'warn')
        except Exception as e:
            self.set_status('无法打开目录：%s' % e, 'err')


def default_output_dir():
    candidates = [
        os.path.join(os.path.expanduser('~'), 'Desktop'),
        'D:\\桌面',
    ]
    for d in candidates:
        if os.path.isdir(d):
            return d
    return os.path.expanduser('~')


def main():
    global UI_SCALE
    dpi = enable_dpi_awareness()
    UI_SCALE = max(1.0, dpi / 96.0)

    root = tk.Tk()
    try:
        root.tk.call('tk', 'scaling', dpi / 72.0)
    except tk.TclError:
        pass

    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    w = min(px(1160), sw - px(40))
    h = min(px(720), sh - px(90))
    x = max(0, (sw - w) // 2)
    y = max(0, (sh - h) // 2 - px(10))
    root.geometry('%dx%d+%d+%d' % (w, h, x, y))
    root.minsize(min(px(940), sw - px(40)), min(px(600), sh - px(120)))

    App(root)
    root.mainloop()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        try:
            here = os.path.dirname(os.path.abspath(__file__))
            with open(os.path.join(here, '启动错误.log'), 'w', encoding='utf-8') as f:
                f.write(traceback.format_exc())
        except Exception:
            pass
        try:
            messagebox.showerror('启动失败', traceback.format_exc())
        except Exception:
            pass
