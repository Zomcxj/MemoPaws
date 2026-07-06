"""全局搜索对话框。"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout


class GlobalSearchDialog(QDialog):
    def __init__(self, *, search_provider, open_result, parent=None):
        super().__init__(parent)
        self._search_provider = search_provider
        self._open_result_cb = open_result
        self.setWindowTitle("全局搜索")
        self.resize(640, 420)

        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addWidget(QLabel("🔍"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索备忘录、剪切板、历史记录...")
        self.search_input.textChanged.connect(self.refresh_results)
        header.addWidget(self.search_input, 1)
        layout.addLayout(header)

        scope_row = QHBoxLayout()
        self.chk_memo = QCheckBox("备忘录")
        self.chk_clipboard = QCheckBox("剪切板")
        self.chk_history = QCheckBox("操作历史")
        for chk in (self.chk_memo, self.chk_clipboard, self.chk_history):
            chk.setChecked(True)
            chk.stateChanged.connect(self.refresh_results)
            scope_row.addWidget(chk)
        scope_row.addStretch()
        layout.addLayout(scope_row)

        self.result_label = QLabel("结果 (0 条)")
        layout.addWidget(self.result_label)

        self.result_list = QListWidget()
        self.result_list.itemActivated.connect(self._open_selected)
        self.result_list.itemDoubleClicked.connect(self._open_selected)
        layout.addWidget(self.result_list, 1)

    def refresh_results(self):
        query = self.search_input.text().strip()
        results = self._search_provider(query, self.selected_scopes())
        self.result_list.clear()
        for result in results:
            item = QListWidgetItem(f"[{result['source']}] {result['title']}\n{result['snippet']}")
            item.setData(Qt.ItemDataRole.UserRole, result)
            self.result_list.addItem(item)
        self.result_label.setText(f"结果 ({len(results)} 条)")

    def selected_scopes(self):
        scopes = []
        if self.chk_memo.isChecked():
            scopes.append("memo")
        if self.chk_clipboard.isChecked():
            scopes.append("clipboard")
        if self.chk_history.isChecked():
            scopes.append("history")
        return scopes

    def _open_selected(self, item):
        result = item.data(Qt.ItemDataRole.UserRole)
        if result:
            self._open_result_cb(result)
            self.accept()
