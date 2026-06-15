"""工具函数模块"""

import os
import sys
import ctypes
import logging
import numpy as np
import cv2
from PIL import Image
from PySide6.QtGui import QPixmap, QImage, QPainter, QPainterPath
from PySide6.QtCore import Qt, QSize

logger = logging.getLogger(__name__)

# PyInstaller --onefile 运行时资源目录
# 注意：__file__ 指向 snaptrans/utils.py，需要向上一级获取项目根目录
BUNDLE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

APP_NAME = "SnapTrans"

# 所有 JSON 配置文件统一放在 ~/.SnapTrans/ 目录下
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".SnapTrans")
CONFIG_FILE = os.path.join(CONFIG_DIR, "SnapTrans.json")
HISTORY_FILE = os.path.join(CONFIG_DIR, "SnapTrans_history.json")
CLIPBOARD_FILE = os.path.join(CONFIG_DIR, "SnapTrans_clipboard.json")
MEMO_FILE = os.path.join(CONFIG_DIR, "SnapTrans_memo.json")


def ensure_config_dir():
    """确保配置目录存在"""
    if not os.path.isdir(CONFIG_DIR):
        os.makedirs(CONFIG_DIR, exist_ok=True)


def get_app_root():
    """获取应用程序安装根目录
    
    打包后为 exe 所在目录，开发环境为项目根目录。
    所有运行时数据（日志、缓存等）都应存放在此目录下，
    只有配置文件（.SnapTrans.json）和历史记录保留在用户目录。
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后：exe 所在目录
        return os.path.dirname(sys.executable)
    else:
        # 开发环境：项目根目录（main.py 所在目录的上一级/同级）
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def set_title_bar_color(hwnd, dark: bool):
    """设置 Windows 标题栏颜色
    
    Args:
        hwnd: 窗口句柄
        dark: True 为暗色，False 为亮色
    """
    try:
        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20 (Windows 10 1809+)
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        value = ctypes.c_int(1 if dark else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(value), ctypes.sizeof(value)
        )
        
        # 设置标题栏颜色 (Windows 11)
        # DWMWA_CAPTION_COLOR = 35
        DWMWA_CAPTION_COLOR = 35
        if dark:
            # 暗色主题：深色标题栏
            color = ctypes.c_int(0x00111111)  # BGR 格式的 #111111
        else:
            # 亮色主题：浅灰色标题栏
            color = ctypes.c_int(0x00F0E0D5)  # BGR 格式的 #D5E0F0
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_CAPTION_COLOR,
            ctypes.byref(color), ctypes.sizeof(color)
        )
    except Exception as e:
        logger.debug("设置标题栏颜色失败: %s", e)


def generate_ico_from_png(png_path, ico_path):
    """从 PNG 生成 ICO（含多尺寸）"""
    try:
        img = Image.open(png_path).convert("RGBA")
        base = img.resize((256, 256), Image.LANCZOS)
        sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        base.save(ico_path, format='ICO', sizes=sizes)
        return True
    except Exception as e:
        logger.warning("ICO 生成失败: %s", e)
        return False


def get_icon_path():
    """获取图标路径，自动从 PNG 生成 ICO（如果需要）"""
    icon_ico = os.path.join(BUNDLE_DIR, "assets", "app.ico")
    icon_png = os.path.join(BUNDLE_DIR, "assets", "app.png")

    if not os.path.isfile(icon_ico) and os.path.isfile(icon_png):
        generate_ico_from_png(icon_png, icon_ico)

    return icon_ico if os.path.isfile(icon_ico) else None


def get_icon_pixmap(size: int = 20):
    """加载 PNG app 图标，缩放到 size×size"""
    icon_png = os.path.join(BUNDLE_DIR, "assets", "app.png")
    if not os.path.isfile(icon_png):
        return QPixmap(size, size)
    pix = QPixmap(icon_png)
    if pix.isNull():
        return QPixmap(size, size)
    # 裁剪掉 cream 背景（只保留 bear + bunny 角色），左对齐到 size×size 透明画布
    src_w, src_h = pix.width(), pix.height()
    cropped = pix.copy(src_w // 6, src_h // 6,
                       src_w * 2 // 3, src_h * 2 // 3)
    scaled = cropped.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
    canvas = QPixmap(size, size)
    canvas.fill(Qt.GlobalColor.transparent)
    p = QPainter(canvas)
    p.drawPixmap(0, (size - scaled.height()) // 2, scaled)
    p.end()
    return canvas


def make_rounded_pixmap(path, size, radius=12):
    """加载图片并裁剪为圆角，返回 QPixmap"""
    pix = QPixmap(path)
    if pix.isNull():
        return QPixmap(size, size)
    pix = pix.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                     Qt.TransformationMode.SmoothTransformation)
    rounded = QPixmap(size, size)
    rounded.fill(Qt.GlobalColor.transparent)
    painter = QPainter(rounded)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, size, size, radius, radius)
    painter.setClipPath(path)
    x = (size - pix.width()) // 2
    y = (size - pix.height()) // 2
    painter.drawPixmap(x, y, pix)
    painter.end()
    return rounded


def qimage_to_numpy(qimage: QImage):
    """QImage 转 numpy 数组"""
    qimage = qimage.convertToFormat(QImage.Format.Format_RGBA8888)
    width = qimage.width()
    height = qimage.height()
    ptr = qimage.bits()
    arr = np.array(ptr).reshape(height, width, 4)
    return arr.copy()


def qpixmap_to_numpy(pixmap: QPixmap):
    """QPixmap 转 numpy 数组 (BGR)"""
    image = pixmap.toImage()
    arr = qimage_to_numpy(image)
    return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)


def numpy_to_qpixmap(arr):
    """numpy 数组转 QPixmap"""
    if len(arr.shape) == 2:
        h, w = arr.shape
        bytes_per_line = w
        qimg = QImage(arr.data, w, h, bytes_per_line, QImage.Format.Format_Grayscale8)
        return QPixmap.fromImage(qimg.copy())
    else:
        rgb = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        return QPixmap.fromImage(qimg.copy())


def detect_lang(text):
    """简单语言检测：检测文本是中文还是英文"""
    if not text:
        return "en"
    cjk = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    total = len(text.strip())
    if total == 0:
        return "en"
    if cjk / total > 0.1:
        return "zh"
    return "en"
