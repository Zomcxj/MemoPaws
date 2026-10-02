# 贡献指南

感谢你参与 MemoPaws 的开发！本文档说明本地开发流程、测试方式与提交规范。

## 环境准备

### 必需工具

- **Rust**（stable 通道，2021 edition）
- **Node.js**（18 或更高版本）与 npm
- **Git**
- **Windows 10/11**（当前唯一支持平台）

### 克隆与安装

```bash
git clone https://github.com/Zomcxj/MemoPaws.git
cd MemoPaws
npm --prefix frontend install
```

## 本地开发

### 启动开发服务器

```bash
npm --prefix frontend exec -- tauri dev
```

此命令会自动执行 `npm --prefix frontend run dev`（端口 1420），并打开 Tauri 窗口。前端修改即时热重载，Rust 修改触发重新编译。

### 前端单独开发

```bash
npm --prefix frontend run dev
```

然后通过 `http://localhost:1420` 访问（需要单独启动 Tauri 后端或使用 E2E 测试的 mock 模式）。

### 前端单独构建

```bash
npm --prefix frontend run build
```

### 构建安装包（Windows）

```powershell
$env:RUST_MIN_STACK='67108864'
$env:CARGO_BUILD_JOBS='2'
npm --prefix frontend exec -- tauri build --bundles nsis
```

产物位于 `target/release/bundle/nsis/`。两个环境变量在 Windows 上必须设置：`RUST_MIN_STACK` 将测试/构建线程的最小栈设为 64MB，`CARGO_BUILD_JOBS=2` 限制并行编译任务，避免内存耗尽。

### 发布 Release（Windows）

发布新版本时需要上传两个资产，缺一不可（应用内“下载安装包”和“下载离线包”分别依赖这两个文件名，改名会破坏应用内更新）：

1. **安装包**：构建步骤的产物 `target/release/bundle/nsis/MemoPaws_<版本>_x64-setup.exe`（如 `MemoPaws_0.0.3_x64-setup.exe`）。
2. **离线包（免安装版）**：`cargo build --release`（`tauri build` 过程中也会完成）后在 `target/release/memopaws.exe`。上传前把它复制并重命名为 `MemoPaws_<版本>_x64.exe`（如 `MemoPaws_0.0.3_x64.exe`）。

```powershell
Copy-Item target/release/memopaws.exe MemoPaws_0.0.3_x64.exe
```

资产命名规则与 `crates/tauri/src/commands/update.rs` 的解析逻辑对应：文件名以 `-setup.exe` 结尾的被识别为安装包，以 `_x64.exe` 结尾（且不含 `-setup`）的被识别为离线包。

## 测试

### Rust 测试

```powershell
$env:RUST_MIN_STACK='67108864'
$env:CARGO_BUILD_JOBS='2'
cargo test --workspace
```

该命令运行所有 crate 的单元测试和集成测试，包括：

- `crates/core`（`memopaws-core`）：路径迁移、锚点写入等
- `crates/config`（`memopaws-config`）：配置读写、历史记录
- `crates/keys`（`memopaws-keys`）：密钥库加解密
- `crates/memo`（`memopaws-memo`）：备忘录存储与搜索
- `crates/ocr`（`memopaws-ocr`）：图像工具函数
- `crates/clipboard`（`memopaws-clipboard`）：剪贴板历史与图片存储
- `crates/tauri`（`memopaws-tauri`）：热键映射、关闭行为、IPC 命令
- `crates/canvas`（`memopaws-canvas`）：截图管理

### 前端 E2E 测试

E2E 测试基于 Playwright，测试文件位于 `frontend/e2e/`：

```bash
node frontend/e2e/test-static-contracts.cjs
node frontend/e2e/test-pages.cjs
node frontend/e2e/test-navigation.cjs
node frontend/e2e/test-capture-overlay.cjs
node frontend/e2e/test-interaction-behaviour.cjs
node frontend/e2e/test-update-check.cjs
node frontend/e2e/test-design-tokens.cjs
node frontend/e2e/shot-handles.cjs
npm --prefix frontend run test:tauri
```

> 注意：
>
> - `test-static-contracts.cjs` 只读文件，无需开发服务器，可单独运行。
> - 其余 mock E2E 测试需要前端开发服务器运行在 `http://localhost:1420`。
> - `npm --prefix frontend run test:tauri` 会先构建当前 release binary，再用临时数据目录和 WebView2 profile 启动 MemoPaws，并通过 CDP 把同一套原生测试跑两遍（`--label=app --port=9222` 与 `--label=driver --port=9223`）。
> - 原生 e2e 不得重定向 `USERPROFILE`（WebView2 153 在该条件下不监听 CDP 端口）；测试数据隔离由 `MEMOPAWS_HOME` 与 `WEBVIEW2_USER_DATA_FOLDER` 保证。
> - 原生 e2e 通过 `MEMOPAWS_E2E_HIDDEN=1` 保持窗口隐藏（仅测试脚本设置，正常运行不受影响）。

### 前端构建验证

```bash
npm --prefix frontend run build
```

确保 TypeScript 编译通过且 Vite 打包无错误。

## Cargo.lock

根目录的 `Cargo.lock` 纳入版本控制。修改依赖后，在仓库根目录运行 `cargo check --workspace` 或 `cargo build --workspace`，确认构建成功后检查并提交对应的锁文件变更。

### 完整测试流程

```powershell
$env:RUST_MIN_STACK='67108864'
$env:CARGO_BUILD_JOBS='2'
cargo test --workspace
npm --prefix frontend run build
node frontend/e2e/test-static-contracts.cjs
node frontend/e2e/test-pages.cjs
node frontend/e2e/test-navigation.cjs
node frontend/e2e/test-capture-overlay.cjs
node frontend/e2e/test-interaction-behaviour.cjs
node frontend/e2e/test-update-check.cjs
node frontend/e2e/test-design-tokens.cjs
node frontend/e2e/shot-handles.cjs
npm --prefix frontend run test:tauri
```

运行 mock E2E 前需在另一个终端保持 `npm --prefix frontend run dev`；原生测试会自行构建并启动当前 release binary。

## 代码规范

### Rust

- 遵循 `cargo fmt` 格式化
- 每个 crate 为单一职责
- 使用 `Result<T, Error>` 而非 `panic!`
- 为公共函数编写文档注释
- 新增功能必须附带对应单元测试

### TypeScript / React

- 遵循 ESLint 与 TypeScript 严格模式
- 组件使用函数式写法与 Hooks
- 页面组件放在 `frontend/src/pages/`
- 通用组件放在 `frontend/src/components/`

### Git 提交

提交信息格式：`<type>: <description>`

常用类型：
- `feat`：新功能
- `fix`：修复
- `refactor`：重构
- `docs`：文档
- `test`：测试
- `chore`：工具或配置变更

#### pre-commit 门禁

仓库配置了本地 pre-commit 钩子（`.githooks/pre-commit`），每次 `git commit` 会自动运行：

1. `cargo test --workspace`
2. `node frontend/e2e/test-static-contracts.cjs`

首次克隆后执行一次 `cp .githooks/pre-commit .git/hooks/pre-commit` 启用（本仓库已默认安装）。需要跳过时用 `git commit --no-verify`（仅限赶时间且已手动跑过测试的场景）。

#### 持续集成

推送与 PR 触发 GitHub Actions（`.github/workflows/ci.yml`）：前端构建 → Rust 全量测试 → 静态契约，跑在 Windows runner 上。

## 目录约定

```
crates/<name>/
├── src/lib.rs          # crate 入口
├── Cargo.toml
└── tests/              # 集成测试（可选）

crates/tauri/src/
├── lib.rs              # Tauri 装配（插件、事件、invoke_handler）
├── commands/           # 全部 IPC 命令，按业务域拆分的子模块
│   ├── mod.rs          # 状态类型 + lock_recover! 宏 + pub use 聚合
│   ├── config.rs       # 主题/配置/窗口行为
│   ├── memo.rs         # 备忘录
│   ├── keys.rs         # 密钥库
│   ├── ocr.rs          # AI 识别/翻译/连接测试
│   ├── clipboard.rs    # 剪贴板与全局搜索
│   ├── capture.rs      # 截图与图像处理
│   ├── history.rs      # 历史记录
│   ├── textrep.rs      # 文本替换
│   ├── storage.rs      # 数据目录与迁移
│   └── update.rs       # 应用内更新（轮询、下载、安装/替换）
├── hotkeys.rs          # 全局快捷键
├── tray.rs             # 系统托盘
└── text_replacer*.rs   # 键盘钩子与替换状态机

frontend/src/
├── pages/              # 页面组件
├── components/         # 通用组件
├── styles/             # 全局 CSS
└── i18n/               # 国际化配置
```

## 数据配置

应用配置存储在 `%USERPROFILE%/.memopaws/setting.json`，开发时可直接编辑该文件来测试配置变更。
