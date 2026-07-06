# MemoPaws

轻量级桌面 OCR、翻译、剪切板、备忘录与密钥管理工具，支持本地 RapidOCR 和多模态大模型识别。

## 功能

- 📷 **截图识别**：按下 `Alt+X` 截图，自动加载到画布
- 🔍 **本地 OCR**：基于 RapidOCR，离线可用，快速识别
- 🤖 **AI 识别**：接入多模态大模型（如 glm-4v-flash），识别复杂文字
- 🌐 **AI 翻译**：识别后一键翻译
- 🎨 **画布编辑**：支持标注、裁剪、擦除
- 🖼️ **导出**：支持 PNG/JPG/文本导出
- 📋 **剪切板历史**：记录、搜索、锁定和批量删除剪切板内容
- 📝 **Markdown 备忘录**：支持编辑、同步预览、纯预览、标签与导入导出
- 🔑 **密钥管理**：管理大模型密钥和普通密钥，支持主密码锁定和测速
- 🌗 **主题与语言**：支持亮/暗主题与中英文界面切换

## 快速开始

```bash
D:/software/miniforge3/envs/llm/python.exe -m pip install -r requirements.txt
D:/software/miniforge3/envs/llm/python.exe main.py
```

## 构建与打包

使用统一脚本打包：

```bash
bash build.sh portable
```

| 命令 | 模式 | 输出 |
|------|------|------|
| `bash build.sh` | onedir | `dist/MemoPaws/` |
| `bash build.sh fast` | onedir（复用缓存） | `dist/MemoPaws/` |
| `bash build.sh portable` | onefile 单文件 | `dist/MemoPaws_Portable.exe` |

Windows 下建议在 Git Bash/MSYS2 中执行，脚本会自动包含 `assets/`、`memopaws/resources/` 以及 conda 环境的 OpenSSL DLL（供 HTTPS/API/OCR 使用）。

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
- **模型名**：如 `glm-4v-flash`
- **关闭行为**：直接退出 / 最小化到托盘
- **存储目录**：通过 `C:\Users\<用户>\.memopaws.json` 锚点定位实际 `.memopaws` 数据目录
- **快捷键**：可在设置页修改截图、画布自适应、新建备忘录等快捷键

## 项目结构

```text
memopaws/
├── canvas/      # 画布、截图覆盖层、边框动效
├── clipboard/   # 剪切板历史
├── config/      # 设置页、快捷键、配置迁移
├── core/        # 路径、主题、通用工具
├── keys/        # 密钥管理
├── memo/        # Markdown 备忘录、渲染、存储、UI
├── ocr/         # OCR 与翻译
└── ui/          # 主窗口、导航、托盘、识别页
```

## 技术栈

- **UI**: PySide6
- **OCR**: RapidOCR (ONNX Runtime)
- **AI**: 多模态大模型 API
- **打包**: PyInstaller
