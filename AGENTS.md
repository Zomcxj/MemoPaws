# AGENTS.md

## ⚠️ 最高优先级规则

- **修复后自动提交导出** — 用户已明确要求（2026-08-18）：每次功能修复/变更完成并通过测试后，**直接执行** `git commit`（本地）并以 `RUST_MIN_STACK=67108864 CARGO_BUILD_JOBS=2 npm --prefix frontend exec -- tauri build --bundles nsis` 导出安装包，**不再询问**。唯一例外：涉及删除/重写用户数据、或用户明确说"先别提交"时。
- 仅当用户询问流程或要求回退时才说明提交信息。

## 关键规则

- **时刻维护文档** — 文件功能变更后，必须同步更新相关文档（README、AGENTS.md、教程等）
- **文本替换审核** — 全局输入钩子仅在内存保留最多 64 个最近普通字符，不记录、上报或持久化用户输入；仅 Windows 启用。合成键盘事件必须带 `dwExtraInfo` 标记，钩子必须跳过该标记以防递归触发。
- **Python 环境**：使用 `D:/software/miniforge3/envs/llm/python.exe`，不是系统 Python
- **数据目录**：`%USERPROFILE%\.memopaws\`（setting.json 配置、keys.json 加密密钥库）；API Key 永不入 setting.json
- **测试隔离**：仅原生 E2E 子进程可设置 `MEMOPAWS_HOME` 指向临时目录；正常运行不设置时仍使用 `%USERPROFILE%\.memopaws\`
- **构建命令**：必须 `RUST_MIN_STACK=67108864 CARGO_BUILD_JOBS=2`（大栈/全量并行会打爆 Windows 提交内存）
- **Git 规范**：变更通过全部测试（Rust + e2e）后直接提交本地，不推送远程
- 遵循全局AGENTS.md
