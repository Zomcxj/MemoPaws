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
# 注意：__file__ 指向 memopaws/core/utils.py，需要向上两级获取项目根目录
BUNDLE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

APP_NAME = "MemoPaws"
CONFIG_DIR_NAME = ".memopaws"
ANCHOR_FILE_NAME = ".memopaws.json"
_OLD_APP_NAME = "Snap" "Trans"
_OLD_CONFIG_DIR_NAME = "." + "snap" + "trans"
_OLD_ANCHOR_FILE_NAME = "." + "snap" + "trans" + ".json"

# 锚点文件（单文件，只存数据目录指针）
_ANCHOR_FILE = os.path.join(os.path.expanduser("~"), ANCHOR_FILE_NAME)

# 当前实际路径（启动时初始化默认值，init_paths() 后通过锚点文件修正）
# 注意：此处赋值会被 init_paths() 覆盖，不产生实际目录创建
_DEFAULT_CONFIG_DIR = os.path.join(os.path.expanduser("~"), CONFIG_DIR_NAME)
CONFIG_DIR = _DEFAULT_CONFIG_DIR
CONFIG_FILE = os.path.join(CONFIG_DIR, "setting.json")
HISTORY_FILE = os.path.join(CONFIG_DIR, "history.json")
CLIPBOARD_FILE = os.path.join(CONFIG_DIR, "clipboard.json")
MEMO_DIR = os.path.join(CONFIG_DIR, "memo")
LEGACY_MEMO_FILE = os.path.join(CONFIG_DIR, "memo.json")


def _detect_config_dir() -> str:
    """检测配置目录：读锚点文件，否则用默认目录"""
    anchor_file = _ANCHOR_FILE
    old_anchor_file = os.path.join(os.path.expanduser("~"), _OLD_ANCHOR_FILE_NAME)
    if not os.path.exists(anchor_file) and os.path.exists(old_anchor_file):
        anchor_file = old_anchor_file
    if not os.path.exists(anchor_file):
        return os.path.join(os.path.expanduser("~"), CONFIG_DIR_NAME)
    try:
        import json
        with open(anchor_file, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        data_dir = cfg.get("data_dir", "")
        if data_dir and os.path.isdir(data_dir):
            return os.path.join(data_dir, CONFIG_DIR_NAME)
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), CONFIG_DIR_NAME)


def _update_path_constants(config_dir: str):
    """更新全局路径常量"""
    global CONFIG_DIR, CONFIG_FILE, HISTORY_FILE, CLIPBOARD_FILE, MEMO_DIR, LEGACY_MEMO_FILE
    CONFIG_DIR = config_dir
    CONFIG_FILE = os.path.join(config_dir, "setting.json")
    HISTORY_FILE = os.path.join(config_dir, "history.json")
    CLIPBOARD_FILE = os.path.join(config_dir, "clipboard.json")
    MEMO_DIR = os.path.join(config_dir, "memo")
    LEGACY_MEMO_FILE = os.path.join(config_dir, "memo.json")


def init_paths():
    """启动时初始化路径"""
    config_dir = _detect_config_dir()
    _update_path_constants(config_dir)


def save_anchor(data_dir: str):
    """保存锚点文件"""
    import json
    os.makedirs(os.path.dirname(_ANCHOR_FILE), exist_ok=True)
    with open(_ANCHOR_FILE, "w", encoding="utf-8") as f:
        json.dump({"data_dir": data_dir}, f, ensure_ascii=False, indent=2)


def get_root_path() -> str:
    """返回用户设置的父目录（不含当前应用数据目录）"""
    return os.path.dirname(CONFIG_DIR)


def get_config_dir() -> str:
    """返回当前配置目录"""
    return CONFIG_DIR


def get_memo_dir() -> str:
    """返回当前备忘录目录"""
    return MEMO_DIR


def get_root_path() -> str:
    """返回用户设置的父目录（不含当前应用数据目录）"""
    return os.path.dirname(CONFIG_DIR)


def move_memopaws_folder(src_root: str, dst_root: str, mode: str = "move") -> bool:
    """移动/复制 .memopaws 文件夹

    Args:
        src_root: 源父目录
        dst_root: 目标父目录
        mode: "move" 移动, "merge" 合并, "overwrite" 覆盖

    Returns:
        是否成功
    """
    import shutil
    src_dir = os.path.join(src_root, CONFIG_DIR_NAME)
    dst_dir = os.path.join(dst_root, CONFIG_DIR_NAME)

    if not os.path.isdir(src_dir):
        return False

    os.makedirs(dst_root, exist_ok=True)

    # 保留默认配置文件（setting.json），不移动
    keep_files = {"setting.json"}

    if mode == "overwrite":
        if os.path.exists(dst_dir):
            shutil.rmtree(dst_dir)
        os.makedirs(dst_dir, exist_ok=True)
        for item in os.listdir(src_dir):
            if item in keep_files:
                continue
            s = os.path.join(src_dir, item)
            d = os.path.join(dst_dir, item)
            if os.path.isfile(s):
                shutil.copy2(s, d)
            elif os.path.isdir(s):
                shutil.copytree(s, d)
    elif mode == "merge":
        os.makedirs(dst_dir, exist_ok=True)
        for item in os.listdir(src_dir):
            if item in keep_files:
                continue
            s = os.path.join(src_dir, item)
            d = os.path.join(dst_dir, item)
            if os.path.isfile(s) and not os.path.exists(d):
                shutil.copy2(s, d)
            elif os.path.isdir(s) and not os.path.exists(d):
                shutil.copytree(s, d)
    else:  # move
        os.makedirs(dst_dir, exist_ok=True)
        for item in os.listdir(src_dir):
            if item in keep_files:
                continue
            s = os.path.join(src_dir, item)
            d = os.path.join(dst_dir, item)
            if os.path.isfile(s):
                shutil.move(s, d)
            elif os.path.isdir(s):
                shutil.move(s, d)

    return True


def ensure_config_dir():
    """确保配置目录存在"""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(MEMO_DIR, exist_ok=True)


def migrate_legacy_config():
    """迁移旧配置到当前应用数据目录"""
    import shutil

    # 旧文件映射到新文件
    migrations = [
        (f"{_OLD_APP_NAME}.json", "setting.json"),
        (f"{_OLD_APP_NAME}_keys.json", "keys.json"),
        (f"{_OLD_APP_NAME}_history.json", "history.json"),
        (f"{_OLD_APP_NAME}_clipboard.json", "clipboard.json"),
    ]

    legacy_dirs = [
        os.path.join(os.path.expanduser("~"), f".{_OLD_APP_NAME}"),
        os.path.join(os.path.expanduser("~"), _OLD_CONFIG_DIR_NAME),
    ]
    old_anchor_file = os.path.join(os.path.expanduser("~"), _OLD_ANCHOR_FILE_NAME)
    if os.path.exists(old_anchor_file):
        try:
            import json
            with open(old_anchor_file, "r", encoding="utf-8") as f:
                data_dir = json.load(f).get("data_dir", "")
            if data_dir:
                legacy_dirs.append(os.path.join(data_dir, _OLD_CONFIG_DIR_NAME))
        except Exception:
            pass

    for legacy_dir in legacy_dirs:
        if not os.path.isdir(legacy_dir):
            continue

        for old_name, new_name in migrations:
            old_path = os.path.join(legacy_dir, old_name)
            new_path = os.path.join(CONFIG_DIR, new_name)
            if os.path.exists(old_path) and not os.path.exists(new_path):
                try:
                    shutil.copy2(old_path, new_path)
                except Exception:
                    pass

        # 迁移旧 memo.json 到新 memo/ 目录
        old_memo_file = os.path.join(legacy_dir, "memo.json")
        if os.path.exists(old_memo_file):
            try:
                import json
                with open(old_memo_file, "r", encoding="utf-8") as f:
                    old_data = json.load(f)
                if isinstance(old_data, list):
                    os.makedirs(MEMO_DIR, exist_ok=True)
                    for m in old_data:
                        fname = m.get("_file", f"memo_{m.get('id', 0)}.md")
                        fpath = os.path.join(MEMO_DIR, fname)
                        if not os.path.exists(fpath):
                            title = m.get("title", "memo")
                            content = m.get("content", "")
                            with open(fpath, "w", encoding="utf-8") as f:
                                f.write(f"---\ntitle: {title}\nid: {m.get('id', 0)}\n---\n\n{content}")
            except Exception:
                pass

        # 迁移 memo 子目录中的文件
        legacy_memo_dir = os.path.join(legacy_dir, "memo")
        if os.path.exists(legacy_memo_dir) and os.path.isdir(legacy_memo_dir):
            for fname in os.listdir(legacy_memo_dir):
                old_path = os.path.join(legacy_memo_dir, fname)
                new_path = os.path.join(MEMO_DIR, fname)
                if os.path.isfile(old_path) and not os.path.exists(new_path):
                    try:
                        shutil.copy2(old_path, new_path)
                    except Exception:
                        pass


def migrate_pending_memo():
    """已废弃，保留空函数兼容旧代码"""
    pass


def get_app_root():
    """获取应用程序安装根目录
    
    打包后为 exe 所在目录，开发环境为项目根目录。
    所有运行时数据（日志、缓存等）都应存放在此目录下，
    只有配置文件（setting.json）和历史记录保留在用户目录。
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后：exe 所在目录
        return os.path.dirname(sys.executable)
    else:
        # 开发环境：项目根目录（main.py 所在目录的上一级/同级）
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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
    scaled = pix.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation)
    canvas = QPixmap(size, size)
    canvas.fill(Qt.GlobalColor.transparent)
    p = QPainter(canvas)
    p.drawPixmap((size - scaled.width()) // 2, (size - scaled.height()) // 2, scaled)
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


# ── 公共工具函数 ──

def load_svg_icon(svg_path: str, size: int = 20, color: str = None):
    """加载 SVG 文件并返回指定大小的 QPixmap，支持动态换色和高 DPI"""
    import re
    from PySide6.QtGui import QPixmap, QPainter, QGuiApplication
    from PySide6.QtCore import Qt
    from PySide6.QtSvg import QSvgRenderer
    try:
        with open(svg_path, "r", encoding="utf-8") as f:
            svg_data = f.read()
        if color:
            svg_data = svg_data.replace('currentColor', color)
            svg_data = re.sub(r'fill="#ccc"', f'fill="{color}"', svg_data)
        renderer = QSvgRenderer(svg_data.encode("utf-8"))
        # 根据屏幕 DPR 渲染，保证高分屏清晰
        screen = QGuiApplication.primaryScreen()
        dpr = screen.devicePixelRatio() if screen else 1.0
        physical = int(size * dpr)
        pixmap = QPixmap(physical, physical)
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        return pixmap
    except Exception:
        return QPixmap(size, size)


def normalize_api_url(url: str) -> str:
    """规范化 API URL：确保以 /chat/completions 结尾"""
    url = (url or "").rstrip("/")
    if not url:
        return "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    if url.endswith("/chat/completions"):
        return url
    return url + "/chat/completions"


def test_api_connection(api_key: str, api_url: str, model: str = "glm-4-flash", timeout: float = 10.0) -> dict:
    """测试 API 连接，返回 {success, elapsed_ms, status_code, error}"""
    import time
    import httpx
    url = normalize_api_url(api_url)
    t0 = time.perf_counter()
    try:
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload, headers=headers)
        elapsed = int((time.perf_counter() - t0) * 1000)
        return {"success": resp.status_code == 200, "elapsed_ms": elapsed, "status_code": resp.status_code, "error": ""}
    except httpx.TimeoutException:
        return {"success": False, "elapsed_ms": int((time.perf_counter() - t0) * 1000), "status_code": 0, "error": "timeout"}
    except httpx.ConnectError:
        return {"success": False, "elapsed_ms": int((time.perf_counter() - t0) * 1000), "status_code": 0, "error": "connect_error"}
    except Exception as e:
        return {"success": False, "elapsed_ms": int((time.perf_counter() - t0) * 1000), "status_code": 0, "error": str(e)}
