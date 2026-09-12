# MemoPaws

基于 Rust、Tauri 和 React 的 Windows 桌面笔记与密钥管理工具。

## 核心能力

- Markdown 备忘录、搜索、渲染与本地持久化
- 加密密钥库，支持主密码锁定、解锁、排序和 opencode 配置一键导入
- 文本与图片剪贴板历史（重复自动去重置顶）
- 截图 OCR、翻译、裁剪、图像预处理与操作历史
- Windows 全局快捷键与文字替换
- 系统托盘和可配置的关闭行为

## 环境要求

- Windows 10/11
- Rust stable（2021 edition）
- Node.js 18+ 与 npm

## 快速开始

```bash
npm --prefix frontend install
npm --prefix frontend exec -- tauri dev
```

开发命令会启动前端开发服务器并打开 Tauri 窗口。生产构建使用：

```powershell
$env:RUST_MIN_STACK='67108864'
$env:CARGO_BUILD_JOBS='2'
npm --prefix frontend exec -- tauri build --bundles nsis
```

Windows 上必须设置这两个环境变量（默认大栈与全量并行会打爆提交内存），详见[贡献指南](docs/CONTRIBUTING.md)。

## 文档

- [用户指南](docs/USER_GUIDE.md)：功能、快捷键、数据目录和配置
- [贡献指南](docs/CONTRIBUTING.md)：开发、测试、构建和提交规范
- [版本发布](https://github.com/Zomcxj/MemoPaws/releases)：Windows 安装包与发布说明

## 许可

本项目采用 [MIT License](LICENSE)。
