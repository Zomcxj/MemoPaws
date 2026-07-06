# MemoPaws

MemoPaws 是一个基于 PySide6 的桌面工具，面向截图文字识别、翻译、画布编辑、剪切板历史、Markdown 备忘录和密钥管理。项目支持本地 RapidOCR 离线识别，也支持通过多模态大模型进行 AI OCR。

## 核心能力

- 截图识别：使用 `Alt+X` 截图并载入画布。
- 本地 OCR：基于 RapidOCR 和 ONNX Runtime，离线可用。
- AI OCR：调用多模态大模型识别复杂图片文字。
- 翻译：支持识别后翻译和大模型翻译路径。
- 画布编辑：支持标注、裁剪、擦除、导出图片和文本。
- 剪切板历史：记录、搜索、锁定和批量删除剪切板内容。
- Markdown 备忘录：支持编辑、预览、标签、导入和导出。
- 密钥管理：管理普通密钥和大模型密钥，支持主密码锁定和测速。
- 设置：支持主题、语言、关闭行为、存储目录和快捷键配置。

## 快速开始

```bash
python -m pip install -r requirements.txt
python main.py
```

## 常用命令

| 命令 | 用途 |
|------|------|
| `python main.py` | 运行应用 |
| `python -m pytest tests/ --tb=short -q` | 运行测试 |
| `bash build.sh` | 构建 onedir 版本到 `dist/MemoPaws/` |
| `bash build.sh fast` | 复用缓存快速构建 onedir 版本 |
| `bash build.sh portable` | 构建 onefile 便携版到 `dist/MemoPaws_Portable.exe` |

Windows 下建议在 Git Bash/MSYS2 中执行构建脚本。脚本会自动包含 `assets/`、`memopaws/resources/` 以及 conda 环境的 OpenSSL DLL，供 HTTPS、API 测速和 AI OCR 使用。

## 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Alt+X` | 截图并加载到画布 |
| `Ctrl+S` | 保存为图片 |
| `Ctrl+C` | 复制识别结果 |
| `Ctrl+Z` | 撤销 |
| `Ctrl+Y` | 重做 |
| `Delete` | 删除选中元素 |
| `Esc` | 取消当前操作 |

## 配置位置

- 锚点文件：用户主目录下的 `.memopaws.json`
- 默认数据目录：用户主目录下的 `.memopaws/`
- 可在设置页修改存储目录，修改后会迁移整个 `.memopaws` 数据目录。

## 项目文档

- [功能说明](docs/features.md)
- [项目文件说明](docs/project-structure.md)
- [开发与构建规范](docs/development.md)

## 技术栈

- Python 3.12
- PySide6
- RapidOCR + ONNX Runtime
- OpenCV + Pillow + NumPy
- httpx
- cryptography
- PyInstaller

## 许可证

MIT License

Copyright (c) 2026 Zomcxj
