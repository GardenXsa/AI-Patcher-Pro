"""
Главное окно приложения AI Patcher Pro.

Поддерживает:
- Выполнение консольных команд из патча (after_analysis / after_apply)
- Обязательный запуск от имени администратора
- Лог выполнения команд с возможностью копирования
- Диалог подтверждения перед выполнением команд
- Реальное время статусов и потоковый вывод команд
"""

import os
import json
import time
from datetime import datetime

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
from PyQt6.QtCore import Qt, QTimer
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


# ─────────────────────── Цвета стадий ───────────────────────

STAGE_COLORS = {
    "parse": "#3498db",      # Синий — парсинг
    "load": "#f39c12",       # Оранжевый — загрузка файла
    "search": "#9b59b6",     # Фиолетовый — поиск
    "apply": "#2ecc71",      # Зелёный — применение
    "diff": "#1abc9c",       # Бирюзовый — генерация diff
    "cmd_start": "#f39c12",  # Оранжевый — команда началась
    "cmd_stdout": "#2ecc71", # Зелёный — вывод stdout
    "cmd_stderr": "#e74c3c", # Красный — вывод stderr
    "cmd_done": "#27ae60",   # Зелёный — команда завершена
    "done": "#27ae60",       # Зелёный — завершено
}

STAGE_LABELS = {
    "parse": "ПАРСИНГ",
    "load": "ЗАГРУЗКА",
    "search": "ПОИСК",
    "apply": "ПРИМЕНЕНИЕ",
    "diff": "DIFF",
    "cmd_start": "КОМАНДА",
    "cmd_stdout": "STDOUT",
    "cmd_stderr": "STDERR",
    "cmd_done": "РЕЗУЛЬТАТ",
    "done": "ГОТОВО",
}


class AIPatcherPro(QMainWindow):
    """Главное окно приложения AI Patcher Pro."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Patcher Pro v3.1")
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

        # Анимация пульсации индикатора
        self._pulse_state = False
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._toggle_pulse)

        self._setup_ui()
        self.backup_mgr.init_backup_dir()

    # ─────────────────── Анимация индикатора ───────────────────

    def _toggle_pulse(self) -> None:
        """Переключает пульсацию индикатора активности."""
        self._pulse_state = not self._pulse_state
        if self._pulse_state:
            self.lbl_activity_dot.setStyleSheet(
                "background-color: #2ecc71; border-radius: 7px;"
            )
        else:
            self.lbl_activity_dot.setStyleSheet(
                "background-color: #1a6b3a; border-radius: 7px;"
            )

    def _start_pulse(self) -> None:
        """Запускает пульсацию."""
        self._pulse_state = False
        self._pulse_timer.start(500)

    def _stop_pulse(self, success: bool = True) -> None:
        """Останавливает пульсацию и показывает финальный цвет."""
        self._pulse_timer.stop()
        color = "#27ae60" if success else "#c0392b"
        self.lbl_activity_dot.setStyleSheet(
            f"background-color: {color}; border-radius: 7px;"
        )

    # ─────────────────── Drag & Drop ───────────────────

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

    # ─────────────────── UI ───────────────────

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

        # ── Индикатор активности ──
        activity_frame = QFrame()
        activity_frame.setObjectName("activity_frame")
        act_layout = QHBoxLayout(activity_frame)
        act_layout.setContentsMargins(8, 4, 8, 4)

        self.lbl_activity_dot = QLabel()
        self.lbl_activity_dot.setFixedSize(14, 14)
        self.lbl_activity_dot.setStyleSheet(
            "background-color: #555555; border-radius: 7px;"
        )
        act_layout.addWidget(self.lbl_activity_dot)

        self.lbl_activity = QLabel("Ожидание")
        self.lbl_activity.setObjectName("lbl_activity")
        self.lbl_activity.setStyleSheet(
            "color: #888888; font-size: 12px; font-weight: bold;"
        )
        act_layout.addWidget(self.lbl_activity, 1)

        side_layout.addWidget(activity_frame)

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
        main_splitter = QSplitter(Qt.Orientation.Vertical)

        # Верхняя часть: карточки операций
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

        main_splitter.addWidget(right_panel)

        # ── ПАНЕЛЬ ЛОГА АКТИВНОСТИ (нижняя) ──
        log_panel = QWidget()
        log_panel.setObjectName("log_panel")
        log_layout = QVBoxLayout(log_panel)
        log_layout.setContentsMargins(10, 6, 10, 6)
        log_layout.setSpacing(4)

        # Заголовок лога
        log_header = QHBoxLayout()

        self.lbl_log_title = QLabel("Лог активности")
        self.lbl_log_title.setObjectName("log_title")
        log_header.addWidget(self.lbl_log_title)

        log_header.addStretch()

        self.btn_toggle_log = QPushButton("Свернуть")
        self.btn_toggle_log.setObjectName("btn_toggle_log")
        self.btn_toggle_log.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_log.setFixedWidth(90)
        self.btn_toggle_log.clicked.connect(self._toggle_log_panel)
        log_header.addWidget(self.btn_toggle_log)

        self.btn_clear_log = QPushButton("Очистить")
        self.btn_clear_log.setObjectName("btn_toggle_log")
        self.btn_clear_log.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_log.setFixedWidth(80)
        self.btn_clear_log.clicked.connect(self._clear_log)
        log_header.addWidget(self.btn_clear_log)

        log_layout.addLayout(log_header)

        # Текстовое поле лога
        self.activity_log = QTextEdit()
        self.activity_log.setReadOnly(True)
        self.activity_log.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.activity_log.setMaximumHeight(200)
        self.activity_log.setStyleSheet(
            "QTextEdit { font-family: Consolas, monospace; font-size: 11px; "
            "background-color: #0a0a0a; border: 1px solid #2a2a2a; border-radius: 4px; "
            "padding: 6px; color: #d4d4d4; }"
        )
        log_layout.addWidget(self.activity_log)

        main_splitter.addWidget(log_panel)
        main_splitter.setSizes([550, 200])

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

        tabs.addTab(main_splitter, "Патчер")

        self.scanner_tab = ScannerTab()
        tabs.addTab(self.scanner_tab, "Сканер проекта")

        splitter.addWidget(tabs)
        splitter.setSizes([380, 920])

        # Счётчик логов (для авто-обрезки)
        self._log_line_count = 0
        self._log_max_lines = 2000

    # ─────────────────── Лог активности ───────────────────

    def _log(self, stage: str, message: str, detail: str = "") -> None:
        """
        Добавляет запись в лог активности.

        Args:
            stage: Стадия обработки (parse, load, search, apply, diff, cmd_*).
            message: Основное сообщение.
            detail: Дополнительная информация.
        """
        now = datetime.now().strftime("%H:%M:%S")
        color = STAGE_COLORS.get(stage, "#888888")
        label = STAGE_LABELS.get(stage, stage.upper())

        detail_html = ""
        if detail:
            escaped_detail = (
                detail.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            detail_html = (
                f"<span style='color: #666666; font-size: 10px;'> "
                f"→ {escaped_detail}</span>"
            )

        escaped_msg = (
            message.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

        line = (
            f"<div style='padding: 1px 0;'>"
            f"<span style='color: #555555;'>{now}</span> "
            f"<span style='color: {color}; font-weight: bold;'>[{label}]</span> "
            f"<span style='color: #d4d4d4;'>{escaped_msg}</span>"
            f"{detail_html}"
            f"</div>"
        )

        self.activity_log.append(line)
        self._log_line_count += 1

        # Авто-обрезка при превышении лимита
        if self._log_line_count > self._log_max_lines:
            cursor = self.activity_log.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            # Удаляем первые 500 строк
            for _ in range(500):
                cursor.movePosition(
                    cursor.MoveOperation.Down, cursor.MoveMode.KeepAnchor
                )
            cursor.movePosition(
                cursor.MoveOperation.StartOfLine, cursor.MoveMode.KeepAnchor
            )
            cursor.removeSelectedText()
            self._log_line_count -= 500

        # Прокрутка вниз
        self.activity_log.verticalScrollBar().setValue(
            self.activity_log.verticalScrollBar().maximum()
        )

    def _clear_log(self) -> None:
        """Очищает лог активности."""
        self.activity_log.clear()
        self._log_line_count = 0

    _log_collapsed = False

    def _toggle_log_panel(self) -> None:
        """Сворачивает/разворачивает панель лога."""
        if self._log_collapsed:
            self.activity_log.setVisible(True)
            self.btn_toggle_log.setText("Свернуть")
            self._log_collapsed = False
        else:
            self.activity_log.setVisible(False)
            self.btn_toggle_log.setText("Развернуть")
            self._log_collapsed = True

    def _update_activity_indicator(self, stage: str, message: str) -> None:
        """Обновляет индикатор активности в сайдбаре."""
        color = STAGE_COLORS.get(stage, "#888888")
        label = STAGE_LABELS.get(stage, "")

        self.lbl_activity.setText(f"{label}: {message}")
        self.lbl_activity.setStyleSheet(
            f"color: {color}; font-size: 12px; font-weight: bold;"
        )

    # ─────────────────── Основные действия ───────────────────

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

        # Сброс индикатора
        self._stop_pulse(success=False)
        self.lbl_activity_dot.setStyleSheet(
            "background-color: #555555; border-radius: 7px;"
        )
        self.lbl_activity.setText("Ожидание")
        self.lbl_activity.setStyleSheet(
            "color: #888888; font-size: 12px; font-weight: bold;"
        )

        self._clear_log()

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

    # ─────────────────── Парсинг и анализ ───────────────────

    def parse_and_analyze(self) -> None:
        """Парсит JSON из текстового поля и запускает анализ."""
        self._log("parse", "Парсинг JSON из текстового поля...")

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

            self._log(
                "parse",
                f"Найдено: {len(self.raw_operations)} операций, "
                f"{len(all_commands)} команд",
                f"Патч: {self.patch_name}"
            )

        except (ValueError, json.JSONDecodeError) as e:
            self._log("parse", f"Ошибка парсинга: {e}")
            self._stop_pulse(success=False)
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

        self._start_pulse()

        if not is_recalc:
            self.progress_bar.setMaximum(len(self.raw_operations))
            self.progress_bar.setValue(0)
            while self.scroll_layout.count():
                child = self.scroll_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

        self.thread = ProcessorThread(self.workspace, pending_ops, self.memory_files)
        self.thread.status_update.connect(self._on_status_update)
        self.thread.operation_done.connect(self._on_operation_done)
        self.thread.finished_all.connect(self._on_analysis_finished)
        self.thread.start()

    def _on_status_update(self, stage: str, message: str, detail: str) -> None:
        """Обрабатывает промежуточный статус обработки."""
        self._log(stage, message, detail)
        self._update_activity_indicator(stage, message)

    def _on_operation_done(self, result: dict) -> None:
        """Обрабатывает завершение одной операции."""
        self.processed_operations.append(result)
        self.progress_bar.setValue(len(self.processed_operations))
        self.lbl_progress_text.setText(
            f"{len(self.processed_operations)} / {len(self.raw_operations)}"
        )

        # Логируем результат
        op = result["op"]
        file_path = op.get("path") or op.get("file", "?")
        action = op.get("action") or op.get("op", "?")
        status = result["status"]

        if status == "success":
            self._log("done", f"OK: {action} → {file_path}")
        elif status == "already_applied":
            self._log("done", f"УЖЕ ПРИМЕНЕНО: {action} → {file_path}")
        else:
            self._log("cmd_stderr", f"ОШИБКА: {action} → {file_path}", result.get("error", ""))

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
        else:
            # Нет команд — просто остановить пульсацию
            has_errors = any(op["status"] == "error" for op in self.processed_operations)
            self._stop_pulse(success=not has_errors)

    # ─────────────────── Выполнение команд ───────────────────

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

        self._start_pulse()

        self.cmd_log_frame.setVisible(True)
        self.cmd_log_text.clear()
        self._current_cmd_phase = phase
        self._current_cmd_index = 0

        self._log("cmd_start", f"Начало выполнения {len(commands)} команд ({phase})")

        self._cmd_thread = CommandExecutorThread(commands, self.workspace)
        self._cmd_thread.command_started.connect(self._on_command_started)
        self._cmd_thread.command_output.connect(self._on_command_output)
        self._cmd_thread.command_done.connect(self._on_command_done)
        self._cmd_thread.finished_all.connect(self._on_commands_finished)
        self._cmd_thread.start()

    def _on_command_started(self, index: int, cmd: str, description: str) -> None:
        """Обрабатывает начало выполнения команды."""
        self._current_cmd_index = index
        self._log("cmd_start", f"[{index + 1}] Запуск: {cmd}", description)

        self._update_activity_indicator("cmd_start", f"Команда {index + 1}: {cmd[:60]}...")

        # Добавляем заголовок в лог команд
        html = self.cmd_log_text.toHtml()
        header = (
            f"<div style='margin-bottom: 4px; padding: 6px; "
            f"border: 1px solid #f39c12; border-radius: 6px; "
            f"background-color: #1a1a1a;'>"
            f"<div style='color: #f39c12; font-weight: bold; font-size: 13px;'>"
            f"<span id='cmd_{index}'>{index + 1}. {cmd.replace('<', '&lt;').replace('>', '&gt;')}</span>"
            f" <span style='color: #888; font-size: 11px;'>⏳ Выполняется...</span></div>"
        )
        if description:
            header += (
                f"<div style='color: #8e44ad; font-style: italic; font-size: 12px; "
                f"margin-top: 2px;'>{description.replace('<', '&lt;').replace('>', '&gt;')}</div>"
            )
        header += (
            f"<div id='cmd_out_{index}' style='font-family: Consolas, monospace; "
            f"font-size: 11px; white-space: pre-wrap;'></div>"
            f"</div>"
        )
        self.cmd_log_text.setHtml(html + header)

    def _on_command_output(self, index: int, stream_type: str, data: str) -> None:
        """
        Обрабатывает потоковый вывод команды в реальном времени.

        Args:
            index: Порядковый номер команды.
            stream_type: "stdout" или "stderr".
            data: Порция вывода.
        """
        color = "#2ecc71" if stream_type == "stdout" else "#e74c3c"
        stage = "cmd_stdout" if stream_type == "stdout" else "cmd_stderr"

        # В лог активности — только первые строки, чтобы не засорять
        preview = data.strip()[:200]
        if preview:
            self._log(stage, f"[{index + 1}] {stream_type}: {preview}")

        # В лог команд — полный вывод
        escaped = (
            data.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        # Добавляем в текущую команду
        # Перечитываем и пересобираем HTML с новым выводом
        current_html = self.cmd_log_text.toHtml()
        # Вставляем перед закрывающим div команды
        insert_marker = f"id='cmd_out_{index}'"
        if insert_marker in current_html:
            # Добавляем порцию вывода внутрь блока
            span = (
                f"<span style='color: {color};'>{escaped}</span>"
            )
            # Заменяем маркер, добавляя span после него
            current_html = current_html.replace(
                f"{insert_marker} style='font-family: Consolas, monospace; "
                f"font-size: 11px; white-space: pre-wrap;'>",
                f"{insert_marker} style='font-family: Consolas, monospace; "
                f"font-size: 11px; white-space: pre-wrap;'>{span}",
            )
            self.cmd_log_text.setHtml(current_html)
        else:
            # Fallback — просто добавляем
            self.cmd_log_text.append(
                f"<span style='color: {color};'>{escaped}</span>"
            )

    def _on_command_done(self, result: dict) -> None:
        """Обрабатывает завершение одной команды."""
        self.command_results.append(result)
        self._update_command_log()

        cmd = result.get("cmd", "???")
        status = result.get("status", "???")
        returncode = result.get("returncode", -1)

        if status == "success":
            self._log("cmd_done", f"OK: {cmd[:80]}", f"Код возврата: {returncode}")
        else:
            stderr_preview = (result.get("stderr", "") or "")[:200]
            self._log("cmd_stderr", f"ОШИБКА: {cmd[:80]}", f"Код: {returncode}, {stderr_preview}")

        self._update_activity_indicator(
            "cmd_done",
            f"Команда {self._current_cmd_index + 1} завершена"
        )

    def _on_commands_finished(self) -> None:
        """Обрабатывает завершение всех команд."""
        self.btn_analyze.setEnabled(True)
        QApplication.restoreOverrideCursor()
        self._check_ready_status()

        has_cmd_errors = any(
            r.get("status") == "error"
            for r in self.command_results
        )
        self._stop_pulse(success=not has_cmd_errors)

        self._log(
            "done",
            f"Все команды выполнены. Успешно: "
            f"{sum(1 for r in self.command_results if r.get('status') == 'success')}, "
            f"Ошибки: {sum(1 for r in self.command_results if r.get('status') == 'error')}"
        )

    def _update_command_log(self) -> None:
        """Обновляет блок лога команд (полная перерисовка при завершении команды)."""
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

    # ─────────────────── Сортировка и статусы ───────────────────

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

    # ─────────────────── Действия с операциями ───────────────────

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

        self._log("apply", f"Запись файлов на диск...")

        try:
            for abs_p, content in self.memory_files.items():
                os.makedirs(os.path.dirname(abs_p), exist_ok=True)
                with open(abs_p, "w", encoding="utf-8") as f:
                    f.write(content)

            self._log("done", f"Патч '{self.patch_name}' успешно применён!")

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
            self._log("cmd_stderr", f"Ошибка записи: {e}")
            self._stop_pulse(success=False)
            QMessageBox.critical(
                self, "Ошибка записи", f"Не удалось записать файлы:\n{e}"
            )
