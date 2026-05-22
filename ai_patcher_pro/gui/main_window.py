"""
Главное окно приложения AI Patcher Pro.

Поддерживает:
- Выполнение консольных команд из патча (after_analysis / after_apply)
- Обязательный запуск от имени администратора
- Лог выполнения команд с возможностью копирования
- Диалог подтверждения перед выполнением команд
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
    QTabWidget,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDragEnterEvent, QDropEvent

from ai_patcher_pro.core.json_parser import extract_all_json
from ai_patcher_pro.core.security import secure_path_join
from ai_patcher_pro.core.backup import BackupManager
from ai_patcher_pro.core.processor import ProcessorThread
from ai_patcher_pro.core.command_executor import CommandExecutorThread
from ai_patcher_pro.gui.operation_card import OperationCard
from ai_patcher_pro.gui.backup_dialog import BackupManagerDialog
from ai_patcher_pro.gui.code_viewer import CodeHighlighter
from ai_patcher_pro.gui.scanner_tab import ScannerTab
from ai_patcher_pro.utils.file_io import read_file_safe


class AIPatcherPro(QMainWindow):
    """Главное окно приложения AI Patcher Pro."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Patcher Pro v3.0")
        self.resize(1300, 800)
        self.setAcceptDrops(True)

        self.workspace = os.getcwd()
        self.patch_name = "Без имени"
        self.raw_operations: list = []
        self.processed_operations: list = []
        self.memory_files: dict = {}

        # Команды из патча
        self.commands_after_analysis: list = []
        self.commands_after_apply: list = []
        self.command_results: list = []

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

        # --- БЛОК ЛОГА КОМАНД ---
        self.cmd_log_frame = QFrame()
        self.cmd_log_frame.setObjectName("cmd_log_frame")
        self.cmd_log_frame.setVisible(False)

        cmd_log_layout = QVBoxLayout(self.cmd_log_frame)
        cmd_log_layout.setContentsMargins(15, 15, 15, 15)

        cmd_header = QHBoxLayout()
        lbl_cmd_title = QLabel("Лог выполнения команд")
        lbl_cmd_title.setObjectName("accent_title")
        cmd_header.addWidget(lbl_cmd_title)
        cmd_header.addStretch()

        self.btn_copy_cmd_log = QPushButton("Скопировать лог")
        self.btn_copy_cmd_log.setObjectName("btn_copy")
        self.btn_copy_cmd_log.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy_cmd_log.clicked.connect(self._copy_command_log)
        cmd_header.addWidget(self.btn_copy_cmd_log)
        cmd_log_layout.addLayout(cmd_header)

        self.cmd_log_text = QTextEdit()
        self.cmd_log_text.setReadOnly(True)
        self.cmd_log_text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.cmd_log_text.setMaximumHeight(250)
        self.cmd_log_text.setStyleSheet(
            "QTextEdit { font-family: Consolas, monospace; font-size: 12px; "
            "background-color: #0d0d0d; border: 1px solid #3c3c3c; border-radius: 6px; "
            "padding: 8px; color: #d4d4d4; }"
        )
        cmd_log_layout.addWidget(self.cmd_log_text)

        right_layout.addWidget(self.cmd_log_frame)

        # --- ТАБЫ: Патчер + Сканер ---
        tabs = QTabWidget()
        tabs.setStyleSheet(
            "QTabWidget::pane { border: none; background-color: #1e1e1e; }"
            "QTabBar::tab { background-color: #2d2d2d; color: #d4d4d4; "
            "padding: 8px 20px; border-top-left-radius: 6px; "
            "border-top-right-radius: 6px; margin-right: 2px; font-weight: bold; }"
            "QTabBar::tab:selected { background-color: #1e1e1e; color: #3498db; }"
            "QTabBar::tab:hover { background-color: #3a3a3a; }"
        )

        tabs.addTab(right_panel, "Патчер")

        self.scanner_tab = ScannerTab()
        tabs.addTab(self.scanner_tab, "Сканер проекта")

        splitter.addWidget(tabs)
        splitter.setSizes([380, 920])

    def clear_all(self) -> None:
        """Очищает все данные и UI."""
        self.txt_json.clear()
        self.raw_operations.clear()
        self.processed_operations.clear()
        self.memory_files.clear()
        self.commands_after_analysis.clear()
        self.commands_after_apply.clear()
        self.command_results.clear()

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
        self.cmd_log_frame.setVisible(False)
        self.cmd_log_text.clear()

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
            # Разделяем команды по времени выполнения
            all_commands = data.get("commands", [])
            self.commands_after_analysis = [
                c for c in all_commands if c.get("run") == "after_analysis"
            ]
            self.commands_after_apply = [
                c for c in all_commands if c.get("run") == "after_apply"
            ]
            self.command_results.clear()
        except (ValueError, json.JSONDecodeError) as e:
            QMessageBox.critical(self, "Ошибка парсинга", str(e))
            return

        self.processed_operations.clear()
        self.memory_files.clear()
        self._start_processing(self.raw_operations)

    def recalculate_file(self, filepath: str) -> None:
        """
        Пересчитывает операции для конкретного файла.
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

        # Если есть команды after_analysis — предлагаем выполнить
        if self.commands_after_analysis:
            self._propose_commands(
                self.commands_after_analysis,
                "after_analysis",
            )

    def _propose_commands(self, commands: list, phase: str) -> None:
        """
        Показывает диалог подтверждения перед выполнением команд.

        Args:
            commands: Список нормализованных команд.
            phase: Фаза выполнения ("after_analysis" или "after_apply").
        """
        if not commands:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Выполнение консольных команд")
        dialog.resize(700, 500)
        dialog.setStyleSheet(
            "QDialog { background-color: #1e1e1e; } "
            "QLabel { color: #d4d4d4; } "
            "QTextEdit { background-color: #151515; color: #d4d4d4; "
            "border: 1px solid #3c3c3c; border-radius: 6px; "
            "padding: 8px; font-family: Consolas, monospace; font-size: 13px; }"
        )

        layout = QVBoxLayout(dialog)

        # Предупреждение
        lbl_warn = QLabel(
            "ВНИМАНИЕ: Команды сгенерированы ИИ и будут выполнены в консоли.\n"
            "Убедитесь, что вы доверяете источнику!"
        )
        lbl_warn.setStyleSheet("color: #f39c12; font-weight: bold; font-size: 13px;")
        lbl_warn.setWordWrap(True)
        layout.addWidget(lbl_warn)

        phase_text = {
            "after_analysis": "после анализа (до применения патча)",
            "after_apply": "после применения патча",
        }
        lbl_phase = QLabel(
            f"Фаза выполнения: {phase_text.get(phase, phase)}"
        )
        lbl_phase.setStyleSheet("color: #3498db; font-size: 12px; font-style: italic;")
        layout.addWidget(lbl_phase)

        # Список команд
        lbl_cmd_list = QLabel("Команды для выполнения:")
        lbl_cmd_list.setStyleSheet("color: #d4d4d4; font-weight: bold; margin-top: 10px;")
        layout.addWidget(lbl_cmd_list)

        cmd_text_parts = []
        for i, cmd_info in enumerate(commands, 1):
            cmd_str = cmd_info.get("cmd", "")
            desc = cmd_info.get("description", "")
            warnings = cmd_info.get("warnings", [])

            line = f"{i}. {cmd_str}"
            if desc:
                line += f"  — {desc}"
            cmd_text_parts.append(line)

            if warnings:
                for w in warnings:
                    cmd_text_parts.append(f"   ОПАСНО: {w}")

        cmd_display = QTextEdit()
        cmd_display.setReadOnly(True)
        cmd_display.setPlainText("\n".join(cmd_text_parts))

        # Подсветка опасных команд
        html = "<pre style='font-family: Consolas, monospace; font-size: 13px; margin: 0;'>"
        for line in cmd_text_parts:
            escaped = line.replace("<", "&lt;").replace(">", "&gt;")
            if line.strip().startswith("ОПАСНО:"):
                html += f"<div style='color: #e74c3c; background-color: rgba(192,57,43,0.15); padding: 2px;'>{escaped}</div>"
            else:
                html += f"<div style='color: #d4d4d4; padding: 2px;'>{escaped}</div>"
        html += "</pre>"
        cmd_display.setHtml(html)
        layout.addWidget(cmd_display)

        # Кнопки
        btn_box = QHBoxLayout()
        btn_cancel = QPushButton("Отмена")
        btn_cancel.setObjectName("btn_danger")
        btn_cancel.setStyleSheet(
            "background-color: #c0392b; color: white; border: none; "
            "padding: 8px 20px; border-radius: 6px; font-weight: bold;"
        )
        btn_cancel.clicked.connect(dialog.reject)

        btn_execute = QPushButton("Выполнить команды")
        btn_execute.setStyleSheet(
            "background-color: #27ae60; color: white; border: none; "
            "padding: 8px 20px; border-radius: 6px; font-weight: bold;"
        )
        btn_execute.clicked.connect(dialog.accept)

        btn_box.addWidget(btn_cancel)
        btn_box.addStretch()
        btn_box.addWidget(btn_execute)
        layout.addLayout(btn_box)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._execute_commands(commands, phase)

    def _execute_commands(self, commands: list, phase: str) -> None:
        """
        Запускает выполнение команд в фоновом потоке.

        Args:
            commands: Список нормализованных команд.
            phase: Фаза выполнения.
        """
        self.btn_analyze.setEnabled(False)
        self.btn_apply.setEnabled(False)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        self.cmd_log_frame.setVisible(True)
        self.cmd_log_text.clear()
        self._current_cmd_phase = phase

        self._cmd_thread = CommandExecutorThread(commands, self.workspace)
        self._cmd_thread.command_done.connect(self._on_command_done)
        self._cmd_thread.finished_all.connect(self._on_commands_finished)
        self._cmd_thread.start()

    def _on_command_done(self, result: dict) -> None:
        """Обрабатывает завершение одной команды."""
        self.command_results.append(result)
        self._update_command_log()

    def _on_commands_finished(self) -> None:
        """Обрабатывает завершение всех команд."""
        self.btn_analyze.setEnabled(True)
        QApplication.restoreOverrideCursor()
        self._check_ready_status()

    def _update_command_log(self) -> None:
        """Обновляет блок лога команд."""
        html_parts = []
        for i, result in enumerate(self.command_results, 1):
            cmd = result.get("cmd", "???")
            desc = result.get("description", "")
            status = result.get("status", "???")
            stdout = result.get("stdout", "")
            stderr = result.get("stderr", "")
            returncode = result.get("returncode", -1)

            # Заголовок команды
            status_color = "#27ae60" if status == "success" else "#c0392b"
            status_text = "УСПЕХ" if status == "success" else f"ОШИБКА (код: {returncode})"

            html_parts.append(
                f"<div style='margin-bottom: 10px; padding: 8px; "
                f"border: 1px solid {status_color}; border-radius: 6px; "
                f"background-color: #1a1a1a;'>"
            )
            html_parts.append(
                f"<div style='color: {status_color}; font-weight: bold; font-size: 13px;'>"
                f"{i}. {cmd.replace('<', '&lt;').replace('>', '&gt;')} — {status_text}</div>"
            )
            if desc:
                html_parts.append(
                    f"<div style='color: #8e44ad; font-style: italic; font-size: 12px; "
                    f"margin-top: 2px;'>{desc.replace('<', '&lt;').replace('>', '&gt;')}</div>"
                )
            if stdout.strip():
                escaped_out = (
                    stdout.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                html_parts.append(
                    f"<div style='color: #2ecc71; font-size: 12px; margin-top: 4px; "
                    f"white-space: pre-wrap;'>stdout:\n{escaped_out}</div>"
                )
            if stderr.strip():
                escaped_err = (
                    stderr.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                html_parts.append(
                    f"<div style='color: #e74c3c; font-size: 12px; margin-top: 4px; "
                    f"white-space: pre-wrap;'>stderr:\n{escaped_err}</div>"
                )
            html_parts.append("</div>")

        self.cmd_log_text.setHtml("".join(html_parts))

    def _copy_command_log(self) -> None:
        """Копирует лог выполнения команд в буфер обмена."""
        lines = []
        for i, result in enumerate(self.command_results, 1):
            cmd = result.get("cmd", "???")
            desc = result.get("description", "")
            status = result.get("status", "???")
            stdout = result.get("stdout", "")
            stderr = result.get("stderr", "")
            returncode = result.get("returncode", -1)

            status_text = "УСПЕХ" if status == "success" else f"ОШИБКА (код: {returncode})"
            lines.append(f"--- Команда {i}: {cmd} ---")
            if desc:
                lines.append(f"Описание: {desc}")
            lines.append(f"Статус: {status_text}")
            if stdout.strip():
                lines.append(f"stdout:\n{stdout}")
            if stderr.strip():
                lines.append(f"stderr:\n{stderr}")
            lines.append("")

        QApplication.clipboard().setText("\n".join(lines))
        QMessageBox.information(self, "Скопировано", "Лог команд скопирован в буфер обмена!")

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
        has_cmd_errors = any(
            r.get("status") == "error"
            for r in self.command_results
        )

        if not has_errors and not has_cmd_errors and self.processed_operations:
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

            # Если есть команды after_apply — предлагаем выполнить
            if self.commands_after_apply:
                self._propose_commands(
                    self.commands_after_apply,
                    "after_apply",
                )
            else:
                self.clear_all()

        except (OSError, IOError) as e:
            QMessageBox.critical(
                self, "Ошибка записи", f"Не удалось записать файлы:\n{e}"
            )
