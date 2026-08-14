# Changelog

## [0.1.0] - 2026-08-14

### 新增

- Rust + Tauri v2 完整重写，达成与 Python 原版的功能对齐
- 前端 React 18 + TypeScript + Vite 5 应用，Zustand 5 状态管理
- 备忘录模块（`memopaws-memo`）：Markdown 渲染、全文搜索、本地存储与数据迁移
- 密钥库模块（`memopaws-keys`）：加密存储、主密码锁定/解锁、增删改查与排序
- 剪切板模块（`memopaws-clipboard`）：文本与图片记录、搜索、锁定、批量删除
- 截图模块（`memopaws-canvas`）：屏幕截图、CaptureManager 持久化
- OCR 模块（`memopaws-ocr`）：AI OCR 识别、图像预处理、马赛克区域标注、裁剪
- AI 翻译（`ai_translate` IPC 命令）
- 全局快捷键系统（`hotkeys.rs`）：5 个默认快捷键，支持配置覆盖
- 文字替换引擎（`text_replacer.rs`）+ 键盘钩子监听（Windows）
- 浮动小部件窗口（`floating` window，始终置顶、无边框、透明背景）
- 系统托盘集成（`tray.rs`）
- 核心工具库（`memopaws-core`）：数据目录管理、锚点文件、目录迁移（Merge/Replace）
- 应用配置（`memopaws-config`）：主题、语言、关闭行为、API 参数、历史记录上限
- 5 个前端页面：识别页、备忘录页、密钥页、剪切板页、设置页
- Playwright E2E 测试套件（9 个测试文件，覆盖页面截图与交互）
- 全局搜索（`Ctrl+Shift+F`）

### 技术栈

- Tauri v2（Rust 后端 + Web 前端）
- React 18 + TypeScript
- Zustand 5
- Vite 5
- Playwright
