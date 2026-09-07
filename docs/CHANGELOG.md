# Changelog

## 未发布

### 新增

- 操作历史：AI 识别/翻译成功记录，历史面板默认四行、可收起展开，`history_max_items` 配置项
- 密钥页一键导入 opencode 提供商：读取 `~/.config/opencode/opencode.json`，按「提供商/模型」批量生成密钥条目，重名自动跳过
- 剪贴板去重：重复复制的文本/图片刷新时间置顶，不再产生重复记录
- Alt+X 从任意页面直达截图（含托盘隐藏状态）
- 截图结果窗独立直角（∟ 形）拖动手柄

### 改进

- 截图选框 8 个手柄改为圆点；结果窗 10px 圆角
- 截图前等待窗口隐藏动画完成，跨页 Alt+X 等待新页面绘制完成，消除主界面半透明残影
- 截图确认后加纯色过渡遮罩，避免恢复窗口时闪现旧帧
- 侧边栏「贴图识别」改名「图片识别」
- 默认模型切换为 `glm-4v-flash`，旧配置加载时自动迁移
- 保留 One Punch 操作，拆分 OCR 与翻译的处理中状态
- 截图工具按钮改为按界面语言显示完整的中文或英文名称

### 修复

- 设置保存兼容旧配置中的 null 字段（读取时剔除，保存不再失败）
- 剪贴板与配置改为原子写入（临时文件 + fsync + rename），崩溃不再留下损坏的 JSON
- OCR/翻译成功后写历史失败不再把整个操作误报为失败
- 剪贴板时间戳改为毫秒粒度；界面时间渲染兼容旧秒级时间戳与更早的格式化字符串

### 改进

- 截图生成消除一次整份 PNG 内存拷贝

### 移除

- 区域马赛克功能（按钮、拖选逻辑与样式）；整图马赛克预处理保留
- 区域马赛克的后端命令与图像实现（前端已无调用方）

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
- 系统托盘集成（`tray.rs`）
- 核心工具库（`memopaws-core`）：数据目录管理、锚点文件、目录迁移（Merge/Replace）
- 应用配置（`memopaws-config`）：主题、语言、关闭行为、API 参数、历史记录上限
- 5 个前端页面：识别页、备忘录页、密钥页、剪切板页、设置页
- Playwright E2E 测试套件（8 个测试文件，覆盖页面截图与交互）
- 全局搜索（`Ctrl+Shift+F`）

### 技术栈

- Tauri v2（Rust 后端 + Web 前端）
- React 18 + TypeScript
- Zustand 5
- Vite 5
- Playwright
