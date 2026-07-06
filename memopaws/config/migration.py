"""设置页存储目录迁移逻辑。"""

import os
import shutil

from PySide6.QtWidgets import QMessageBox

from ..core.utils import get_config_dir, init_paths, move_memopaws_folder, save_anchor


def ask_existing_data_mode(parent, dst_memopaws: str, lang: str) -> str | None:
    """目标 .memopaws 已存在时询问处理方式。"""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle("Target directory has data" if lang == "en" else "目标目录已存在数据")
    box.setText(
        f"{dst_memopaws} already exists\n\nHow should it be handled?"
        if lang == "en"
        else f"{dst_memopaws} 已存在\n\n如何处理？"
    )
    merge_btn = box.addButton("Merge" if lang == "en" else "合并", QMessageBox.ButtonRole.AcceptRole)
    overwrite_btn = box.addButton("Overwrite" if lang == "en" else "覆盖", QMessageBox.ButtonRole.DestructiveRole)
    cancel_btn = box.addButton("Cancel" if lang == "en" else "取消", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel_btn)
    box.exec()

    clicked = box.clickedButton()
    if clicked == cancel_btn:
        return None
    if clicked == merge_btn:
        return "merge"
    if clicked == overwrite_btn:
        return "overwrite"
    return "overwrite"


def migrate_storage_root(current_root: str, new_root: str, mode: str, logger=None) -> bool:
    """迁移 .memopaws，刷新锚点，并删除旧默认目录。"""
    old_config_dir = get_config_dir()
    if not move_memopaws_folder(current_root, new_root, mode=mode):
        return False
    save_anchor(new_root)
    init_paths()

    new_config_dir = get_config_dir()
    if os.path.abspath(old_config_dir) != os.path.abspath(new_config_dir) and os.path.isdir(old_config_dir):
        try:
            shutil.rmtree(old_config_dir)
        except Exception as exc:
            if logger:
                logger.warning("删除旧配置目录失败: %s", exc)
    return True


def ask_restart(parent, lang: str) -> bool:
    """询问是否立即重启。"""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle("Restart required" if lang == "en" else "重启生效")
    box.setText(
        "Storage directory changed. Restart is required.\n\nRestart now?"
        if lang == "en"
        else "存储目录已修改，需要重启生效。\n\n是否立即重启？"
    )
    restart_btn = box.addButton("Restart Now" if lang == "en" else "立即重启", QMessageBox.ButtonRole.AcceptRole)
    box.addButton("Later" if lang == "en" else "稍后重启", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(restart_btn)
    box.exec()
    return box.clickedButton() == restart_btn
