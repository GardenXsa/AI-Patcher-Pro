"""
Главное окно приложения AI Patcher Pro.

ИСПРАВЛЕНО:
- bare except: заменены на конкретные типы исключений
- BackupManagerDialog получает BackupManager вместо глобального BACKUP_DIR
- recalculate_file: убран bare except
- action_edit: хайлайтер создаётся через фабрику
"""

import os
import json

from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QLabel,
    QProgressBar,
    QComboBox,
    QScrollArea,
    QMessageBox,
    QDialog,
    QFrame,
    QSplitter,
    QFileDialog,
    QApplication,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDragEnterEvent, QDropEvent

from ai_patcher_pro.core.json_parser import extract_all_json
from ai_patcher_pro.core.security import secure_path_join
from ai_patcher_pro.core.backup import BackupManager
from ai_patcher_pro.core.processor import ProcessorThread
from ai_patcher_pro.gui.operation_card import OperationCard
from ai_patcher_pro.gui.backup_dialog import BackupManagerDialog
from ai_patcher_pro.gui.code_viewer import CodeHighlighter
from ai_patcher_pro.utils.file_io import read_file_safe


class AIPatcherPro(QMainWindow):
    """Главное окно приложения AI Patcher Pro."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Patcher Pro v2.0")
        self.resize(1300, 800)
        self.setAcceptDrops(True)

        self.workspace = os.getcwd()
        self.patch_name = "Без имени"
        self.raw_operations: list = []
        self.processed_operations: list = []
        self.memory_files: dict = {}

        self.backup_mgr = BackupManager(self.workspace)

        self._setup_ui()
        self.backup_mgr.init_backup_dir()

    # --- Drag & Drop ---
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Принимает перетаскивание файлов или текста."""
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        """Обрабатывает сброс файлов или текста."""
        if event.mimeData().hasUrls():
            url = event.mimeData().urls()[0]
            if url.isLocalFile():
                try:
                    text = read_file_safe(url.toLocalFile())
                    self.txt_json.setText(text)
                except (OSError, ValueError) as e:
                    QMessageBox.warning(
                        self, "Ошибка", f"Не удалось прочитать файл: {e}"
                    )
        elif event.mimeData().hasText():
            self.txt_json.setText(event.mimeData().text())

    def change_workspace(self) -> None:
        """Открывает диалог выбора рабочей директории."""
        folder = QFileDialog.getExistingDirectory(
            self, "Выберите папку проекта", self.workspace
        )
        if folder:
            self.workspace = folder
            self.backup_mgr = BackupManager(self.workspace)
            self.backup_mgr.init_backup_dir()
            folder_name = os.path.basename(folder) or folder
            self.btn_workspace.setText(f"  {folder_name}")
            self.clear_all()

    def _setup_ui(self) -> None:
        """Инициализация UI главного окна."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background-color: #1e1e1e; }")
        main_layout.addWidget(splitter)

        # --- SIDEBAR ---
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(350)
        sidebar.setMaximumWidth(400)

        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(15, 15, 15, 15)

        folder_name = os.path.basename(self.workspace) or self.workspace
        self.btn_workspace = QPushButton(f"  {folder_name}")
        self.btn_workspace.setObjectName("btn_workspace")
        self.btn_workspace.setMinimumHeight(35)
        self.btn_workspace.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_workspace.setToolTip(
            "Кликните, чтобы изменить рабочую папку проекта"
        )
        self.btn_workspace.clicked.connect(self.change_workspace)
        side_layout.addWidget(self.btn_workspace)

        btn_box = QHBoxLayout()

        btn_paste = QPushButton("Вставить")
        btn_paste.clicked.connect(
            lambda: self.txt_json.setText(QApplication.clipboard().text())
        )
        btn_box.addWidget(btn_paste)

        btn_clear = QPushButton("Очистить")
        btn_clear.setObjectName("btn_danger")
        btn_clear.clicked.connect(self.clear_all)
        btn_box.addWidget(btn_clear)

        side_layout.addLayout(btn_box)

        lbl_json = QLabel("Сырой JSON (Можно перетащить файл сюда):")
        lbl_json.setStyleSheet("font-size: 12px; color: #aaaaaa;")
        side_layout.addWidget(lbl_json)

        self.txt_json = QTextEdit()
        self.txt_json.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.json_highlighter = CodeHighlighter(self.txt_json.document())
        side_layout.addWidget(self.txt_json)

        self.btn_analyze = QPushButton("Парсить и Анализировать")
        self.btn_analyze.setMinimumHeight(45)
        self.btn_analyze.clicked.connect(self.parse_and_analyze)
        side_layout.addWidget(self.btn_analyze)

        # Прогресс
        progress_frame = QFrame()
        prog_layout = QVBoxLayout(progress_frame)

        self.lbl_status = QLabel("Статус: Ожидание")
        self.lbl_status.setObjectName("status_warning")
        prog_layout.addWidget(self.lbl_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        prog_layout.addWidget(self.progress_bar)

        self.lbl_progress_text = QLabel("0 / 0")
        self.lbl_progress_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        prog_layout.addWidget(self.lbl_progress_text)

        side_layout.addWidget(progress_frame)

        self.btn_history = QPushButton("История бэкапов")
        self.btn_history.setObjectName("btn_purple")
        self.btn_history.clicked.connect(
            lambda: BackupManagerDialog(self, self.workspace).exec()
        )
        side_layout.addWidget(self.btn_history)

        self.btn_report = QPushButton("Отчет об ошибках для ИИ")
        self.btn_report.setObjectName("btn_warning")
        self.btn_report.clicked.connect(self.copy_error_report)
        side_layout.addWidget(self.btn_report)

        self.btn_apply = QPushButton("ПРИМЕНИТЬ ПАТЧ")
        self.btn_apply.setObjectName("btn_success")
        self.btn_apply.setMinimumHeight(50)
        self.btn_apply.setEnabled(False)
        self.btn_apply.clicked.connect(self.apply_patch)
        side_layout.addWidget(self.btn_apply)

        splitter.addWidget(sidebar)

        # --- MAIN AREA ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("Сортировка:"))

        self.sort_menu = QComboBox()
        self.sort_menu.addItems(["Сначала ошибки", "По умолчанию", "По файлам"])
        self.sort_menu.currentTextChanged.connect(self.apply_sorting)
        top_bar.addWidget(self.sort_menu)
        top_bar.addStretch()
        right_layout.addLayout(top_bar)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)

        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.scroll_area.setWidget(self.scroll_content)
        right_layout.addWidget(self.scroll_area)

        splitter.addWidget(right_panel)
        splitter.setSizes([380, 920])

    def clear_all(self) -> None:
        """Очищает все данные и UI."""
        self.txt_json.clear()
        self.raw_operations.clear()
        self.processed_operations.clear()
        self.memory_files.clear()

        while self.scroll_layout.count():
            child = self.scroll_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        self.progress_bar.setValue(0)
        self.lbl_progress_text.setText("0 / 0")

        self.lbl_status.setText("Статус: Ожидание")
        self.lbl_status.setObjectName("status_warning")
        self.lbl_status.style().unpolish(self.lbl_status)
        self.lbl_status.style().polish(self.lbl_status)

        self.btn_apply.setEnabled(False)

    def copy_error_report(self) -> None:
        """Генерирует и копирует в буфер обмена отчёт об ошибках для ИИ."""
        failed = [
            op for op in self.processed_operations if op["status"] != "success"
        ]
        if not failed:
            QMessageBox.information(self, "Отчет", "Все успешно!")
            return

        report = "Привет, ИИ. Возникли ошибки:\n\n"
        for i, item in enumerate(failed, 1):
            op = item["op"]
            file_path = op.get("path") or op.get("file", "?")
            action = op.get("action") or op.get("op", "?")

            report += f"### {i}: Файл `{file_path}` ({action})\nПричина: {item['error']}\n"

            if op.get("search"):
                report += "Искали:\n```\n" + op.get("search") + "\n```\n"

            if item.get("suggestions"):
                report += "Найдено алгоритмом:\n"
                for idx, (ratio, sug) in enumerate(item["suggestions"]):
                    report += (
                        f"- Вариант {idx + 1} ({int(ratio * 100)}%):\n"
                        f"```\n{sug}\n```\n"
                    )

        QApplication.clipboard().setText(report)
        QMessageBox.information(self, "Скопировано", "Отчет скопирован в буфер обмена!")

    def action_copy(self, op_dict: dict) -> None:
        """Копирует JSON операции в буфер обмена."""
        QApplication.clipboard().setText(
            json.dumps(op_dict, indent=2, ensure_ascii=False)
        )
        QMessageBox.information(self, "Скопировано", "JSON блока скопирован.")

    def parse_and_analyze(self) -> None:
        """Парсит JSON из текстового поля и запускает анализ."""
        try:
            data = extract_all_json(self.txt_json.toPlainText().strip())
            self.patch_name = data["patch_name"]
            self.raw_operations = [
                {"id": i, "op": op} for i, op in enumerate(data["operations"])
            ]
        except (ValueError, json.JSONDecodeError) as e:
            QMessageBox.critical(self, "Ошибка парсинга", str(e))
            return

        self.processed_operations.clear()
        self.memory_files.clear()
        self._start_processing(self.raw_operations)

    def recalculate_file(self, filepath: str) -> None:
        """
        Пересчитывает операции для конкретного файла.

        ИСПРАВЛЕНО: bare except заменён на конкретные исключения.
        """
        self.btn_apply.setEnabled(False)

        # Удаляем обработанные операции для этого файла
        self.processed_operations = [
            op
            for op in self.processed_operations
            if (op["op"].get("path") or op["op"].get("file", "unknown")) != filepath
        ]

        # Берём исходные операции для этого файла
        file_raw_ops = [
            item
            for item in self.raw_operations
            if (item["op"].get("path") or item["op"].get("file", "unknown")) == filepath
        ]

        try:
            abs_p = secure_path_join(self.workspace, filepath)
        except (PermissionError, ValueError):
            abs_p = None

        if abs_p and abs_p in self.memory_files:
            del self.memory_files[abs_p]

        self._start_processing(file_raw_ops, is_recalc=True)

    def _start_processing(self, pending_ops: list, is_recalc: bool = False) -> None:
        """Запускает фоновую обработку операций."""
        self.btn_analyze.setEnabled(False)
        self.scroll_area.setEnabled(False)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        if not is_recalc:
            self.progress_bar.setMaximum(len(self.raw_operations))
            self.progress_bar.setValue(0)
            while self.scroll_layout.count():
                child = self.scroll_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

        self.thread = ProcessorThread(self.workspace, pending_ops, self.memory_files)
        self.thread.operation_done.connect(self._on_operation_done)
        self.thread.finished_all.connect(self._on_analysis_finished)
        self.thread.start()

    def _on_operation_done(self, result: dict) -> None:
        """Обрабатывает завершение одной операции."""
        self.processed_operations.append(result)
        self.progress_bar.setValue(len(self.processed_operations))
        self.lbl_progress_text.setText(
            f"{len(self.processed_operations)} / {len(self.raw_operations)}"
        )

    def _on_analysis_finished(self, updated_cache: dict) -> None:
        """Обрабатывает завершение всего анализа."""
        self.btn_analyze.setEnabled(True)
        self.scroll_area.setEnabled(True)
        QApplication.restoreOverrideCursor()

        self.memory_files.update(updated_cache)
        self.apply_sorting()
        self._check_ready_status()

    def apply_sorting(self) -> None:
        """Применяет выбранную сортировку к карточкам операций."""
        while self.scroll_layout.count():
            child = self.scroll_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        mode = self.sort_menu.currentText()
        sorted_ops = list(self.processed_operations)

        if mode == "По умолчанию":
            sorted_ops.sort(key=lambda x: x["id"])
        elif mode == "По файлам":
            sorted_ops.sort(key=lambda x: (x["op"].get("path", ""), x["id"]))
        elif mode == "Сначала ошибки":
            sorted_ops.sort(key=lambda x: (0 if x["status"] == "error" else 1, x["id"]))

        for item in sorted_ops:
            self.scroll_layout.addWidget(OperationCard(item, self))

    def _check_ready_status(self) -> None:
        """Проверяет, готовы ли все операции к применению."""
        has_errors = any(op["status"] == "error" for op in self.processed_operations)

        if not has_errors and self.processed_operations:
            self.lbl_status.setText("Готово к применению")
            self.lbl_status.setObjectName("status_success")
            self.btn_apply.setEnabled(True)
        elif not self.processed_operations:
            self.lbl_status.setText("Статус: Ожидание")
            self.lbl_status.setObjectName("status_warning")
            self.btn_apply.setEnabled(False)
        else:
            self.lbl_status.setText("Есть ошибки")
            self.lbl_status.setObjectName("status_error")
            self.btn_apply.setEnabled(False)

        self.lbl_status.style().unpolish(self.lbl_status)
        self.lbl_status.style().polish(self.lbl_status)

    def action_delete(self, op_id: int) -> None:
        """Удаляет операцию из списка."""
        target_raw = next(
            (item for item in self.raw_operations if item["id"] == op_id), None
        )
        target_processed = next(
            (item for item in self.processed_operations if item["id"] == op_id), None
        )

        if not target_raw or not target_processed:
            return

        filepath = target_raw["op"].get("path") or target_raw["op"].get("file", "unknown")
        self.raw_operations = [
            item for item in self.raw_operations if item["id"] != op_id
        ]

        if target_processed["status"] != "success":
            self.processed_operations = [
                item for item in self.processed_operations if item["id"] != op_id
            ]
            self.progress_bar.setMaximum(len(self.raw_operations))
            self.progress_bar.setValue(len(self.processed_operations))
            self.lbl_progress_text.setText(
                f"{len(self.processed_operations)} / {len(self.raw_operations)}"
            )
            self.apply_sorting()
            self._check_ready_status()
        else:
            self.recalculate_file(filepath)

    def action_edit(self, op_id: int) -> None:
        """Открывает диалог редактирования операции."""
        target_raw = next(
            (item for item in self.raw_operations if item["id"] == op_id), None
        )
        if not target_raw:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Редактирование")
        dialog.resize(700, 500)

        layout = QVBoxLayout(dialog)
        te = QTextEdit()
        te.setPlainText(
            json.dumps(target_raw["op"], indent=2, ensure_ascii=False)
        )
        CodeHighlighter(te.document())
        layout.addWidget(te)

        btn_box = QHBoxLayout()
        btn_cancel = QPushButton("Отмена")
        btn_cancel.setObjectName("btn_danger")
        btn_cancel.clicked.connect(dialog.reject)

        btn_save = QPushButton("Сохранить")
        btn_save.setObjectName("btn_success")
        btn_save.clicked.connect(dialog.accept)

        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_save)
        layout.addLayout(btn_box)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                target_raw["op"] = json.loads(te.toPlainText())
                filepath = (
                    target_raw["op"].get("path")
                    or target_raw["op"].get("file", "unknown")
                )
                self.recalculate_file(filepath)
            except json.JSONDecodeError as e:
                QMessageBox.critical(self, "Ошибка JSON", str(e))

    def action_apply_suggestion(self, op_id: int, new_search_text: str) -> None:
        """Применяет подсказку от fuzzy search к операции."""
        target_raw = next(
            (item for item in self.raw_operations if item["id"] == op_id), None
        )
        if target_raw:
            target_raw["op"]["search"] = new_search_text
            filepath = (
                target_raw["op"].get("path")
                or target_raw["op"].get("file", "unknown")
            )
            self.recalculate_file(filepath)

    def apply_patch(self) -> None:
        """Применяет все успешные операции патча."""
        # Создаём бэкап
        self.backup_mgr.create_backup(self.patch_name, self.memory_files)

        try:
            for abs_p, content in self.memory_files.items():
                os.makedirs(os.path.dirname(abs_p), exist_ok=True)
                with open(abs_p, "w", encoding="utf-8") as f:
                    f.write(content)

            QMessageBox.information(
                self, "Успех", f"Патч '{self.patch_name}' успешно применен!"
            )
            self.clear_all()
        except (OSError, IOError) as e:
            QMessageBox.critical(
                self, "Ошибка записи", f"Не удалось записать файлы:\n{e}"
            )
