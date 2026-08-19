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
git clone https://github.com/MemoPaws/MemoPaws-Rust.git
cd MemoPaws-Rust
cargo build --workspace
npm --prefix frontend install
```

## 本地开发

### 启动开发服务器

```bash
cargo tauri dev
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

## 测试

### Rust 测试

```bash
cargo test --workspace
```

该命令运行所有 crate 的单元测试和集成测试，包括：

- `memopaws-core`：路径迁移、锚点写入等
- `memopaws-config`：配置读写、历史记录
- `memopaws-keys`：密钥库加解密
- `memopaws-memo`：备忘录存储与搜索
- `memopaws-ocr`：图像工具函数
- `memopaws-tauri`：热键映射、关闭行为、IPC 命令
- `memopaws-canvas`：截图管理

### 前端 E2E 测试

E2E 测试基于 Playwright，测试文件位于 `frontend/e2e/`：

```bash
node frontend/e2e/test-pages.cjs
node frontend/e2e/test-navigation.cjs
node frontend/e2e/test-tauri-app.cjs
node frontend/e2e/test-tauri-driver.cjs
node frontend/e2e/test-capture-overlay.cjs
node frontend/e2e/test-clipboard-layout.cjs
node frontend/e2e/test-key-interaction-refinement.cjs
node frontend/e2e/test-final-review-fixes.cjs
```

> 注意：E2E 测试需要前端开发服务器运行在 `http://localhost:1420`。可使用 mock 模式模拟 Tauri API。

### 前端构建验证

```bash
npm --prefix frontend run build
```

确保 TypeScript 编译通过且 Vite 打包无错误。

## Cargo.lock

根目录的 `Cargo.lock` 纳入版本控制。修改依赖后，在仓库根目录运行 `cargo check --workspace` 或 `cargo build --workspace`，确认构建成功后检查并提交对应的锁文件变更。

### 完整测试流程

```bash
cargo test --workspace
npm --prefix frontend run build
node frontend/e2e/test-pages.cjs
```

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

## 目录约定

```
crates/memopaws-<name>/
├── src/lib.rs          # crate 入口
├── Cargo.toml
└── tests/              # 集成测试（可选）

frontend/src/
├── pages/              # 页面组件
├── components/         # 通用组件
├── styles/             # 全局 CSS
└── i18n/               # 国际化配置
```

## 数据配置

应用配置存储在 `%USERPROFILE%/.memopaws-rust/setting.json`，开发时可直接编辑该文件来测试配置变更。
