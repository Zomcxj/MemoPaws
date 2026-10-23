# AGENTS.md

## ⚠️ 最高优先级规则

- **修复后自动提交导出** — 用户已明确要求（2026-08-18）：每次功能修复/变更完成并通过测试后，**直接执行** `git commit`（本地）并以 `RUST_MIN_STACK=67108864 CARGO_BUILD_JOBS=2 npm --prefix frontend exec -- tauri build --bundles nsis` 导出安装包，**不再询问**。唯一例外：涉及删除/重写用户数据、或用户明确说"先别提交"时。
- 仅当用户询问流程或要求回退时才说明提交信息。

## 关键规则

- **时刻维护文档** — 文件功能变更后，必须同步更新相关文档（README、AGENTS.md、教程等）
- **文本替换审核** — 全局输入钩子仅在内存保留最多 64 个最近普通字符，不记录、上报或持久化用户输入；仅 Windows 启用。合成键盘事件必须带 `dwExtraInfo` 标记，钩子必须跳过该标记以防递归触发。
- **Python 环境**：使用 `D:/software/miniforge3/envs/llm/python.exe`，不是系统 Python
- **数据目录**：`%USERPROFILE%\.memopaws\`（setting.json 配置、keys.json 加密密钥库）；API Key 永不入 setting.json
- **钉图状态归属**：钉图图片/会话可见性保存在 Rust `pinned_images` 注册表（按窗口标签隔离，按调用窗口身份取图/关闭）；前端不得保存恢复状态或传递任意标签，主窗恢复只由 Rust 销毁钩子在最后一张钉图关闭时执行
- **标注坐标空间**：标注点一律存原图（截图）像素坐标（`frontend/src/annotation/model.ts`），与 CSS 显示缩放无关；预览与导出共用 `annotation/render.ts` 的同一合成器（drawMarks/composePng），所有浮层动作经 `imageForSelection()` 取同一张"标注后 PNG"再分发；旧标记的 color/width 随标记定格，回放时不得读当前工具栏状态
- **离线 OCR 边界**：本地识别只走 `crates/tauri/src/local_ocr.rs`（Windows.Media.Ocr），禁止访问 ai_client/vault/reqwest/遥测，禁止自动安装语言包或静默回退到云识别；图片解码有 128MiB RGBA 预算（`decode_limited_with_rgba_limit`），原图字节不改写、不落盘，历史只存文本
- **测试隔离**：仅原生 E2E 子进程可设置 `MEMOPAWS_HOME` 指向临时目录；正常运行不设置时仍使用 `%USERPROFILE%\.memopaws\`
- **构建命令**：必须 `RUST_MIN_STACK=67108864 CARGO_BUILD_JOBS=2`，且**显式去掉 `REMOVE_UNUSED_COMMANDS`**（`env -u REMOVE_UNUSED_COMMANDS ...`）。该变量被设成了用户级全局环境变量（指向 `F:\VibeCoding_workspace\Verta\src-tauri`），tauri 构建脚本会按 **Verta 的命令清单**在编译期剥离 MemoPaws 的窗口命令（`plugin:window|hide`/`set_position`/`set_size`/`set_fullscreen` 曾因此消失，运行时报 `Command hide not found`）。2026-10-23 发现。
- **Git 规范**：变更通过全部测试（Rust + e2e）后直接提交本地，不推送远程（用户明确要求时除外）。已装 pre-commit 钩子（`.githooks/pre-commit`），提交时自动跑 `cargo test --workspace` + 静态契约，勿用 `--no-verify` 绕过，除非已手动验证
- 遵循全局AGENTS.md
