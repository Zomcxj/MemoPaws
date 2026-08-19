# MemoPaws

跨平台桌面笔记与密钥管理工具，基于 Rust + Tauri + React 构建。

## 功能

- **备忘录**：Markdown 格式笔记，支持搜索、渲染与本地持久化
- **密钥管理**：加密密钥库，支持主密码锁定/解锁、增删改查与排序
- **剪切板历史**：文本与图片剪切板记录，支持搜索、锁定、批量删除
- **AI 识别与翻译**：截图 OCR、图片预处理、马赛克与裁剪，AI 文本翻译
- **文字替换**：全局键盘钩子驱动的缩写替换（Windows）
- **浮动小部件**：常驻窗口的浮动工具面板
- **全局快捷键**：可配置的快捷键映射
- **系统托盘**：最小化到托盘，支持退出/隐藏行为配置

## 技术栈

| 层 | 技术 |
|---|---|
| 桌面框架 | Tauri v2 (Rust) |
| 前端 | React 18 + TypeScript + Vite 5 |
| 状态管理 | Zustand 5 |
| 构建 | Cargo workspace + npm |
| 测试 | Rust unit tests + Playwright E2E |

## 快速开始

### 环境要求

- Rust 2021 edition（建议最新版 stable）
- Node.js 18+ 与 npm
- Windows 10/11（当前目标平台）

### 安装依赖

```bash
cargo build --workspace
npm --prefix frontend install
```

### 开发模式

```bash
cargo tauri dev
```

该命令会自动启动前端开发服务器（`npm run dev` on port 1420）并打开 Tauri 窗口。

### 生产构建

```bash
cargo tauri build --bundles nsis
```

生成 Windows NSIS 安装包（位于 `crates/memopaws-tauri/target/release/bundle/nsis/`）。

## 目录结构

```
MemoPaws-Rust/
├── Cargo.toml                         # Workspace 根配置
├── README.md                          # 本文件
├── AGENTS.md                          # 开发约定
├── docs/
│   ├── CONTRIBUTING.md                # 贡献指南
│   └── CHANGELOG.md                   # 版本日志
├── crates/
│   ├── memopaws-core/                 # 核心工具：路径管理、错误类型、主题
│   ├── memopaws-config/               # 应用配置、历史记录管理
│   ├── memopaws-ocr/                  # OCR 客户端、图像工具
│   ├── memopaws-clipboard/            # 剪切板管理器
│   ├── memopaws-memo/                 # 备忘录存储、搜索、渲染、迁移
│   ├── memopaws-keys/                 # 密钥库加密存储
│   ├── memopaws-canvas/               # 截图画布、CaptureManager
│   └── memopaws-tauri/                # Tauri 应用入口
│       ├── src/
│       │   ├── main.rs                # 应用入口
│       │   ├── lib.rs                 # Tauri builder、命令注册
│       │   ├── commands.rs            # 全部 IPC 命令
│       │   ├── hotkeys.rs             # 全局快捷键管理
│       │   ├── tray.rs                # 系统托盘
│       │   ├── clipboard_hook.rs      # 剪切板监听
│       │   ├── text_replacer.rs       # 文字替换引擎
│       │   └── text_replacer_hook.rs  # 键盘钩子监听
│       ├── capabilities/
│       │   └── default.json           # Tauri ACL 能力配置
│       ├── tauri.conf.json            # Tauri 应用配置
│       └── Cargo.toml
└── frontend/                          # 前端源码
    ├── package.json
    ├── index.html
    ├── vite.config.ts
    ├── src/
    │   ├── main.tsx                   # 入口
    │   ├── App.tsx                    # 应用根组件
    │   ├── pages/                     # 页面组件
    │   ├── components/                # 通用组件
    │   ├── styles/                    # 全局样式
    │   └── i18n/                      # 国际化
    └── e2e/                           # Playwright E2E 测试
```

## 全局快捷键

| 动作 | 默认快捷键 | 说明 |
|---|---|---|
| `capture` | `Alt+X` | 触发屏幕截图 |
| `canvas_fit` | `Ctrl+F` | 画布自适应缩放 |
| `new_memo` | `Ctrl+N` | 新建备忘录 |
| `global_search` | `Ctrl+Shift+F` | 全局搜索面板 |
| `toggle_clipboard` | `Ctrl+Shift+V` | 切换剪切板历史面板 |

> 所有快捷键均可在「设置」页面中自定义修改。

## 数据存储

应用数据默认存储在 `%USERPROFILE%/.memopaws-rust/` 目录下，包含：

| 路径 | 内容 |
|---|---|
| `memo/` | 备忘录文件 |
| `keys.json` | 加密密钥库 |
| `clipboard.json` | 剪切板历史记录 |
| `history.json` | 操作历史 |
| `setting.json` | 应用配置 |
| `clipboard_images/` | 剪切板图片 |
| `captures/` | 截图文件 |

支持在设置中迁移数据目录（Merge / Replace）。

## 配置

配置文件位于数据目录下的 `setting.json`，支持以下字段：

- `theme`：主题（dark / light）
- `language`：界面语言
- `close_behavior`：关闭行为（exit / tray）
- `api_key` / `api_url` / `api_model`：AI 服务配置
- `shortcuts`：快捷键覆盖
- `text_replacements`：文字替换规则
- `clipboard_max_items` / `history_max_items`：历史记录上限

## 许可

本项目的具体许可信息请查看仓库根目录下的 LICENSE 文件。
