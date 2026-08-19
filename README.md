# MemoPaws

基于 Rust、Tauri 和 React 的 Windows 桌面笔记与密钥管理工具。

## 核心能力

- Markdown 备忘录、搜索、渲染与本地持久化
- 加密密钥库，支持主密码锁定、解锁和排序
- 文本与图片剪贴板历史
- 截图 OCR、翻译、裁剪和图像标注
- Windows 全局快捷键与文字替换
- 系统托盘和可配置的关闭行为

## 环境要求

- Windows 10/11
- Rust stable（2021 edition）
- Node.js 18+ 与 npm

## 快速开始

```bash
cargo build --workspace
npm --prefix frontend install
cargo tauri dev
```

开发命令会启动前端开发服务器并打开 Tauri 窗口。生产构建使用：

```bash
cargo tauri build --bundles nsis
```

## 文档

- [用户指南](docs/USER_GUIDE.md)：功能、快捷键、数据目录和配置
- [贡献指南](docs/CONTRIBUTING.md)：开发、测试、构建和提交规范
- [更新日志](docs/CHANGELOG.md)

## 许可

具体许可信息请查看仓库根目录的 `LICENSE` 文件。
