# 常用编码转译工具 · Codec Translator

An offline Windows desktop tool for everyday encoding/decoding: Base64, URL, Hex, Unicode, HTML entities, JSON escapes, MD5/SHA hashes with a local weak-password lookup, text encoding detection and file-type-aware saving. Single-file Python + tkinter, standard library only, no network, no telemetry.

一个离线的 Windows 桌面小工具：粘贴文本或选择文件，做常见编码 / 解码，结果可直接回显、复制，或按智能扩展名保存成文件。

- 获取：`git clone https://github.com/Nancy521926/codec-translator.git`，放在任意目录都能跑
- 运行环境：Windows + Python 3（只用 Python 标准库，不需要安装任何第三方包）
- 不联网，不上传任何内容

## 怎么启动

双击 **`start-无弹窗版.pyw`**（无黑框，直接出界面）。

也可以双击 `start.bat`（效果相同，批处理窗口会闪一下）。

如果打不开或想看报错，双击 **`start-debug.bat`**，它会在命令行窗口里运行并保留错误信息。

> `编码转译工具.py` 是主源码；直接双击它会带一个控制台窗口，日常用 `start-无弹窗版.pyw` 或 `start.bat`。

## 输入方式

界面左侧有两个页签：

1. **粘贴文本** —— 直接粘贴，结果在右侧文本区直接回显。
2. **选择文件** —— 选一个任意文件，显示大小、类型、文本编码和预览；执行时读取完整文件。二进制文件也能做 Base64 / Hex 编码和哈希。

## 支持的转译

| 分组 | 操作 |
|------|------|
| 智能 | 智能识别（自动解码）：自动判断 Data URI / Unicode / URL / HTML / Hex / Base64；认出一整串无分隔的 32/40/64/128 位十六进制、且解出来不像文本或文件头时，判定为 MD5 / SHA-1 / SHA-256 / SHA-512 摘要，直接说明「不可解码」而不是吐一个 `.bin` |
| Base64 | 编码（可带 Data URI 前缀）、解码（支持 URL-safe、去 PEM 头尾、补全 `=`） |
| URL | 编码、解码（支持 `%XX`、`%uXXXX` 和表单模式 `+` ↔ 空格） |
| Hex | 编码、解码（支持空格、换行、逗号、`0x`、`\x`） |
| Unicode | 转义为 `\uXXXX`（emoji 自动用代理对）、还原 `\uXXXX` / `\UXXXXXXXX` / `\xXX` |
| HTML | 实体编码、实体解码（含 `&#...;` 数字实体） |
| JSON | 字符串转义、反转义（自动去掉首尾引号） |
| 哈希 | MD5、SHA-1、SHA-256、SHA-512（文本按 UTF-8，文件按原始字节）；**哈希反查**：粘一串摘要，用本地字典还原常见弱口令原文 |
| 文本编码 | 识别文件是 UTF-8 / UTF-16 / GBK / GB18030 / Big5；也可把粘贴文本转成 GBK 字节保存 |

## 结果与保存

- **文本结果**：直接显示在右侧，可「复制结果」「保存为文件」「结果 → 输入」继续二次转译。
- **二进制结果**：文本区显示格式说明和十六进制预览，点「保存为文件」写出原始字节。
- **哈希摘要**：整串十六进制如果长度正好是 16 / 20 / 32 / 64 字节、又没有空格或 `0x` 前缀、解出来也不像文本或已知文件头，会判定成摘要并提示算法名。真要那几字节原始数据，手动选「Hex 解码」。
- **哈希反查**：判定成摘要后自动跑本地字典，命中就直接告诉你原文（例如 `E10ADC…883E` → `123456`）。字典 = 约 190 个常见弱口令 × 12 种数字/符号后缀 × 大小写变体，再加 6 位以内的纯数字（含前导零），全程离线，最慢一枪约 0.8 秒。查不到不代表没原文，只说明不在这个范围里。
- **智能扩展名**：保存时按文件头识别真实类型，自动给出建议文件名和扩展名：
  - 图片：png / jpg / gif / webp / bmp / ico / tif / heic / avif
  - 文档：pdf / docx / xlsx / pptx / doc
  - 压缩包：zip / rar / 7z / gz / bz2 / xz
  - 程序与数据：exe / elf / apk / jar / class / wasm / sqlite / der
  - 音视频：mp3 / flac / ogg / wav / mp4 / mov / m4a / mkv
  - 文本：txt / json / xml / html
- 例如：把 `photo.png` 做 Base64 编码，建议保存为 `photo.base64.txt`；把以 `.base64` 结尾的文件解码，识别出 PNG 就建议 `photo.png`。
- 保存对话框里可以改文件名、换目录、改扩展名。

## 快捷键

- `Ctrl + Enter`：执行转译
- `Ctrl + S`：保存结果

## 文件结构

```
codec-translator\
  编码转译工具.py    主程序（单文件，全部逻辑都在里面）
  start-无弹窗版.pyw 无黑框启动器（双击这个）
  start.bat          备用启动（pyw，批处理会闪一下）
  start-debug.bat    排错启动（保留控制台和报错）
  LICENSE            MIT
  .gitignore         忽略缓存和日志
  .gitattributes     固定 .bat 为 CRLF、.py/.pyw 为 LF
  README.md          本说明
```

源码就是 `编码转译工具.py`；`start-无弹窗版.pyw` 只是无黑框启动器。

## 常见问题

**双击 bat 没反应 / 提示找不到 Python**
安装 Python 3（安装时勾选 “Add Python to PATH”），确认命令行里能运行 `py -3 --version`。

**界面模糊或太大**
程序会按系统 DPI 自动缩放；如仍不合适，可在 Windows「显示设置 → 缩放」里调整。

**保存时扩展名不对**
二进制结果以文件头识别为准；极少数自定义格式会显示为 `.bin`，保存时手动改扩展名即可。

**大文件**
文本区最多预览 128 KB、显示结果最多 20 万字符；执行和保存都使用完整内容，不受预览限制。哈希和 Base64 对几十 MB 的文件也能正常工作，只是需要稍等。
