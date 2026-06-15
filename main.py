"""SnapTrans - 离线截图 OCR 翻译与编辑工具

入口文件
"""

import os
import sys
import logging

from snaptrans.utils import get_app_root, get_icon_path

# 配置日志 - 存放在安装根目录（exe 所在目录），不是临时目录
log_path = os.path.join(get_app_root(), "SnapTrans_debug.log")
logging.basicConfig(
    filename=log_path,
    level=logging.DEBUG,
    format="%(asctime)s [%(threadName)s] %(levelname)s: %(message)s",
    force=True,
)
print(f"日志文件: {log_path}", file=sys.stderr)

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QIcon

from snaptrans.main_window import MainWindow


def main():
    """主函数"""
    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei UI", 10))
    
    # 设置程序图标
    icon_path = get_icon_path()
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))
    
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
