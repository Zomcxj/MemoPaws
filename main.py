"""MemoPaws - 离线截图 OCR 翻译与编辑工具

入口文件
"""

import os
import sys
import logging

# 禁用 GPU 合成，必须在 QApplication 创建之前设置
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu-compositing"
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

from memopaws.core.utils import get_app_root, get_icon_path

# 配置日志 - 存放在安装根目录（exe 所在目录），不是临时目录
log_path = os.path.join(get_app_root(), "MemoPaws_debug.log")
logging.basicConfig(
    filename=log_path,
    level=logging.DEBUG,
    format="%(asctime)s [%(threadName)s] %(levelname)s: %(message)s",
    force=True,
)
print(f"日志文件: {log_path}", file=sys.stderr)

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from memopaws.core.utils import get_app_root, get_icon_path, init_paths, migrate_legacy_config, migrate_pending_memo
from memopaws.ui.main_window import MainWindow


def main():
    """主函数"""
    # 启动时初始化路径
    init_paths()
    # 迁移旧配置
    migrate_legacy_config()
    # 迁移待处理的存储目录
    migrate_pending_memo()

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseSoftwareOpenGL)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 关闭窗口不退出，靠托盘图标保活
    
    # 设置程序图标
    icon_path = get_icon_path()
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))
    
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
