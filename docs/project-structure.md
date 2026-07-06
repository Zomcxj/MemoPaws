# 项目文件说明

本文档按目录说明 MemoPaws 的项目文件职责。新增或移动文件时，应同步更新本文档。

## 根目录

| 路径 | 说明 |
|------|------|
| `main.py` | 应用入口，创建 Qt 应用并启动主窗口。 |
| `build.sh` | 统一打包脚本，支持 onedir、快速构建和 onefile 便携版。 |
| `requirements.txt` | 运行依赖列表。测试和打包依赖以注释形式保留。 |
| `README.md` | 项目入口文档，提供简介、常用命令和文档索引。 |
| `AGENTS.md` | 项目协作规范和环境约束。 |
| `.gitignore` | 忽略缓存、构建产物、日志、本地数据目录和 spec 文件。 |

## `assets/`

| 路径 | 说明 |
|------|------|
| `assets/app.png` | 应用图标源图。 |
| `assets/app.ico` | Windows 打包图标。 |
| `assets/icons/` | SVG 图标资源。 |
| `assets/fonts/` | JetBrains Mono 字体文件。 |

## `memopaws/`

应用主包。按功能分为 `canvas`、`clipboard`、`config`、`core`、`keys`、`memo`、`ocr`、`ui` 和 `resources`。

### `memopaws/ui/`

| 文件 | 说明 |
|------|------|
| `main_window.py` | 主窗口，负责页面装配、导航、主题、语言和 OCR 配置传递。 |
| `main_window_ui.py` | 主窗口标题栏、导航栏和页面栈装配辅助函数。 |
| `recognize_page.py` | 识别页 UI，承载画布、OCR、翻译和导出入口。 |
| `frameless_window.py` | 无边框窗口基础能力。 |
| `nav_sidebar.py` | 左侧导航栏。 |
| `segmented_control.py` | 分段按钮控件。 |
| `tray.py` | 系统托盘行为。 |

### `memopaws/canvas/`

| 文件 | 说明 |
|------|------|
| `canvas.py` | 图片画布、标注、裁剪、擦除、缩放、撤销和导出。 |
| `capture.py` | 截图覆盖层和截图流程。 |
| `border_glow_widget.py` | 识别和翻译等操作使用的边框动效。 |

### `memopaws/ocr/`

| 文件 | 说明 |
|------|------|
| `ocr.py` | OCR 管理器、本地 RapidOCR 初始化、AI OCR 请求和 OCR 线程 worker。 |
| `ocr_translate.py` | 识别页 OCR 与翻译异步流程 mixin。 |
| `translator.py` | 在线翻译和大模型翻译实现。 |

### `memopaws/config/`

| 文件 | 说明 |
|------|------|
| `settings_page.py` | 设置页主类，负责配置保存、事件处理和子模块串联。 |
| `settings_ui.py` | 设置页 UI 构建。 |
| `settings_style.py` | 设置页输入框和 SpinBox 样式。 |
| `api_config.py` | API 配置加载和连接测试。 |
| `migration.py` | `.memopaws` 存储目录迁移、合并、覆盖和重启提示。 |
| `shortcut_manager.py` | 快捷键配置、注册和保存。 |
| `text_replacer.py` | 文本替换器能力。 |
| `history.py` | 操作历史配置和记录管理。 |
| `config_dialog.py` | 配置相关弹窗。 |

### `memopaws/keys/`

| 文件 | 说明 |
|------|------|
| `key_page.py` | 密钥管理页面、拖拽排序、测速和 UI 状态更新。 |
| `key_manager.py` | 密钥数据读写、加密、解密和主密码锁定。 |
| `key_dialogs.py` | 密钥弹窗和多语言文本。 |

### `memopaws/memo/`

| 文件 | 说明 |
|------|------|
| `memo_page.py` | 备忘录页面主逻辑。 |
| `memo_ui.py` | 备忘录页面 UI 构建。 |
| `memo_storage.py` | 备忘录文件、标签、导入和导出。 |
| `memo_search.py` | 备忘录标题、正文、标签、拼音和模糊搜索匹配。 |
| `markdown_converter.py` | Markdown 到 HTML 的渲染转换。 |
| `memo_widgets.py` | 备忘录自定义控件。 |

### `memopaws/clipboard/`

| 文件 | 说明 |
|------|------|
| `clipboard_page.py` | 剪切板历史页面。 |
| `clipboard_dialog.py` | 剪切板相关弹窗。 |

### `memopaws/core/`

| 文件 | 说明 |
|------|------|
| `utils.py` | 路径、配置目录、API URL、图标加载、通用网络测试等工具函数。 |
| `themes.py` | 暗色和亮色主题 token、按钮样式和通用阴影样式。 |

### `memopaws/resources/`

| 文件 | 说明 |
|------|------|
| `default_models.yaml` | RapidOCR 默认模型配置。 |
| `rapidocr_config.yaml` | RapidOCR 配置。 |
| `onnxruntime_hook.py` | ONNX Runtime 打包辅助 hook。 |

## `tests/`

测试目录覆盖工具函数、主题、Qt 控件、OCR、翻译、设置页、剪切板、备忘录、密钥管理、画布和应用导入。运行命令：

```bash
python -m pytest tests/ --tb=short -q
```

## `docs/`

| 文件 | 说明 |
|------|------|
| `docs/features.md` | 功能模块说明。 |
| `docs/project-structure.md` | 项目目录和文件职责。 |
| `docs/development.md` | 开发、测试、构建和协作规范。 |
