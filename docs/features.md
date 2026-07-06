# 功能说明

本文档说明 MemoPaws 当前已实现的主要功能模块。功能入口以应用左侧导航和设置页为主。

## 截图与画布

截图入口由 `memopaws/canvas/capture.py` 和主窗口快捷键触发，默认快捷键为 `Alt+X`。截图后图片会载入识别页画布。

画布能力位于 `memopaws/canvas/canvas.py`，负责图片展示、缩放、标注、裁剪、擦除、撤销、重做和导出。边框动效位于 `memopaws/canvas/border_glow_widget.py`。

## OCR 识别

OCR 入口位于 `memopaws/ocr/ocr.py`，通过 `OCRManager` 统一管理本地识别和 AI 识别。

本地 OCR 使用 RapidOCR 和 ONNX Runtime，适合离线和低延迟场景。AI OCR 通过配置的大模型 API 识别图片文字，适合复杂排版、截图质量较差或需要更强语义理解的场景。

识别页异步流程位于 `memopaws/ocr/ocr_translate.py`，避免 OCR 运行时阻塞主界面。

## 翻译

翻译逻辑位于 `memopaws/ocr/translator.py`。项目包含在线翻译和大模型翻译路径，网络请求统一使用 `httpx`。

打包后的 HTTPS 能力依赖 OpenSSL DLL。Windows 便携版由 `build.sh portable` 自动包含 conda 环境中的 `libssl-3-x64.dll` 和 `libcrypto-3-x64.dll`。

## 剪切板历史

剪切板功能位于 `memopaws/clipboard/`。

- `clipboard_page.py`：剪切板历史页，负责列表展示、搜索、锁定和删除。
- `clipboard_dialog.py`：剪切板相关弹窗。

剪切板最大记录数可在设置页配置。

## Markdown 备忘录

备忘录功能位于 `memopaws/memo/`。

- `memo_page.py`：备忘录页面主逻辑。
- `memo_ui.py`：页面构建和控件组织。
- `memo_storage.py`：备忘录文件读写、导入导出和标签数据。
- `markdown_converter.py`：Markdown 转 HTML 渲染。
- `memo_widgets.py`：备忘录页面自定义控件。

备忘录数据存放在当前 `.memopaws` 数据目录中。

## 密钥管理

密钥功能位于 `memopaws/keys/`。

- `key_page.py`：密钥管理页面和测速逻辑。
- `key_manager.py`：密钥存储、加密和主密码锁定。
- `key_dialogs.py`：密钥相关弹窗和文案。

大模型密钥测速会调用兼容 OpenAI Chat Completions 风格的接口。测速线程无论网络层是否初始化成功，都会通知 UI 收尾，避免按钮和动画卡在测试状态。

## 设置

设置功能位于 `memopaws/config/`。

- `settings_page.py`：设置页主类和配置保存流程。
- `settings_ui.py`：设置页 UI 构建。
- `settings_style.py`：设置页输入框样式。
- `api_config.py`：API 配置加载和连接测试。
- `migration.py`：存储目录迁移和冲突处理。
- `shortcut_manager.py`：全局快捷键配置。
- `text_replacer.py`：文本替换相关能力。
- `history.py`：操作历史配置与管理。
- `config_dialog.py`：配置相关弹窗。

## 主题与语言

主题和颜色 token 位于 `memopaws/core/themes.py`。设置页和主窗口会根据当前主题刷新控件样式。

界面支持中文和英文切换。页面应避免通过重建复杂控件来刷新语言，优先更新现有控件文本，减少闪烁和状态丢失。
