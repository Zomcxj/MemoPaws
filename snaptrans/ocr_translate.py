"""OCR 和翻译逻辑的 Mixin"""

from PySide6.QtWidgets import QMessageBox
from PySide6.QtCore import QThread

from .ocr import OCRWorker, MODE_LOCAL, MODE_CLOUD
from .translator import SimpleTranslator, TranslateWorker
from .utils import qpixmap_to_numpy


class OCRTranslateMixin:
    """混合到 RecognizePage 的 OCR 和翻译逻辑"""
    
    # ══════════════════════════════════════════════
    #  OCR
    # ══════════════════════════════════════════════
    
    def _run_ocr_local(self):
        if self.ocr_running:
            return
        self.ocr_manager.ocr_mode = MODE_LOCAL
        self.run_ocr_all()
    
    def _run_ocr_ai(self):
        if self.ocr_running:
            return
        self.ocr_manager.ocr_mode = MODE_CLOUD
        self.run_ocr_all()
    
    def run_ocr_async(self, pixmap, callback=None):
        if self.ocr_running:
            return
        self.ocr_running = True
        self._glow_ocr.start()
        arr = qpixmap_to_numpy(pixmap)
        self._cleanup_ocr_thread()
        self.ocr_thread = QThread()
        self.ocr_worker = OCRWorker(self.ocr_manager, arr)
        self.ocr_worker.moveToThread(self.ocr_thread)
        self.ocr_thread.started.connect(self.ocr_worker.run)
        self.ocr_worker.finished.connect(self.ocr_thread.quit)
        self.ocr_worker.finished.connect(self.ocr_worker.deleteLater)
        self.ocr_thread.finished.connect(self.ocr_thread.deleteLater)
        self._ocr_pending_callback = callback
        self.ocr_worker.finished.connect(self._on_ocr_finished)
        self.ocr_thread.start()

    def _cleanup_ocr_thread(self):
        """清理旧的OCR线程"""
        try:
            if hasattr(self, 'ocr_thread') and self.ocr_thread and self.ocr_thread.isRunning():
                self.ocr_thread.quit()
                self.ocr_thread.wait(1000)
        except RuntimeError:
            pass
    
    def run_ocr_all(self):
        if not self.canvas.display_pixmap:
            self._show_message(QMessageBox.Icon.Information, "提示", "请先导入图片")
            return
        pixmap = self.canvas.display_pixmap.copy()
        self._ocr_mode_name = "AI识别" if self.ocr_manager.ocr_mode == MODE_CLOUD else "本地识别"
        
        def on_result(text):
            if text.startswith("[OCR 错误]") and "Tesseract" in text:
                self._show_message(QMessageBox.Icon.Warning, "识别失败",
                    "本地识别需要安装 Tesseract-OCR\n\n"
                    "下载地址：https://github.com/UB-Mannheim/tesseract/wiki")
                return
            self.ocr_text.setPlainText(text)
            self.history_manager.add_record(f"识别({self._ocr_mode_name})", text, ocr_text=text)
            self.history_manager.update_status_list(self.status_list)
        
        self.run_ocr_async(pixmap, on_result)
    
    def _on_ocr_finished(self, text):
        self.ocr_running = False
        self._glow_ocr.stop()
        if not text:
            text = "未识别到文本，或 OCR 引擎未正确配置。"
        cb = getattr(self, '_ocr_pending_callback', None)
        if cb:
            cb(text)
            self._ocr_pending_callback = None
    
    # ══════════════════════════════════════════════
    #  翻译
    # ══════════════════════════════════════════════
    
    def _run_translate_online(self):
        if self.translate_thread is not None:
            try:
                if self.translate_thread.isRunning():
                    return
            except RuntimeError:
                pass
        self.translator.set_mode(SimpleTranslator.MODE_ONLINE)
        self.run_translate()
    
    def _run_translate_ai(self):
        if self.translate_thread is not None:
            try:
                if self.translate_thread.isRunning():
                    return
            except RuntimeError:
                pass
        self.translator.set_mode(SimpleTranslator.MODE_LLM)
        self.run_translate()
    
    def _on_translate_target_changed(self, text: str):
        self.translate_target = text
        if hasattr(self, "translate_source_combo"):
            pair = {"英文": "中文", "中文": "英文"}
            if text in pair:
                self.translate_source_combo.blockSignals(True)
                self.translate_source_combo.setCurrentText(pair[text])
                self.translate_source_combo.blockSignals(False)
    
    def run_translate(self):
        text = self.ocr_text.toPlainText().strip()
        if not text:
            self._show_message(QMessageBox.Icon.Information, "提示", "请先识别文本")
            return
        if self.translate_thread is not None:
            try:
                if self.translate_thread.isRunning():
                    return
            except RuntimeError:
                pass
            self.translate_thread = None
        if self.translate_worker is not None:
            self.translate_worker = None
        
        self._translate_source_text = text
        self._translate_mode = self.translator.mode
        
        self.translate_thread = QThread()
        self.translate_worker = TranslateWorker(
            self.translator, text, self.translate_target,
            getattr(self, "translate_source_combo", None) and self.translate_source_combo.currentText() or None,
        )
        self.translate_worker.moveToThread(self.translate_thread)
        self.translate_thread.started.connect(self.translate_worker.run)
        self.translate_worker.finished.connect(self.translate_thread.quit)
        self.translate_worker.finished.connect(self.translate_worker.deleteLater)
        self.translate_thread.finished.connect(self.translate_thread.deleteLater)
        self.translate_thread.finished.connect(
            lambda t=self.translate_thread:
            setattr(self, 'translate_thread', None)
            if getattr(self, 'translate_thread', None) is t
            else None
        )

        self.translate_worker.finished.connect(self._on_translate_finished)
        self.translate_worker.error.connect(self._on_translate_error)

        self._glow_trans.start()
        self.btn_trans_online.setEnabled(False)
        self.btn_trans_ai.setEnabled(False)
        self.translate_thread.start()

    def cleanup_threads(self):
        """清理所有线程"""
        for attr in ('ocr_thread', 'translate_thread'):
            thread = getattr(self, attr, None)
            try:
                if thread and thread.isRunning():
                    thread.quit()
                    thread.wait(500)
            except RuntimeError:
                pass
    
    def _on_translate_finished(self, translated):
        self._glow_trans.stop()
        self.btn_trans_online.setEnabled(True)
        self.btn_trans_ai.setEnabled(True)
        self.translate_text.setPlainText(translated)
        source = getattr(self, '_translate_source_text', '')
        mode = getattr(self, '_translate_mode', 'unknown')
        mode_name = {"llm": "AI翻译", "online": "在线翻译"}.get(mode, mode)
        record_text = f"[原文] {source[:100]}\n[模式] {mode_name}\n[译文] {translated[:100]}"
        self.history_manager.add_record(
            f"翻译({self.translate_target})",
            record_text,
            source=source,
            target=translated,
            mode_name=mode_name,
        )
        self.history_manager.update_status_list(self.status_list)
    
    def _on_translate_error(self, err_msg):
        self._glow_trans.stop()
        self.btn_trans_online.setEnabled(True)
        self.btn_trans_ai.setEnabled(True)
        self.translate_text.setPlainText(err_msg)
        mode = getattr(self, '_translate_mode', 'unknown')
        mode_name = {"llm": "AI翻译", "online": "在线翻译"}.get(mode, mode)
        self.history_manager.add_record(f"翻译失败({mode_name})", err_msg)
        self.history_manager.update_status_list(self.status_list)
    
    # ══════════════════════════════════════════════
    #  一键出结果
    # ══════════════════════════════════════════════
    
    def _run_one_click(self):
        """一键出结果：AI识别 + AI翻译"""
        if not self.canvas or not self.canvas.display_pixmap:
            self._show_message(QMessageBox.Icon.Information, "提示", "请先导入图片")
            return
        if self.ocr_running:
            return
        self.ocr_running = True
        self._glow_ocr.start()
        self.ocr_manager.ocr_mode = MODE_CLOUD
        self._ocr_mode_name = "一键出结果"
        pixmap = self.canvas.display_pixmap.copy()
        arr = qpixmap_to_numpy(pixmap)
        self.ocr_thread = QThread()
        self.ocr_worker = OCRWorker(self.ocr_manager, arr)
        self.ocr_worker.moveToThread(self.ocr_thread)
        self.ocr_thread.started.connect(self.ocr_worker.run)
        self.ocr_worker.finished.connect(self.ocr_thread.quit)
        self.ocr_worker.finished.connect(self.ocr_worker.deleteLater)
        self.ocr_thread.finished.connect(self.ocr_thread.deleteLater)
        self._ocr_pending_callback = self._auto_translate_after_ocr
        self.ocr_worker.finished.connect(self._on_ocr_finished)
        self.ocr_thread.start()
    
    def _auto_translate_after_ocr(self, text=""):
        """OCR完成后自动AI翻译"""
        if text:
            self.ocr_text.setPlainText(text)
        t = self.ocr_text.toPlainText().strip()
        if not t:
            return
        self.translator.set_mode(SimpleTranslator.MODE_LLM)
        self.run_translate()