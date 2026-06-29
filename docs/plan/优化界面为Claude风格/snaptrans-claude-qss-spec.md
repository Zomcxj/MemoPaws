# Claude Design System -- PySide6 QSS 暗色主题样式规范

> 本文档是 Claude Design System 暗色模式 (Dark Mode) 到 PySide6 QSS (Qt Style Sheet) 的完整映射规范。
> AI 编码代理可直接参照本文档修改 PySide6 桌面应用的视觉样式。

---

## 1. 颜色变量映射表

### 1.1 语义色 (Semantic Colors)

以下为 Claude 暗色模式语义 token 与 QSS 可用十六进制值的直接映射：

| 语义 Token | 色值 | 用途说明 |
|---|---|---|
| `--background` | `#262624` | 主窗口背景 |
| `--card` | `#2C2C2B` | 卡片/面板背景 |
| `--popover` | `#30302E` | 弹出层/浮层背景 |
| `--muted` | `#1B1B19` | 静音/禁用区域背景 |
| `--foreground` | `#F1F1EF` | 主文本颜色 |
| `--card-foreground` | `#FAF9F5` | 卡片内文本 |
| `--popover-foreground` | `#E5E5E2` | 弹出层文本 |
| `--primary-foreground` | `#141413` | 主色按钮上的文字 |
| `--secondary-foreground` | `#30302E` | 次要按钮上的文字 |
| `--muted-foreground` | `#B7B5A9` | 静音/辅助文本 |
| `--accent-foreground` | `#F5F4EE` | 强调区域文字 |
| `--destructive-foreground` | `#FFFFFF` | 危险按钮文字 |
| `--primary` | `#D97757` | 品牌主色/强调色 |
| `--secondary` | `#FAF9F5` | 次要色 |
| `--accent` | `#1A1915` | 强调背景 |
| `--input` | `#52514A` | 输入框边框 |
| `--ring` | `#D97757` | 焦点环颜色 |
| `--border` | `#3E3E38` | 默认边框 |
| `--destructive` | `#EF4444` | 危险/错误色 |
| `--success` | `#8CA06F` | 成功色 |
| `--success-foreground` | `#141413` | 成功区域文字 |
| `--error` | `#EF4444` | 错误色 |
| `--error-foreground` | `#FFFFFF` | 错误区域文字 |

### 1.2 侧边栏专用色

| 语义 Token | 色值 | 用途说明 |
|---|---|---|
| `--sidebar` | `#1F1E1D` | 侧边栏背景 |
| `--sidebar-foreground` | `#C3C0B6` | 侧边栏文本 |
| `--sidebar-primary` | `#343434` | 侧边栏主色元素背景 |
| `--sidebar-primary-foreground` | `#FBFBFB` | 侧边栏主色元素文字 |
| `--sidebar-accent` | `#0F0F0E` | 侧边栏高亮项背景 |
| `--sidebar-accent-foreground` | `#C3C0B6` | 侧边栏高亮项文字 |
| `--sidebar-border` | `#EBEBEB` | 侧边栏边框 |
| `--sidebar-ring` | `#B5B5B5` | 侧边栏焦点环 |

### 1.3 品牌色阶 (Brand Scale)

| Token | 色值 |
|---|---|
| `--brand-50` | `#3A2A22` |
| `--brand-100` | `#4D3528` |
| `--brand-200` | `#6B4533` |
| `--brand-300` | `#8A5740` |
| `--brand-400` | `#B0683F` |
| `--brand-500` | `#D97757` |
| `--brand-600` | `#E08D6F` |
| `--brand-700` | `#E8A98F` |
| `--brand-800` | `#F0C6B3` |
| `--brand-900` | `#F8E3D8` |

### 1.4 文本色阶 (Text Scale)

| Token | 色值 |
|---|---|
| `--text-50` | `#1B1B19` |
| `--text-100` | `#2C2C2B` |
| `--text-200` | `#46443B` |
| `--text-300` | `#6E6D68` |
| `--text-400` | `#908E84` |
| `--text-500` | `#B7B5A9` |
| `--text-600` | `#C3C0B6` |
| `--text-700` | `#D8D6CD` |
| `--text-800` | `#F1F1EF` |
| `--text-900` | `#FAF9F5` |

### 1.5 背景色阶 (Background Scale)

| Token | 色值 |
|---|---|
| `--bg-50` | `#1B1B19` |
| `--bg-100` | `#262624` |
| `--bg-200` | `#2C2C2B` |
| `--bg-300` | `#30302E` |
| `--bg-400` | `#3E3E38` |
| `--bg-500` | `#4A4A43` |
| `--bg-600` | `#52514A` |
| `--bg-700` | `#6E6D68` |
| `--bg-800` | `#908E84` |
| `--bg-900` | `#B7B5A9` |

### 1.6 边框色阶 (Border Scale)

| Token | 色值 |
|---|---|
| `--border-50` | `#1F1E1D` |
| `--border-100` | `#2C2C2B` |
| `--border-200` | `#343430` |
| `--border-300` | `#3E3E38` |
| `--border-400` | `#4A4A43` |
| `--border-500` | `#52514A` |
| `--border-600` | `#6E6D68` |
| `--border-700` | `#908E84` |
| `--border-800` | `#B7B5A9` |
| `--border-900` | `#D8D6CD` |

### 1.7 状态色阶 (Success / Error)

**Success:**

| Token | 色值 |
|---|---|
| `--success-50` | `#232A1C` |
| `--success-100` | `#2E3823` |
| `--success-200` | `#3F4D30` |
| `--success-300` | `#556640` |
| `--success-400` | `#708353` |
| `--success-500` | `#8CA06F` |
| `--success-600` | `#A3B58A` |
| `--success-700` | `#BCCAA8` |
| `--success-800` | `#D6DFC8` |
| `--success-900` | `#EDF2E4` |

**Error:**

| Token | 色值 |
|---|---|
| `--error-50` | `#3A1F1F` |
| `--error-100` | `#4D2424` |
| `--error-200` | `#6E2C2C` |
| `--error-300` | `#93302F` |
| `--error-400` | `#C43A39` |
| `--error-500` | `#EF4444` |
| `--error-600` | `#F26B6B` |
| `--error-700` | `#F59292` |
| `--error-800` | `#F9B9B9` |
| `--error-900` | `#FCDEDE` |

---

## 2. QSS 变量定义

> **注意:** QSS 原生不支持 CSS 变量 (`var()`)。以下约定在 Python 端通过字符串模板或常量字典注入实际色值。
> 建议在 Python 中定义一个 `CLAUDE_TOKENS` 字典，然后在生成 QSS 字符串时用 `.format()` 或 f-string 替换。

### 2.1 Python 端 Token 字典 (建议实现)

```python
CLAUDE_DARK_TOKENS = {
    # === 语义色 ===
    "background":          "#262624",
    "card":                "#2C2C2B",
    "popover":             "#30302E",
    "muted":               "#1B1B19",
    "foreground":          "#F1F1EF",
    "card_foreground":     "#FAF9F5",
    "popover_foreground":  "#E5E5E2",
    "primary_foreground":  "#141413",
    "secondary_foreground":"#30302E",
    "muted_foreground":    "#B7B5A9",
    "accent_foreground":   "#F5F4EE",
    "destructive_foreground": "#FFFFFF",
    "primary":             "#D97757",
    "secondary":           "#FAF9F5",
    "accent":              "#1A1915",
    "input_border":        "#52514A",
    "ring":                "#D97757",
    "border":              "#3E3E38",
    "border_subtle":       "#353533",
    "destructive":         "#EF4444",
    "success":             "#8CA06F",
    "success_foreground":  "#141413",
    "error":               "#EF4444",
    "error_foreground":    "#FFFFFF",
    "elevated":            "#3E3E38",

    # === 侧边栏 ===
    "sidebar":             "#1F1E1D",
    "sidebar_foreground": "#C3C0B6",
    "sidebar_primary":    "#343434",
    "sidebar_primary_fg": "#FBFBFB",
    "sidebar_accent":     "#0F0F0E",
    "sidebar_accent_fg":  "#C3C0B6",
    "sidebar_border":     "#EBEBEB",
    "sidebar_ring":       "#B5B5B5",

    # === 圆角 ===
    "radius_sm":           "8px",
    "radius_md":           "12px",
    "radius":              "16px",
    "radius_xl":          "20px",
    "radius_2xl":         "24px",
    "radius_full":        "9999px",

    # === 字体 ===
    "font_sans":           "Poppins, 'Segoe UI', 'Microsoft YaHei', sans-serif",
    "font_serif":          "Lora, Georgia, serif",
    "font_display":        "Newsreader, Georgia, serif",
    "font_mono":           "'Geist Mono', 'JetBrains Mono', Consolas, monospace",

    # === 阴影 (QSS 不支持 box-shadow，用 border 模拟或忽略) ===
    "shadow_color":        "rgba(0, 0, 0, 0.10)",
}
```

### 2.2 QSS 字符串中使用变量的约定

在 QSS 字符串中，使用 `{token_name}` 占位符，在 Python 端通过 `.format(**CLAUDE_DARK_TOKENS)` 注入：

```python
QSS_TEMPLATE = """
QWidget {{
    background-color: {background};
    color: {foreground};
    font-family: {font_sans};
}}
"""

final_qss = QSS_TEMPLATE.format(**CLAUDE_DARK_TOKENS)
```

---

## 3. 全局基础样式

### 3.1 QWidget / QMainWindow

```css
/* === 全局基础 === */
QWidget {
    background-color: #262624;
    color: #F1F1EF;
    font-family: Poppins, "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 14px;
    selection-background-color: #D97757;
    selection-color: #141413;
}

QMainWindow {
    background-color: #262624;
}

QApplication {
    background-color: #262624;
}
```

**要点:**
- 主背景统一使用 `#262624`
- 文字选中态使用品牌色 `#D97757` 作为背景，深色文字 `#141413`
- 字体回退链: Poppins -> Segoe UI -> Microsoft YaHei -> sans-serif (确保中文系统兼容)

---

## 4. 侧边栏导航 (Sidebar)

### 4.1 侧边栏容器 (QFrame 或 QWidget)

```css
/* === 侧边栏容器 === */
QFrame#sidebar,
QWidget#sidebar {
    background-color: #1F1E1D;
    border-right: 1px solid #3E3E38;
}

/* 侧边栏内容区域 */
QFrame#sidebarContent {
    background-color: #1F1E1D;
    color: #C3C0B6;
}
```

### 4.2 侧边栏导航项 (QPushButton 作为导航按钮)

```css
/* === 侧边栏导航按钮 === */
QPushButton#navButton {
    background-color: transparent;
    color: #C3C0B6;
    border: none;
    border-radius: 8px;
    padding: 10px 16px;
    font-size: 14px;
    font-weight: 500;
    text-align: left;
    min-height: 40px;
}

QPushButton#navButton:hover {
    background-color: #0F0F0E;
    color: #C3C0B6;
}

QPushButton#navButton:checked,
QPushButton#navButton:selected {
    background-color: #343434;
    color: #FBFBFB;
}

QPushButton#navButton:pressed {
    background-color: #2C2C2B;
}
```

### 4.3 侧边栏标题 / Logo 区域

```css
QLabel#sidebarLogo {
    color: #FBFBFB;
    font-family: Newsreader, Georgia, serif;
    font-size: 20px;
    font-weight: 500;
    padding: 16px;
}

QLabel#sidebarSectionTitle {
    color: #B7B5A9;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    padding: 8px 16px 4px 16px;
}
```

---

## 5. 卡片 / 面板 (Cards / Panels)

### 5.1 基础卡片 (QFrame)

```css
/* === 卡片 === */
QFrame#card,
QFrame[class="card"] {
    background-color: #2C2C2B;
    border: 1px solid #3E3E38;
    border-radius: 12px;
    padding: 20px;
}

/* 卡片悬停效果 */
QFrame#card:hover {
    border-color: #52514A;
}
```

### 5.2 提升层级卡片 (Elevated Card)

```css
QFrame#elevatedCard {
    background-color: #3E3E38;
    border: 1px solid #4A4A43;
    border-radius: 12px;
    padding: 20px;
}
```

### 5.3 卡片标题 (QLabel)

```css
QLabel#cardTitle {
    color: #FAF9F5;
    font-size: 16px;
    font-weight: 600;
}

QLabel#cardSubtitle {
    color: #B7B5A9;
    font-size: 13px;
}

QLabel#cardDescription {
    color: #C3C0B6;
    font-size: 14px;
    font-family: Lora, Georgia, serif;
    line-height: 1.6;
}
```

### 5.4 分隔线

```css
QFrame#divider,
QFrame[class="divider"] {
    color: #3E3E38;
    max-height: 1px;
    border: none;
    border-top: 1px solid #3E3E38;
}

/* 更细的分隔线 */
QFrame#dividerSubtle {
    color: #353533;
    max-height: 1px;
    border: none;
    border-top: 1px solid #353533;
}
```

---

## 6. 按钮 (Buttons)

### 6.1 主按钮 (Primary Button)

```css
/* === 主按钮 === */
QPushButton#primaryButton,
QPushButton[class="primary"] {
    background-color: #D97757;
    color: #141413;
    border: none;
    border-radius: 16px;
    padding: 10px 24px;
    font-size: 14px;
    font-weight: 600;
    min-height: 40px;
    min-width: 80px;
}

QPushButton#primaryButton:hover,
QPushButton[class="primary"]:hover {
    background-color: #E08D6F;
}

QPushButton#primaryButton:pressed,
QPushButton[class="primary"]:pressed {
    background-color: #B0683F;
}

QPushButton#primaryButton:disabled,
QPushButton[class="primary"]:disabled {
    background-color: #6E6D68;
    color: #908E84;
}
```

### 6.2 次要按钮 (Secondary Button)

```css
/* === 次要按钮 === */
QPushButton#secondaryButton,
QPushButton[class="secondary"] {
    background-color: #FAF9F5;
    color: #30302E;
    border: none;
    border-radius: 16px;
    padding: 10px 24px;
    font-size: 14px;
    font-weight: 600;
    min-height: 40px;
}

QPushButton#secondaryButton:hover,
QPushButton[class="secondary"]:hover {
    background-color: #E5E5E2;
}

QPushButton#secondaryButton:pressed,
QPushButton[class="secondary"]:pressed {
    background-color: #D8D6CD;
}

QPushButton#secondaryButton:disabled,
QPushButton[class="secondary"]:disabled {
    background-color: #3E3E38;
    color: #908E84;
}
```

### 6.3 幽灵按钮 (Ghost Button)

```css
/* === 幽灵按钮 === */
QPushButton#ghostButton,
QPushButton[class="ghost"] {
    background-color: transparent;
    color: #F1F1EF;
    border: none;
    border-radius: 16px;
    padding: 10px 24px;
    font-size: 14px;
    font-weight: 500;
    min-height: 40px;
}

QPushButton#ghostButton:hover,
QPushButton[class="ghost"]:hover {
    background-color: #3E3E38;
}

QPushButton#ghostButton:pressed,
QPushButton[class="ghost"]:pressed {
    background-color: #2C2C2B;
}

QPushButton#ghostButton:disabled,
QPushButton[class="ghost"]:disabled {
    color: #6E6D68;
}
```

### 6.4 危险按钮 (Destructive Button)

```css
/* === 危险按钮 === */
QPushButton#destructiveButton,
QPushButton[class="destructive"] {
    background-color: #EF4444;
    color: #FFFFFF;
    border: none;
    border-radius: 16px;
    padding: 10px 24px;
    font-size: 14px;
    font-weight: 600;
    min-height: 40px;
}

QPushButton#destructiveButton:hover,
QPushButton[class="destructive"]:hover {
    background-color: #F26B6B;
}

QPushButton#destructiveButton:pressed,
QPushButton[class="destructive"]:pressed {
    background-color: #C43A39;
}
```

### 6.5 成功按钮 (Success Button)

```css
/* === 成功按钮 === */
QPushButton#successButton,
QPushButton[class="success"] {
    background-color: #8CA06F;
    color: #141413;
    border: none;
    border-radius: 16px;
    padding: 10px 24px;
    font-size: 14px;
    font-weight: 600;
    min-height: 40px;
}

QPushButton#successButton:hover,
QPushButton[class="success"]:hover {
    background-color: #A3B58A;
}

QPushButton#successButton:pressed,
QPushButton[class="success"]:pressed {
    background-color: #708353;
}
```

### 6.6 图标按钮 (Icon Button)

```css
/* === 图标按钮 === */
QPushButton#iconButton,
QPushButton[class="icon"] {
    background-color: transparent;
    color: #B7B5A9;
    border: none;
    border-radius: 8px;
    padding: 8px;
    min-width: 36px;
    min-height: 36px;
    max-width: 36px;
    max-height: 36px;
}

QPushButton#iconButton:hover,
QPushButton[class="icon"]:hover {
    background-color: #3E3E38;
    color: #F1F1EF;
}

QPushButton#iconButton:pressed,
QPushButton[class="icon"]:pressed {
    background-color: #2C2C2B;
}
```

---

## 7. 输入框 (Input Fields)

### 7.1 单行输入 (QLineEdit)

```css
/* === 单行输入框 === */
QLineEdit {
    background-color: #1B1B19;
    color: #F1F1EF;
    border: 1px solid #52514A;
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 14px;
    font-family: Poppins, "Segoe UI", "Microsoft YaHei", sans-serif;
    min-height: 40px;
    selection-background-color: #D97757;
    selection-color: #141413;
}

QLineEdit:hover {
    border-color: #6E6D68;
}

QLineEdit:focus {
    border-color: #D97757;
    border-width: 2px;
    padding: 9px 13px;  /* 补偿 border-width 增加 */
}

QLineEdit:disabled {
    background-color: #1B1B19;
    color: #6E6D68;
    border-color: #353533;
}

QLineEdit::placeholder {
    color: #6E6D68;
}

/* 只读状态 */
QLineEdit[readOnly="true"] {
    background-color: #2C2C2B;
    border-color: #353533;
    color: #B7B5A9;
}
```

### 7.2 多行文本编辑 (QTextEdit / QPlainTextEdit)

```css
/* === 多行文本编辑 === */
QTextEdit,
QPlainTextEdit {
    background-color: #1B1B19;
    color: #F1F1EF;
    border: 1px solid #52514A;
    border-radius: 8px;
    padding: 12px 14px;
    font-size: 14px;
    selection-background-color: #D97757;
    selection-color: #141413;
}

QTextEdit:focus,
QPlainTextEdit:focus {
    border-color: #D97757;
    border-width: 2px;
    padding: 11px 13px;
}

QTextEdit:disabled,
QPlainTextEdit:disabled {
    background-color: #1B1B19;
    color: #6E6D68;
    border-color: #353533;
}
```

### 7.3 数值输入 (QSpinBox / QDoubleSpinBox)

```css
/* === 数值输入框 === */
QSpinBox,
QDoubleSpinBox {
    background-color: #1B1B19;
    color: #F1F1EF;
    border: 1px solid #52514A;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 14px;
    min-height: 40px;
    selection-background-color: #D97757;
    selection-color: #141413;
}

QSpinBox:focus,
QDoubleSpinBox:focus {
    border-color: #D97757;
    border-width: 2px;
    padding: 7px 11px;
}

/* 上下箭头按钮 */
QSpinBox::up-button,
QDoubleSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 20px;
    border-left: 1px solid #52514A;
    border-top-right-radius: 8px;
    background-color: transparent;
}

QSpinBox::up-button:hover,
QDoubleSpinBox::up-button:hover {
    background-color: #3E3E38;
}

QSpinBox::up-arrow,
QDoubleSpinBox::up-arrow {
    width: 8px;
    height: 8px;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid #B7B5A9;
}

QSpinBox::down-button,
QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 20px;
    border-left: 1px solid #52514A;
    border-bottom-right-radius: 8px;
    background-color: transparent;
}

QSpinBox::down-button:hover,
QDoubleSpinBox::down-button:hover {
    background-color: #3E3E38;
}

QSpinBox::down-arrow,
QDoubleSpinBox::down-arrow {
    width: 8px;
    height: 8px;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #B7B5A9;
}
```

### 7.4 搜索框 (QLineEdit#searchInput)

```css
QLineEdit#searchInput {
    background-color: #1B1B19;
    color: #F1F1EF;
    border: 1px solid #52514A;
    border-radius: 9999px;  /* 全圆角搜索框 */
    padding: 10px 14px 10px 40px;  /* 左侧留图标空间 */
    font-size: 14px;
    min-height: 40px;
}

QLineEdit#searchInput:focus {
    border-color: #D97757;
}
```

---

## 8. 开关 / 分段控件 (Toggle / Segment Controls)

### 8.1 自定义开关 (QCheckBox 模拟 Toggle)

> QSS 不支持原生 toggle switch。推荐使用 QCheckBox 配合自定义样式模拟，或使用自定义 QWidget 绘制。

```css
/* === Toggle Switch (使用 QCheckBox 模拟) === */
QCheckBox#toggleSwitch {
    spacing: 10px;
    color: #F1F1EF;
    font-size: 14px;
}

QCheckBox#toggleSwitch::indicator {
    width: 44px;
    height: 24px;
    border-radius: 12px;
    border: none;
    background-color: #52514A;
}

QCheckBox#toggleSwitch::indicator:unchecked {
    background-color: #52514A;
}

QCheckBox#toggleSwitch::indicator:checked {
    background-color: #D97757;
}

QCheckBox#toggleSwitch::indicator:hover {
    border: 1px solid #6E6D68;
}

/* 开关圆点通过自定义 QWidget 绘制，QSS 无法实现内部圆点 */
```

### 8.2 复选框 (QCheckBox)

```css
/* === 复选框 === */
QCheckBox {
    color: #F1F1EF;
    font-size: 14px;
    spacing: 8px;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 2px solid #52514A;
    border-radius: 4px;
    background-color: #1B1B19;
}

QCheckBox::indicator:hover {
    border-color: #6E6D68;
}

QCheckBox::indicator:checked {
    background-color: #D97757;
    border-color: #D97757;
    image: url();  /* 使用自定义 checkmark 图标 */
}

QCheckBox::indicator:disabled {
    background-color: #2C2C2B;
    border-color: #353533;
}
```

### 8.3 单选按钮 (QRadioButton)

```css
/* === 单选按钮 === */
QRadioButton {
    color: #F1F1EF;
    font-size: 14px;
    spacing: 8px;
}

QRadioButton::indicator {
    width: 18px;
    height: 18px;
    border: 2px solid #52514A;
    border-radius: 9px;
    background-color: #1B1B19;
}

QRadioButton::indicator:hover {
    border-color: #6E6D68;
}

QRadioButton::indicator:checked {
    background-color: #D97757;
    border-color: #D97757;
}

QRadioButton::indicator:disabled {
    background-color: #2C2C2B;
    border-color: #353533;
}
```

### 8.4 分段控件 (使用 QButtonGroup + QPushButton)

```css
/* === 分段控件容器 === */
QFrame#segmentControl {
    background-color: #1B1B19;
    border: 1px solid #3E3E38;
    border-radius: 8px;
    padding: 2px;
}

QFrame#segmentControl QPushButton {
    background-color: transparent;
    color: #B7B5A9;
    border: none;
    border-radius: 6px;
    padding: 6px 16px;
    font-size: 13px;
    font-weight: 500;
}

QFrame#segmentControl QPushButton:checked {
    background-color: #3E3E38;
    color: #F1F1EF;
}

QFrame#segmentControl QPushButton:hover:!checked {
    background-color: #2C2C2B;
    color: #C3C0B6;
}
```

---

## 9. 列表 (Lists)

### 9.1 QListWidget

```css
/* === 列表容器 === */
QListWidget {
    background-color: #262624;
    color: #F1F1EF;
    border: 1px solid #3E3E38;
    border-radius: 12px;
    padding: 8px;
    font-size: 14px;
    outline: none;
}

QListWidget::item {
    padding: 10px 14px;
    border-radius: 8px;
    margin: 2px 0px;
}

QListWidget::item:hover {
    background-color: #3E3E38;
}

QListWidget::item:selected {
    background-color: #D97757;
    color: #141413;
}

QListWidget::item:selected:hover {
    background-color: #E08D6F;
}

QListWidget::item:disabled {
    color: #6E6D68;
}
```

### 9.2 QListView

```css
QListView {
    background-color: #262624;
    color: #F1F1EF;
    border: 1px solid #3E3E38;
    border-radius: 12px;
    padding: 8px;
    outline: none;
}

QListView::item {
    padding: 10px 14px;
    border-radius: 8px;
    margin: 2px 0px;
}

QListView::item:hover {
    background-color: #3E3E38;
}

QListView::item:selected {
    background-color: #D97757;
    color: #141413;
}
```

### 9.3 列表内嵌卡片样式

```css
/* 列表项作为卡片 */
QListWidget#cardList::item {
    background-color: #2C2C2B;
    border: 1px solid #3E3E38;
    border-radius: 12px;
    padding: 16px;
    margin: 4px;
}

QListWidget#cardList::item:hover {
    border-color: #52514A;
    background-color: #2C2C2B;
}

QListWidget#cardList::item:selected {
    border-color: #D97757;
    background-color: #2C2C2B;
    color: #F1F1EF;
}
```

---

## 10. 选项卡 (Tabs)

### 10.1 QTabWidget

```css
/* === 选项卡容器 === */
QTabWidget::pane {
    background-color: #262624;
    border: 1px solid #3E3E38;
    border-radius: 12px;
    border-top-left-radius: 0px;
    padding: 16px;
}

QTabWidget::pane:focus {
    border-color: #D97757;
}
```

### 10.2 QTabBar (顶部选项卡)

```css
/* === 选项卡栏 === */
QTabBar {
    background-color: transparent;
}

QTabBar::tab {
    background-color: transparent;
    color: #B7B5A9;
    border: none;
    border-bottom: 2px solid transparent;
    padding: 10px 20px;
    font-size: 14px;
    font-weight: 500;
    min-width: 80px;
}

QTabBar::tab:hover {
    color: #F1F1EF;
    background-color: #3E3E38;
    border-radius: 8px 8px 0px 0px;
}

QTabBar::tab:selected {
    color: #F1F1EF;
    border-bottom: 2px solid #D97757;
}

QTabBar::tab:disabled {
    color: #6E6D68;
}
```

### 10.3 QTabBar (胶囊/药丸风格)

```css
/* === 胶囊选项卡 === */
QTabBar#pillTabBar::tab {
    background-color: transparent;
    color: #B7B5A9;
    border: none;
    border-radius: 9999px;
    padding: 8px 20px;
    font-size: 13px;
    font-weight: 500;
    margin: 0px 2px;
}

QTabBar#pillTabBar::tab:hover {
    background-color: #3E3E38;
    color: #F1F1EF;
}

QTabBar#pillTabBar::tab:selected {
    background-color: #D97757;
    color: #141413;
}
```

---

## 11. 文本 / 字体设置 (Typography)

### 11.1 字体映射表

| Claude Token | 字体族 | PySide6 用途 |
|---|---|---|
| `--font-sans` | `Poppins, "Segoe UI", "Microsoft YaHei", sans-serif` | 全局 UI 字体、按钮、输入框、标签 |
| `--font-display` | `Newsreader, Georgia, serif` | 大标题、品牌展示文字 |
| `--font-serif` | `Lora, Georgia, serif` | 长文阅读区域、描述文本 |
| `--font-mono` | `"Geist Mono", "JetBrains Mono", Consolas, monospace` | 代码区域、数值显示、等宽文本 |

### 11.2 字号映射

| 用途 | 字号 | 字重 | QSS font 属性 |
|---|---|---|---|
| 大标题 (Display) | 32px | 400 | `font: 400 32px "Newsreader", Georgia, serif` |
| 标题 1 (H1) | 24px | 600 | `font: 600 24px "Poppins", sans-serif` |
| 标题 2 (H2) | 20px | 600 | `font: 600 20px "Poppins", sans-serif` |
| 标题 3 (H3) | 16px | 600 | `font: 600 16px "Poppins", sans-serif` |
| 正文 (Body) | 14px | 400 | `font: 400 14px "Poppins", sans-serif` |
| 正文加粗 (Body Bold) | 14px | 600 | `font: 600 14px "Poppins", sans-serif` |
| 辅助文本 (Caption) | 12px | 400 | `font: 400 12px "Poppins", sans-serif` |
| 标签 (Label) | 13px | 500 | `font: 500 13px "Poppins", sans-serif` |
| 小号标签 (Overline) | 11px | 600 | `font: 600 11px "Poppins", sans-serif` |
| 代码 (Code) | 13px | 400 | `font: 400 13px "Geist Mono", "JetBrains Mono", Consolas, monospace` |
| 按钮文字 | 14px | 600 | `font: 600 14px "Poppins", sans-serif` |

### 11.3 QLabel 样式变体

```css
/* === 标题标签 === */
QLabel#displayTitle {
    color: #FAF9F5;
    font-family: "Newsreader", Georgia, serif;
    font-size: 32px;
    font-weight: 400;
}

QLabel#heading1 {
    color: #FAF9F5;
    font-size: 24px;
    font-weight: 600;
}

QLabel#heading2 {
    color: #FAF9F5;
    font-size: 20px;
    font-weight: 600;
}

QLabel#heading3 {
    color: #FAF9F5;
    font-size: 16px;
    font-weight: 600;
}

/* === 正文标签 === */
QLabel#bodyText {
    color: #F1F1EF;
    font-size: 14px;
    font-weight: 400;
}

/* === 阅读文本 (Serif) === */
QLabel#readingText {
    color: #C3C0B6;
    font-family: "Lora", Georgia, serif;
    font-size: 15px;
    font-weight: 400;
    line-height: 1.7;
}

/* === 辅助文本 === */
QLabel#caption {
    color: #B7B5A9;
    font-size: 12px;
    font-weight: 400;
}

/* === 标签/小标题 === */
QLabel#overline {
    color: #B7B5A9;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
}

/* === 链接文本 === */
QLabel#link {
    color: #D97757;
    font-size: 14px;
    background-color: transparent;
}

QLabel#link:hover {
    color: #E08D6F;
}
```

---

## 12. 滚动条 (Scrollbars)

```css
/* === 垂直滚动条 === */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    border: none;
    margin: 4px 2px 4px 2px;
}

QScrollBar::handle:vertical {
    background-color: #52514A;
    border-radius: 4px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background-color: #6E6D68;
}

QScrollBar::handle:vertical:pressed {
    background-color: #908E84;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0px;
    border: none;
    background: none;
}

QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: none;
}

/* === 水平滚动条 === */
QScrollBar:horizontal {
    background: transparent;
    height: 8px;
    border: none;
    margin: 2px 4px 2px 4px;
}

QScrollBar::handle:horizontal {
    background-color: #52514A;
    border-radius: 4px;
    min-width: 30px;
}

QScrollBar::handle:horizontal:hover {
    background-color: #6E6D68;
}

QScrollBar::handle:horizontal:pressed {
    background-color: #908E84;
}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0px;
    border: none;
    background: none;
}

QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {
    background: none;
}

/* === 滚动条 - 侧边栏专用 (更窄) === */
QFrame#sidebar QScrollBar:vertical {
    width: 4px;
}

QFrame#sidebar QScrollBar::handle:vertical {
    background-color: #6E6D68;
    border-radius: 2px;
}
```

---

## 13. 滑块 (Sliders)

### 13.1 QSlider (水平)

```css
/* === 水平滑块 === */
QSlider::groove:horizontal {
    height: 4px;
    background-color: #3E3E38;
    border-radius: 2px;
}

QSlider::handle:horizontal {
    background-color: #D97757;
    width: 18px;
    height: 18px;
    margin: -7px 0;
    border-radius: 9px;
    border: 2px solid #262624;
}

QSlider::handle:horizontal:hover {
    background-color: #E08D6F;
}

QSlider::handle:horizontal:pressed {
    background-color: #B0683F;
}

QSlider::sub-page:horizontal {
    background-color: #D97757;
    border-radius: 2px;
}

QSlider::add-page:horizontal {
    background-color: #3E3E38;
    border-radius: 2px;
}

QSlider::groove:horizontal:disabled {
    background-color: #353533;
}

QSlider::handle:horizontal:disabled {
    background-color: #6E6D68;
}
```

### 13.2 QSlider (垂直)

```css
/* === 垂直滑块 === */
QSlider::groove:vertical {
    width: 4px;
    background-color: #3E3E38;
    border-radius: 2px;
}

QSlider::handle:vertical {
    background-color: #D97757;
    width: 18px;
    height: 18px;
    margin: 0 -7px;
    border-radius: 9px;
    border: 2px solid #262624;
}

QSlider::handle:vertical:hover {
    background-color: #E08D6F;
}

QSlider::sub-page:vertical {
    background-color: #D97757;
    border-radius: 2px;
}

QSlider::add-page:vertical {
    background-color: #3E3E38;
    border-radius: 2px;
}
```

---

## 14. 状态栏 (Status Bar)

```css
/* === 状态栏 === */
QStatusBar {
    background-color: #1B1B19;
    color: #B7B5A9;
    border-top: 1px solid #3E3E38;
    font-size: 12px;
    padding: 4px 12px;
}

QStatusBar::item {
    border: none;
    padding: 0px 8px;
}

QStatusBar QLabel {
    color: #B7B5A9;
    font-size: 12px;
    padding: 0px;
}

/* 状态栏中的品牌标签 */
QStatusBar QLabel#statusBrand {
    color: #D97757;
    font-weight: 600;
}

/* 状态栏中的成功状态 */
QStatusBar QLabel#statusSuccess {
    color: #8CA06F;
}

/* 状态栏中的错误状态 */
QStatusBar QLabel#statusError {
    color: #EF4444;
}
```

---

## 15. 代码块 / 等宽区域 (Code Block / Mono Areas)

### 15.1 代码显示区域 (QPlainTextEdit)

```css
/* === 代码编辑/显示区域 === */
QPlainTextEdit#codeBlock,
QTextEdit#codeBlock {
    background-color: #1B1B19;
    color: #F1F1EF;
    border: 1px solid #3E3E38;
    border-radius: 12px;
    padding: 16px;
    font-family: "Geist Mono", "JetBrains Mono", Consolas, monospace;
    font-size: 13px;
    line-height: 1.6;
    tab-width: 4;
    selection-background-color: rgba(217, 119, 87, 0.3);
    selection-color: #F1F1EF;
}
```

### 15.2 内联代码标签 (QLabel)

```css
/* === 内联代码 === */
QLabel#inlineCode {
    color: #E8A98F;
    font-family: "Geist Mono", "JetBrains Mono", Consolas, monospace;
    font-size: 13px;
    background-color: #1B1B19;
    border: 1px solid #353533;
    border-radius: 4px;
    padding: 2px 6px;
}
```

### 15.3 代码块头部 (文件名/语言标签)

```css
QLabel#codeBlockHeader {
    color: #B7B5A9;
    font-family: "Geist Mono", "JetBrains Mono", Consolas, monospace;
    font-size: 12px;
    background-color: #1F1E1D;
    border: 1px solid #3E3E38;
    border-bottom: none;
    border-radius: 12px 12px 0px 0px;
    padding: 8px 16px;
}
```

---

## 16. 补充组件样式

### 16.1 QComboBox (下拉选择框)

```css
/* === 下拉选择框 === */
QComboBox {
    background-color: #1B1B19;
    color: #F1F1EF;
    border: 1px solid #52514A;
    border-radius: 8px;
    padding: 8px 32px 8px 14px;
    font-size: 14px;
    min-height: 40px;
}

QComboBox:hover {
    border-color: #6E6D68;
}

QComboBox:focus {
    border-color: #D97757;
    border-width: 2px;
    padding: 7px 31px 7px 13px;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 28px;
    border-left: 1px solid #52514A;
    border-top-right-radius: 8px;
    border-bottom-right-radius: 8px;
    background-color: transparent;
}

QComboBox::down-arrow {
    width: 10px;
    height: 10px;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #B7B5A9;
}

/* 下拉列表 */
QComboBox QAbstractItemView {
    background-color: #2C2C2B;
    color: #F1F1EF;
    border: 1px solid #3E3E38;
    border-radius: 12px;
    padding: 8px;
    selection-background-color: #D97757;
    selection-color: #141413;
    outline: none;
}

QComboBox QAbstractItemView::item {
    padding: 8px 14px;
    border-radius: 6px;
    min-height: 32px;
}

QComboBox QAbstractItemView::item:hover {
    background-color: #3E3E38;
}
```

### 16.2 QToolTip

```css
/* === 工具提示 === */
QToolTip {
    background-color: #2C2C2B;
    color: #F1F1EF;
    border: 1px solid #3E3E38;
    border-radius: 8px;
    padding: 6px 12px;
    font-size: 12px;
    font-family: Poppins, "Segoe UI", "Microsoft YaHei", sans-serif;
}
```

### 16.3 QMenu

```css
/* === 菜单 === */
QMenu {
    background-color: #2C2C2B;
    color: #F1F1EF;
    border: 1px solid #3E3E38;
    border-radius: 12px;
    padding: 8px;
}

QMenu::item {
    padding: 8px 16px;
    border-radius: 6px;
    font-size: 14px;
}

QMenu::item:hover {
    background-color: #3E3E38;
}

QMenu::item:selected {
    background-color: #D97757;
    color: #141413;
}

QMenu::separator {
    height: 1px;
    background-color: #3E3E38;
    margin: 4px 8px;
}

QMenu::indicator {
    width: 16px;
    height: 16px;
    margin-left: 8px;
}
```

### 16.4 QProgressBar

```css
/* === 进度条 === */
QProgressBar {
    background-color: #3E3E38;
    border: none;
    border-radius: 9999px;
    min-height: 6px;
    max-height: 6px;
    text-align: center;
    color: #F1F1EF;
    font-size: 12px;
}

QProgressBar::chunk {
    background-color: #D97757;
    border-radius: 9999px;
}

/* 成功进度条 */
QProgressBar#successProgress::chunk {
    background-color: #8CA06F;
}

/* 错误进度条 */
QProgressBar#errorProgress::chunk {
    background-color: #EF4444;
}
```

### 16.5 QGroupBox

```css
/* === 分组框 === */
QGroupBox {
    color: #F1F1EF;
    font-size: 14px;
    font-weight: 600;
    border: 1px solid #3E3E38;
    border-radius: 12px;
    margin-top: 16px;
    padding: 20px 16px 16px 16px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 4px 12px;
    color: #B7B5A9;
    font-size: 13px;
    font-weight: 600;
}
```

### 16.6 QSplitter

```css
/* === 分割器 === */
QSplitter::handle:horizontal {
    width: 1px;
    background-color: #3E3E38;
}

QSplitter::handle:vertical {
    height: 1px;
    background-color: #3E3E38;
}

QSplitter::handle:hover {
    background-color: #D97757;
}
```

### 16.7 QDialog

```css
/* === 对话框 === */
QDialog {
    background-color: #262624;
    color: #F1F1EF;
}

QDialogButtonBox {
    background-color: transparent;
    spacing: 12px;
}

QDialogButtonBox QPushButton {
    min-width: 80px;
    min-height: 40px;
}
```

### 16.8 QMessageBox

```css
QMessageBox {
    background-color: #2C2C2B;
    border: 1px solid #3E3E38;
    border-radius: 12px;
}
```

---

## 17. 完整 QSS 模板 (可直接使用)

以下为整合后的完整 QSS 字符串模板，可直接复制到 Python 代码中使用：

```python
CLAUDE_DARK_QSS = """
/* ========================================
   Claude Design System - Dark Mode QSS
   ======================================== */

/* === 全局基础 === */
QWidget {
    background-color: #262624;
    color: #F1F1EF;
    font-family: Poppins, "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 14px;
    selection-background-color: #D97757;
    selection-color: #141413;
}

QMainWindow {
    background-color: #262624;
}

/* === 侧边栏 === */
QFrame#sidebar, QWidget#sidebar {
    background-color: #1F1E1D;
    border-right: 1px solid #3E3E38;
}

QPushButton#navButton {
    background-color: transparent;
    color: #C3C0B6;
    border: none;
    border-radius: 8px;
    padding: 10px 16px;
    font-size: 14px;
    font-weight: 500;
    text-align: left;
    min-height: 40px;
}
QPushButton#navButton:hover {
    background-color: #0F0F0E;
}
QPushButton#navButton:checked {
    background-color: #343434;
    color: #FBFBFB;
}

/* === 卡片 === */
QFrame#card {
    background-color: #2C2C2B;
    border: 1px solid #3E3E38;
    border-radius: 12px;
    padding: 20px;
}
QFrame#card:hover {
    border-color: #52514A;
}

/* === 主按钮 === */
QPushButton#primaryButton {
    background-color: #D97757;
    color: #141413;
    border: none;
    border-radius: 16px;
    padding: 10px 24px;
    font-size: 14px;
    font-weight: 600;
    min-height: 40px;
}
QPushButton#primaryButton:hover {
    background-color: #E08D6F;
}
QPushButton#primaryButton:pressed {
    background-color: #B0683F;
}
QPushButton#primaryButton:disabled {
    background-color: #6E6D68;
    color: #908E84;
}

/* === 次要按钮 === */
QPushButton#secondaryButton {
    background-color: #FAF9F5;
    color: #30302E;
    border: none;
    border-radius: 16px;
    padding: 10px 24px;
    font-size: 14px;
    font-weight: 600;
    min-height: 40px;
}
QPushButton#secondaryButton:hover {
    background-color: #E5E5E2;
}

/* === 幽灵按钮 === */
QPushButton#ghostButton {
    background-color: transparent;
    color: #F1F1EF;
    border: none;
    border-radius: 16px;
    padding: 10px 24px;
    font-size: 14px;
    font-weight: 500;
    min-height: 40px;
}
QPushButton#ghostButton:hover {
    background-color: #3E3E38;
}

/* === 危险按钮 === */
QPushButton#destructiveButton {
    background-color: #EF4444;
    color: #FFFFFF;
    border: none;
    border-radius: 16px;
    padding: 10px 24px;
    font-size: 14px;
    font-weight: 600;
    min-height: 40px;
}
QPushButton#destructiveButton:hover {
    background-color: #F26B6B;
}

/* === 输入框 === */
QLineEdit {
    background-color: #1B1B19;
    color: #F1F1EF;
    border: 1px solid #52514A;
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 14px;
    min-height: 40px;
    selection-background-color: #D97757;
    selection-color: #141413;
}
QLineEdit:hover {
    border-color: #6E6D68;
}
QLineEdit:focus {
    border-color: #D97757;
    border-width: 2px;
    padding: 9px 13px;
}
QLineEdit:disabled {
    background-color: #1B1B19;
    color: #6E6D68;
    border-color: #353533;
}

QTextEdit, QPlainTextEdit {
    background-color: #1B1B19;
    color: #F1F1EF;
    border: 1px solid #52514A;
    border-radius: 8px;
    padding: 12px 14px;
    font-size: 14px;
    selection-background-color: #D97757;
    selection-color: #141413;
}
QTextEdit:focus, QPlainTextEdit:focus {
    border-color: #D97757;
    border-width: 2px;
    padding: 11px 13px;
}

/* === 列表 === */
QListWidget, QListView {
    background-color: #262624;
    color: #F1F1EF;
    border: 1px solid #3E3E38;
    border-radius: 12px;
    padding: 8px;
    outline: none;
}
QListWidget::item, QListView::item {
    padding: 10px 14px;
    border-radius: 8px;
    margin: 2px 0px;
}
QListWidget::item:hover, QListView::item:hover {
    background-color: #3E3E38;
}
QListWidget::item:selected, QListView::item:selected {
    background-color: #D97757;
    color: #141413;
}

/* === 选项卡 === */
QTabWidget::pane {
    background-color: #262624;
    border: 1px solid #3E3E38;
    border-radius: 12px;
    border-top-left-radius: 0px;
    padding: 16px;
}
QTabBar::tab {
    background-color: transparent;
    color: #B7B5A9;
    border: none;
    border-bottom: 2px solid transparent;
    padding: 10px 20px;
    font-size: 14px;
    font-weight: 500;
}
QTabBar::tab:hover {
    color: #F1F1EF;
    background-color: #3E3E38;
}
QTabBar::tab:selected {
    color: #F1F1EF;
    border-bottom: 2px solid #D97757;
}

/* === 滚动条 === */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    border: none;
    margin: 4px 2px 4px 2px;
}
QScrollBar::handle:vertical {
    background-color: #52514A;
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background-color: #6E6D68;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
    border: none;
    background: none;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
}

QScrollBar:horizontal {
    background: transparent;
    height: 8px;
    border: none;
    margin: 2px 4px 2px 4px;
}
QScrollBar::handle:horizontal {
    background-color: #52514A;
    border-radius: 4px;
    min-width: 30px;
}
QScrollBar::handle:horizontal:hover {
    background-color: #6E6D68;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
    border: none;
    background: none;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: none;
}

/* === 滑块 === */
QSlider::groove:horizontal {
    height: 4px;
    background-color: #3E3E38;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background-color: #D97757;
    width: 18px;
    height: 18px;
    margin: -7px 0;
    border-radius: 9px;
    border: 2px solid #262624;
}
QSlider::handle:horizontal:hover {
    background-color: #E08D6F;
}
QSlider::sub-page:horizontal {
    background-color: #D97757;
    border-radius: 2px;
}

/* === 状态栏 === */
QStatusBar {
    background-color: #1B1B19;
    color: #B7B5A9;
    border-top: 1px solid #3E3E38;
    font-size: 12px;
    padding: 4px 12px;
}

/* === 代码区域 === */
QPlainTextEdit#codeBlock, QTextEdit#codeBlock {
    background-color: #1B1B19;
    color: #F1F1EF;
    border: 1px solid #3E3E38;
    border-radius: 12px;
    padding: 16px;
    font-family: "Geist Mono", "JetBrains Mono", Consolas, monospace;
    font-size: 13px;
    selection-background-color: rgba(217, 119, 87, 0.3);
    selection-color: #F1F1EF;
}

/* === 下拉选择框 === */
QComboBox {
    background-color: #1B1B19;
    color: #F1F1EF;
    border: 1px solid #52514A;
    border-radius: 8px;
    padding: 8px 32px 8px 14px;
    font-size: 14px;
    min-height: 40px;
}
QComboBox:hover {
    border-color: #6E6D68;
}
QComboBox:focus {
    border-color: #D97757;
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 28px;
    border-left: 1px solid #52514A;
    border-top-right-radius: 8px;
    border-bottom-right-radius: 8px;
}
QComboBox::down-arrow {
    width: 10px;
    height: 10px;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #B7B5A9;
}
QComboBox QAbstractItemView {
    background-color: #2C2C2B;
    color: #F1F1EF;
    border: 1px solid #3E3E38;
    border-radius: 12px;
    padding: 8px;
    selection-background-color: #D97757;
    selection-color: #141413;
    outline: none;
}

/* === 工具提示 === */
QToolTip {
    background-color: #2C2C2B;
    color: #F1F1EF;
    border: 1px solid #3E3E38;
    border-radius: 8px;
    padding: 6px 12px;
    font-size: 12px;
}

/* === 菜单 === */
QMenu {
    background-color: #2C2C2B;
    color: #F1F1EF;
    border: 1px solid #3E3E38;
    border-radius: 12px;
    padding: 8px;
}
QMenu::item {
    padding: 8px 16px;
    border-radius: 6px;
}
QMenu::item:hover {
    background-color: #3E3E38;
}
QMenu::item:selected {
    background-color: #D97757;
    color: #141413;
}
QMenu::separator {
    height: 1px;
    background-color: #3E3E38;
    margin: 4px 8px;
}

/* === 进度条 === */
QProgressBar {
    background-color: #3E3E38;
    border: none;
    border-radius: 9999px;
    min-height: 6px;
    max-height: 6px;
    text-align: center;
    color: #F1F1EF;
    font-size: 12px;
}
QProgressBar::chunk {
    background-color: #D97757;
    border-radius: 9999px;
}

/* === 复选框 === */
QCheckBox {
    color: #F1F1EF;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 2px solid #52514A;
    border-radius: 4px;
    background-color: #1B1B19;
}
QCheckBox::indicator:hover {
    border-color: #6E6D68;
}
QCheckBox::indicator:checked {
    background-color: #D97757;
    border-color: #D97757;
}

/* === 分组框 === */
QGroupBox {
    color: #F1F1EF;
    font-size: 14px;
    font-weight: 600;
    border: 1px solid #3E3E38;
    border-radius: 12px;
    margin-top: 16px;
    padding: 20px 16px 16px 16px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 4px 12px;
    color: #B7B5A9;
    font-size: 13px;
}

/* === 分割器 === */
QSplitter::handle:horizontal {
    width: 1px;
    background-color: #3E3E38;
}
QSplitter::handle:vertical {
    height: 1px;
    background-color: #3E3E38;
}
QSplitter::handle:hover {
    background-color: #D97757;
}

/* === 对话框 === */
QDialog {
    background-color: #262624;
}
"""
```

---

## 18. 使用指南

### 18.1 在 PySide6 中应用样式

```python
from PySide6.QtWidgets import QApplication, QMainWindow
import sys

# 方法一: 直接加载 QSS 字符串
app = QApplication(sys.argv)
app.setStyleSheet(CLAUDE_DARK_QSS)

window = QMainWindow()
window.show()
sys.exit(app.exec())

# 方法二: 从文件加载
with open("claude_dark.qss", "r", encoding="utf-8") as f:
    app.setStyleSheet(f.read())

# 方法三: 使用 Token 字典动态生成
qss = QSS_TEMPLATE.format(**CLAUDE_DARK_TOKENS)
app.setStyleSheet(qss)
```

### 18.2 命名约定

| 前缀/后缀 | 用途 | 示例 |
|---|---|---|
| `#primaryButton` | 主操作按钮 | `QPushButton#primaryButton` |
| `#secondaryButton` | 次要操作按钮 | `QPushButton#secondaryButton` |
| `#ghostButton` | 幽灵/透明按钮 | `QPushButton#ghostButton` |
| `#destructiveButton` | 危险操作按钮 | `QPushButton#destructiveButton` |
| `#successButton` | 成功操作按钮 | `QPushButton#successButton` |
| `#iconButton` | 图标按钮 | `QPushButton#iconButton` |
| `#navButton` | 侧边栏导航项 | `QPushButton#navButton` |
| `#sidebar` | 侧边栏容器 | `QFrame#sidebar` |
| `#card` | 卡片面板 | `QFrame#card` |
| `#elevatedCard` | 提升层级卡片 | `QFrame#elevatedCard` |
| `#codeBlock` | 代码显示区域 | `QPlainTextEdit#codeBlock` |
| `#searchInput` | 搜索输入框 | `QLineEdit#searchInput` |
| `#pillTabBar` | 胶囊选项卡 | `QTabBar#pillTabBar` |
| `#segmentControl` | 分段控件 | `QFrame#segmentControl` |
| `#toggleSwitch` | 开关控件 | `QCheckBox#toggleSwitch` |

在 Python 中设置 objectName:

```python
button = QPushButton("Submit")
button.setObjectName("primaryButton")

sidebar = QFrame()
sidebar.setObjectName("sidebar")
```

### 18.3 注意事项

1. **QSS 不支持 CSS 变量** -- 所有色值必须硬编码或通过 Python 模板注入
2. **QSS 不支持 `box-shadow`** -- 如需阴影效果，需使用自定义 QWidget 绘制或使用 QGraphicsDropShadowEffect
3. **QSS 不支持 `line-height`** -- 文本行高由 Qt 内部计算，无法精确控制
4. **QSS 不支持 `text-transform`** -- 大写转换需在 Python 端处理文本内容
5. **QSS 不支持 `letter-spacing`** -- 字间距无法通过 QSS 设置
6. **字体加载** -- Poppins、Newsreader、Lora、Geist Mono 等字体需在系统中安装，或通过 `QFontDatabase.addApplicationFont()` 加载
7. **圆角裁剪** -- QSS 的 `border-radius` 不会裁剪子控件内容，如需精确圆角裁剪，需配合 `QPainter` 或设置 `WA_TranslucentBackground` 属性

---

## 19. 圆角速查表

| 组件类型 | 圆角值 | Claude Token |
|---|---|---|
| 按钮 (Button) | `16px` | `--radius` |
| 卡片 (Card) | `12px` | `--radius-md` |
| 输入框 (Input) | `8px` | `--radius-sm` |
| 列表项 (List Item) | `8px` | `--radius-sm` |
| 选项卡栏 (Tab) | `0px` (底部) / `8px` (胶囊) | -- |
| 滚动条 (Scrollbar) | `4px` | -- |
| 滑块 (Slider Handle) | `9px` (圆形) | -- |
| 进度条 (Progress Bar) | `9999px` (全圆) | `--radius-full` |
| 搜索框 (Search Input) | `9999px` (全圆) | `--radius-full` |
| 分组框 (Group Box) | `12px` | `--radius-md` |
| 菜单 (Menu) | `12px` | `--radius-md` |
| 工具提示 (Tooltip) | `8px` | `--radius-sm` |
| 下拉列表 (ComboBox Popup) | `12px` | `--radius-md` |
| 弹出层 (Popover) | `12px` | `--radius-md` |

---

> 文档版本: 1.0
> 基于 Claude Design System 暗色模式 Token
> 适用框架: PySide6 (Qt 6.x)
> 生成日期: 2026-06-25
