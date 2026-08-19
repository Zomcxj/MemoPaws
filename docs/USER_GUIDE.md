# 用户指南

## 功能

MemoPaws 提供以下功能：

- **备忘录**：Markdown 笔记、搜索、渲染、本地持久化和数据迁移
- **密钥管理**：加密密钥库、主密码锁定/解锁、增删改查和排序
- **剪贴板历史**：文本与图片记录、搜索、锁定和批量删除
- **AI 识别与翻译**：截图、OCR、图像预处理、裁剪、标注和翻译
- **文字替换**：Windows 全局键盘钩子驱动的缩写替换
- **快捷键与托盘**：可配置的全局快捷键、系统托盘和关闭行为

## 全局快捷键

| 动作 | 默认快捷键 | 说明 |
|---|---|---|
| `capture` | `Alt+X` | 触发屏幕截图 |
| `canvas_fit` | `Ctrl+F` | 画布自适应缩放 |
| `new_memo` | `Ctrl+N` | 新建备忘录 |
| `global_search` | `Ctrl+Shift+F` | 打开全局搜索 |
| `toggle_clipboard` | `Ctrl+Shift+V` | 切换剪贴板历史 |

所有快捷键都可以在设置页面中修改。

## 数据存储

应用数据默认存储在 `%USERPROFILE%/.memopaws-rust/`，包含：

| 路径 | 内容 |
|---|---|
| `memo/` | 备忘录文件 |
| `keys.json` | 加密密钥库 |
| `clipboard.json` | 剪贴板历史 |
| `history.json` | 操作历史 |
| `setting.json` | 应用配置 |
| `clipboard_images/` | 剪贴板图片 |
| `captures/` | 截图文件 |

数据目录可以在设置中迁移，支持 Merge 和 Replace 两种模式。

## 配置

配置文件为数据目录下的 `setting.json`，常用字段如下：

- `theme`：主题，支持 `dark` 和 `light`
- `language`：界面语言
- `close_behavior`：关闭行为，支持 `exit` 和 `tray`
- `api_key`、`api_url`、`api_model`：AI 服务配置
- `shortcuts`：快捷键覆盖
- `text_replacements`：文字替换规则
- `clipboard_max_items`、`history_max_items`：历史记录上限

API Key 也可以通过应用内的密钥管理页面保存。旧配置中的未知字段会被忽略，以便未来版本兼容读取。
