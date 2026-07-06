# 开发与构建规范

本文档记录 MemoPaws 的开发、测试和打包。

## Python 环境

项目使用 Python 3.12。开发和测试前先激活本地虚拟环境，不使用系统 Python。

```bash
python main.py
```

安装运行依赖：

```bash
python -m pip install -r requirements.txt
```

## 运行

```bash
python main.py
```

应用数据默认位于用户主目录下的 `.memopaws/`。锚点文件 `.memopaws.json` 记录实际存储目录。

## 测试

完整测试命令：

```bash
python -m pytest tests/ --tb=short -q
```

涉及 Qt 的测试使用 offscreen 环境，测试配置位于 `tests/conftest.py`。

新增非平凡逻辑时，应补最小可运行测试。优先复用现有测试风格，不新增测试框架。

## 构建

统一使用 `build.sh`。

| 命令 | 输出 | 说明 |
|------|------|------|
| `bash build.sh` | `dist/MemoPaws/` | onedir 发布构建。 |
| `bash build.sh fast` | `dist/MemoPaws/` | 复用缓存的快速构建。 |
| `bash build.sh portable` | `dist/MemoPaws_Portable.exe` | onefile 便携版。 |

Windows 下脚本会优先使用已激活或项目约定的 Python 环境，并在 onefile 包中加入 conda 环境的 OpenSSL DLL，避免 `_ssl` 在 HTTPS/API/OCR 场景加载失败。

构建产物 `build/`、`dist/` 和 `*.spec` 不纳入版本管理。

## 配置和数据

配置和运行数据写入 `.memopaws` 数据目录。设置页支持迁移存储目录，迁移时会移动整个 `.memopaws` 文件夹。

涉及 API Key、主密码、密钥库和本地数据的文件不得提交。

## 代码组织

- UI 页面按功能目录组织，避免单文件继续膨胀。
- `core/` 只放通用能力，例如路径、主题、URL 规范化和图标加载。
- `config/` 负责设置页、快捷键、配置迁移和历史设置。
- `ocr/` 负责 OCR 和翻译，不直接承担页面布局。
- `memo/`、`keys/`、`clipboard/`、`canvas/` 分别维护各自页面和业务逻辑。

修改文件职责或新增模块时，应同步更新 `docs/project-structure.md`。

## UI 文案和语言

用户可见文案应保持中文可用，并兼容英文界面切换。语言切换优先更新现有控件文本，避免不必要地重建卡片或列表。
