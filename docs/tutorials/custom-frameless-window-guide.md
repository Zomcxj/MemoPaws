# PySide6 无边框窗口 + 系统原生动画教程

> 基于 SnapTrans 项目实战总结，踩过的坑都在这里。

---

## 核心问题

PySide6 的 `FramelessWindowHint` 会**移除所有系统原生行为**：
- ❌ 系统缩放（边缘拖动）
- ❌ 系统动画（最大化/最小化/还原）
- ❌ 系统光标（缩放箭头）
- ❌ 系统快捷键（Win+↑/↓/←/→）

手动实现这些行为极其复杂且容易卡死。**正确做法是保留系统行为，只隐藏标题栏外观。**

---

## 正确方案：WM_NCCALCSIZE + WS_THICKFRAME

### 原理

| Windows 概念 | 作用 |
|---|---|
| `WM_NCCALCSIZE` | 拦截后返回 0，让客户区填满整个窗口（隐藏标题栏） |
| `WS_THICKFRAME` | 告诉系统"这个窗口可以缩放"，保留所有系统行为 |
| `WM_NCHITTEST` | 告诉系统鼠标在哪个区域（边框/角落/客户区），系统自动显示对应光标 |

**关键：不用 `FramelessWindowHint`，用 `nativeEvent` 拦截 Windows 消息。**

### 完整实现

```python
"""无边框窗口 Mixin - 通过 WM_NCCALCSIZE 隐藏标题栏但保留系统缩放/动画"""

import os
import ctypes
import ctypes.wintypes
from PySide6.QtWidgets import QMenu
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QPainterPath
from PySide6.QtSvg import QSvgRenderer

# Windows API 常量
WM_NCCALCSIZE = 0x0083
WM_NCHITTEST = 0x0084
HTCLIENT = 1
HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17
GWL_STYLE = -16
WS_THICKFRAME = 0x00040000


class FramelessWindowMixin:
    """无边框窗口 Mixin：通过 WM_NCCALCSIZE 隐藏标题栏，保留系统缩放/动画。"""

    def _setup_frameless(self):
        """在 __init__ 中调用，添加 WS_THICKFRAME 让系统处理缩放"""
        hwnd = int(self.winId())
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style | WS_THICKFRAME)

    def nativeEvent(self, event_type, message):
        """拦截 Windows 原生消息，实现无边框 + 系统缩放"""
        if event_type == b"windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == WM_NCCALCSIZE and msg.wParam:
                # 去掉标题栏区域，让客户区填满整个窗口
                return True, 0
            elif msg.message == WM_NCHITTEST:
                # 让系统处理边缘缩放和光标
                result = self._hit_test(msg.lParam)
                if result is not None:
                    return True, result
        return super().nativeEvent(event_type, message)

    def _hit_test(self, lParam):
        """检测鼠标位置，返回 HT 值让系统处理缩放/光标"""
        x = ctypes.c_short(lParam & 0xFFFF).value
        y = ctypes.c_short((lParam >> 16) & 0xFFFF).value
        geo = self.frameGeometry()
        margin = 6

        # 四角
        if x <= geo.left() + margin and y <= geo.top() + margin:
            return HTTOPLEFT
        if x >= geo.right() - margin and y <= geo.top() + margin:
            return HTTOPRIGHT
        if x <= geo.left() + margin and y >= geo.bottom() - margin:
            return HTBOTTOMLEFT
        if x >= geo.right() - margin and y >= geo.bottom() - margin:
            return HTBOTTOMRIGHT
        # 四边
        if x <= geo.left() + margin:
            return HTLEFT
        if x >= geo.right() - margin:
            return HTRIGHT
        if y <= geo.top() + margin:
            return HTTOP
        if y >= geo.bottom() - margin:
            return HTBOTTOM
        # 客户区（必须显式返回，否则 Qt 接管显示默认光标）
        return HTCLIENT

    def paintEvent(self, event):
        """画带圆角的窗口背景"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # 此处用你的主题颜色
        bg = QColor("#1A1717")  # 替换为主题 bg_main
        path = QPainterPath()
        rect = QRectF(0, 0, self.width(), self.height())
        path.addRoundedRect(rect, 14, 14)  # 14px 圆角
        painter.fillPath(path, bg)
        painter.end()
```

### 使用方式

```python
class MainWindow(FramelessWindowMixin, QMainWindow):
    def __init__(self):
        super().__init__()
        # ⚠️ 关键：不用 FramelessWindowHint！
        self.setWindowFlags(Qt.WindowType.Window)
        # 开启透明背景（让圆角生效）
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        
        # 构建 UI...
        self.init_ui()
        
        # ⚠️ 关键：在 show 之前调用，添加 WS_THICKFRAME
        self._setup_frameless()
```

---

## 三大关键点

### 1. 不用 FramelessWindowHint

```python
# ❌ 错误：移除所有系统行为
self.setWindowFlags(Qt.WindowType.FramelessWindowHint)

# ✅ 正确：只用 Window，通过 nativeEvent 隐藏标题栏
self.setWindowFlags(Qt.WindowType.Window)
```

### 2. _hit_test 必须返回 HTCLIENT

```python
# ❌ 错误：返回 None 让 Qt 接管，Qt 显示默认鼠标光标
if not near_edge:
    return None

# ✅ 正确：返回 HTCLIENT 让 Windows 处理边缘光标
if not near_edge:
    return HTCLIENT
```

### 3. WA_TranslucentBackground 会干扰系统动画

```python
# WA_TranslucentBackground 让圆角生效，但可能干扰最大化动画
# 如果动画不工作，尝试去掉此属性
self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
```

---

## 最大化/还原

系统原生动画由 `WS_THICKFRAME` 自动提供，直接用 Qt 方法：

```python
# 最大化（系统自动播放动画）
self.showMaximized()

# 还原（系统自动播放动画）
self.showNormal()

# 最小化
self.showMinimized()

# 切换
def _toggle_maximize(self):
    if self.isMaximized():
        self.showNormal()
    else:
        self.showMaximized()
```

**最大/最小化图标切换**：监听 `changeEvent` 更新图标

```python
def changeEvent(self, event):
    super().changeEvent(event)
    self._update_maximize_icon()

def _update_maximize_icon(self):
    icon_name = "restore.svg" if self.isMaximized() else "maximize.svg"
    self.maximize_btn.setIcon(load_svg_icon(icon_name))
```

---

## 标题栏拖动

标题栏不需要特殊处理，系统自动支持。但如果你想让空白区域也能拖动：

```python
title_bar.mousePressEvent = lambda e: setattr(self, '_drag_pos', 
    e.globalPosition().toPoint() - self.frameGeometry().topLeft())
title_bar.mouseMoveEvent = lambda e: self.move(
    e.globalPosition().toPoint() - self._drag_pos) if getattr(self, '_drag_pos', None) else None
title_bar.mouseReleaseEvent = lambda e: setattr(self, '_drag_pos', None)
```

---

## 最小化动画（可选增强）

如果系统默认最小化动画不够明显，可以临时加 `WS_CAPTION` 触发系统动画：

```python
def _minimize_with_animation(self):
    hwnd = int(self.winId())
    style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style | WS_CAPTION)
    ctypes.windll.user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
    QTimer.singleShot(500, lambda: ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style))
```

**⚠️ 注意：不要对最大化/还原用这个方法，会导致卡死。**

---

## 常见踩坑

| 问题 | 原因 | 解决 |
|---|---|---|
| 边缘光标是默认鼠标 | `_hit_test` 返回 `None` | 改为返回 `HTCLIENT` |
| 最大化后卡死 | `WS_CAPTION` 去掉时系统重新计算布局 | 不要用 `WS_CAPTION`，用原生 `showMaximized()` |
| 最小化后无法恢复 | `WS_CAPTION` 动画导致窗口状态混乱 | 最小化不要用 `WS_CAPTION` |
| 圆角消失了 | 去掉了 `WA_TranslucentBackground` | 保留此属性，用 `paintEvent` 画圆角 |
| 拖动缩放不工作 | 用了 `FramelessWindowHint` | 改为 `nativeEvent + WS_THICKFRAME` |
| 按钮点击无效 | `_hit_test` 坐标计算错误 | 用 `frameGeometry().left()/top()/right()/bottom()` |
| 缩放时回弹 | 手动 `_perform_resize` 逻辑错误 | 让系统处理，不要手动实现缩放 |

---

## 项目结构参考

```
snaptrans/
  frameless_window.py   ← 无边框 Mixin（WM_NCCALCSIZE + WS_THICKFRAME）
  main_window.py         ← 主窗口（调用 _setup_frameless）
  themes.py              ← 主题系统
```

---

## 一句话总结

**不要用 `FramelessWindowHint`，用 `WM_NCCALCSIZE + WS_THICKFRAME` 隐藏标题栏，保留系统所有原生行为。**
