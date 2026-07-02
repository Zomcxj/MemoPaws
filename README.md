# MemoPaws

轻量级截图 OCR + AI 翻译工具，支持本地 RapidOCR 和多模态大模型识别。

## 功能

- 📷 **截图识别**：按下 `Alt+X` 截图，自动加载到画布
- 🔍 **本地 OCR**：基于 RapidOCR，离线可用，快速识别
- 🤖 **AI 识别**：接入多模态大模型（如 glm-4v-flash），识别复杂文字
- 🌐 **AI 翻译**：识别后一键翻译
- 🎨 **画布编辑**：支持标注、裁剪、擦除
- 🖼️ **导出**：支持 PNG/JPG/文本导出

## 快速开始

```bash
pip install -r requirements.txt
python main.py
```

## 构建与打包

提供两种打包方式：

| 脚本 | 模式 | 输出 |
|------|------|------|
| `build_dev.bat` / `build_dev.sh` | onedir | `dist/dev/MemoPaws` |
| `build_portable.bat` / `build_portable.sh` | onefile | `dist_portable/MemoPaws.exe` |

详见 [README.md](README.md)（构建说明）。

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

## 配置

点击设置按钮可配置：

- **API Key**：多模态大模型 API Key（智谱 AI / OpenAI 等）
- **API URL**：API Base URL
- **模型名**：如 `glm-4v-flash`、`deepseek-vl2`
- **关闭行为**：直接退出 / 最小化到托盘

## 常见问题

### Q: 打包后本地 OCR 报错 "ProtocolResolver.SYSTEM cannot be loaded"

**原因**：`default_models.yaml` 未打包进去。

**解决**：确保构建脚本中包含 `--add-data ...default_models.yaml...` 参数。

### Q: 打包后本地 OCR 报错 "No such file or directory: ...default_models.yaml"

**原因**：RapidOCR 初始化时查找 `default_models.yaml`，但打包后路径不对。

**解决**：已在构建脚本和 spec 文件中正确配置该文件的打包路径。

### Q: 如何替换 OCR 模型？

替换 `rapidocr/models/` 目录下的模型文件即可（开发版在 `_internal/rapidocr/models/`，便携版需重新打包）。

## 技术栈

- **UI**: PySide6
- **OCR**: RapidOCR (ONNX Runtime)
- **AI**: 多模态大模型 API
- **打包**: PyInstaller
