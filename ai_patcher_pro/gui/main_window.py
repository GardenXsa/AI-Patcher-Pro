"""
Главное окно приложения AI Patcher Pro.

Чёткий пайплайн статусов:
1. ПАРСИНГ — разбор JSON
2. АНАЛИЗ — поиск кода, генерация превью (карточки показывают "НАЙДЕНО")
3. КОД НА ДИСК — запись файлов (карточки обновляются на "ПРИМЕНЕНО")
4. КОМАНДЫ — выполнение after_apply команд
5. ГОТОВО — итоговый результат

Ключевые визуальные элементы:
- Пайплайн-индикатор фаз в сайдбаре
- Сводный баннер после каждой фазы
- Карточки с чётким разделением "превью" vs "применено"
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
    QMessageBox,
    QFileDialog,
    QSplitter,
    QApplication,
    QScrollArea,
    QFrame,
    QDialog,
    QStackedWidget,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QDragEnterEvent, QDropEvent

from ai_patcher_pro.core.json_parser import extract_all_json
from ai_patcher_pro.core.processor import ProcessorThread
from ai_patcher_pro.core.backup import BackupManager
from ai_patcher_pro.core.security import secure_path_join
from ai_patcher_pro.core.command_executor import CommandExecutorThread
from ai_patcher_pro.core.ai_report import build_ai_patch_report

from ai_patcher_pro.core.workflow import (
    find_applied_patch,
    format_git_safety_report,
    get_check_commands,
    get_check_profiles,
    gpt_handoff_text,
    mark_patch_applied,
    patch_fingerprint,
    project_rule_warnings,
    save_project_profile,
    workflow_status_report,
)
from ai_patcher_pro.gui.operation_card import OperationCard
from ai_patcher_pro.gui.backup_dialog import BackupManagerDialog
from ai_patcher_pro.gui.scanner_tab import ScannerTab


# ───────────────────── UI Helpers ─────────────────────

PHASES = [
    ("parse", "Парсинг"),
    ("analysis", "Анализ"),
    ("write", "Код на диск"),
    ("commands", "Команды"),
    ("done", "Готово"),
]

PIPELINE_COLORS = {
    "inactive": "#333333",
    "active": "#00bcd4",
    "completed": "#27ae60",
    "error": "#c0392b",
}


class AIPatcherPro(QMainWindow):
    """Главное окно приложения AI Patcher Pro."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Patcher Pro v3.2")
        # Стартовый размер меньше прежнего, чтобы окно нормально помещалось
        # на мониторах с масштабированием 125–150% и на ноутбуках.
        self.resize(1180, 720)
        self.setMinimumSize(860, 560)
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

        # Флаг: патч записан на диск
        self._patch_written = False

        # Runtime-защита от двойного клика по применению
        self._is_applying = False


        # Workflow state
        self._current_patch_fingerprint = ""
        self._current_patch_registry_match = None

        self.backup_mgr = BackupManager(self.workspace)

        # Анимация пульсации индикатора
        self._pulse_state = False
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._toggle_pulse)

        # Текущая фаза пайплайна
        self._current_phase = "parse"

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

    def _start_pulse(self, text: str = "Выполняется...") -> None:
        """Запускает анимацию активности."""
        self.lbl_activity.setText(text)
        self.lbl_activity.setStyleSheet(
            "color: #00bcd4; font-size: 12px; font-weight: bold;"
        )
        self._pulse_timer.start(500)

    def _stop_pulse(self, success: bool = True) -> None:
        """Останавливает анимацию активности."""
        self._pulse_timer.stop()
        if success:
            self.lbl_activity_dot.setStyleSheet(
                "background-color: #27ae60; border-radius: 7px;"
            )
            self.lbl_activity.setText("Готово")
            self.lbl_activity.setStyleSheet(
                "color: #27ae60; font-size: 12px; font-weight: bold;"
            )
        else:
            self.lbl_activity_dot.setStyleSheet(
                "background-color: #555555; border-radius: 7px;"
            )
            self.lbl_activity.setText("Ожидание")
            self.lbl_activity.setStyleSheet(
                "color: #888888; font-size: 12px; font-weight: bold;"
            )

    # ─────────────────── Drag & Drop ───────────────────

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Обрабатывает начало drag & drop."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        """Обрабатывает drop файла в окно."""
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path and os.path.isfile(path):
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        self.txt_json.setPlainText(f.read())
                    self._log("parse", f"Файл загружен: {os.path.basename(path)}")
                    break
                except OSError as e:
                    QMessageBox.critical(
                        self, "Ошибка", f"Не удалось прочитать файл:\n{e}"
                    )

    # ─────────────────── UI Setup ───────────────────

    def _setup_ui(self) -> None:
        """Создаёт интерфейс приложения."""
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        # ════════════════ LEFT SIDEBAR ════════════════
        # Важно: сайдбар должен скроллиться по вертикали.
        # Иначе на небольших мониторах / при 125–150% scaling он растягивает
        # всё окно вниз, и интерфейс перестаёт помещаться в экран.
        sidebar_content = QWidget()
        sidebar_content.setObjectName("sidebar")
        sidebar_content.setMinimumWidth(300)
        sidebar_content.setMaximumWidth(430)
        sidebar_content.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.MinimumExpanding,
        )

        side_layout = QVBoxLayout(sidebar_content)
        side_layout.setSpacing(8)
        side_layout.setContentsMargins(12, 12, 12, 12)

        sidebar = QScrollArea()
        sidebar.setObjectName("sidebar_scroll")
        sidebar.setWidgetResizable(True)
        sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sidebar.setMinimumWidth(320)
        sidebar.setMaximumWidth(450)
        sidebar.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding,
        )
        sidebar.setWidget(sidebar_content)
        sidebar.setStyleSheet(
            "QScrollArea#sidebar_scroll { border: none; background-color: #252526; }"
            "QScrollArea#sidebar_scroll > QWidget > QWidget { background-color: #252526; }"
        )

        title = QLabel("AI Patcher Pro")
        title.setObjectName("title")
        side_layout.addWidget(title)

        subtitle = QLabel("v3.2 — безопасные JSON-патчи + команды + сканер")
        subtitle.setStyleSheet("color: #888; font-size: 11px;")
        side_layout.addWidget(subtitle)

        # ── Workspace selector ──
        ws_box = QHBoxLayout()
        self.lbl_workspace = QLabel(f"Папка: {os.path.basename(self.workspace)}")
        self.lbl_workspace.setStyleSheet("color: #aaa; font-size: 11px;")
        ws_box.addWidget(self.lbl_workspace, 1)

        btn_ws = QPushButton("...")
        btn_ws.setFixedWidth(40)
        btn_ws.clicked.connect(self.select_workspace)
        ws_box.addWidget(btn_ws)
        side_layout.addLayout(ws_box)

        # ── Tab selector ──
        tab_box = QHBoxLayout()
        self.btn_patch_tab = QPushButton("Патчи")
        self.btn_patch_tab.setObjectName("btn_toggle_active")
        self.btn_patch_tab.clicked.connect(lambda: self._switch_tab("patch"))
        tab_box.addWidget(self.btn_patch_tab)

        self.btn_scan_tab = QPushButton("Сканер")
        self.btn_scan_tab.setObjectName("btn_toggle_log")
        self.btn_scan_tab.clicked.connect(lambda: self._switch_tab("scanner"))
        tab_box.addWidget(self.btn_scan_tab)
        side_layout.addLayout(tab_box)

        # ── Input area ──
        self.lbl_input = QLabel("JSON-патч от ИИ:")
        side_layout.addWidget(self.lbl_input)

        self.txt_json = QTextEdit()
        self.txt_json.setPlaceholderText(
            "Вставьте JSON-патч сюда или перетащите файл...\n\n"
            "Поддерживаются:\n"
            "• Markdown code blocks\n"
            "• Альтернативные поля path/file, action/op\n"
            "• Команды commands/cmds/exec"
        )
        self.txt_json.setMinimumHeight(200)
        side_layout.addWidget(self.txt_json, 1)

        # ── Buttons ──
        btn_box = QHBoxLayout()
        self.btn_analyze = QPushButton("Парсить и Анализировать")
        self.btn_analyze.setObjectName("btn_primary")
        self.btn_analyze.clicked.connect(self.parse_and_analyze)
        btn_box.addWidget(self.btn_analyze, 2)

        btn_clear = QPushButton("Очистить")
        btn_clear.setObjectName("btn_danger")
        btn_clear.clicked.connect(self.clear_all)
        btn_box.addWidget(btn_clear)
        side_layout.addLayout(btn_box)

        # ── Pipeline indicator ──
        pipeline_frame = QFrame()
        pipeline_frame.setObjectName("pipeline_frame")
        pipeline_layout = QVBoxLayout(pipeline_frame)
        pipeline_layout.setSpacing(6)
        pipeline_layout.setContentsMargins(8, 8, 8, 8)

        pipeline_title = QLabel("Пайплайн")
        pipeline_title.setStyleSheet(
            "color: #00bcd4; font-size: 12px; font-weight: bold;"
        )
        pipeline_layout.addWidget(pipeline_title)

        self.phase_labels = {}
        self.phase_dots = {}
        for phase_id, phase_name in PHASES:
            row = QHBoxLayout()
            dot = QLabel("●")
            dot.setFixedWidth(18)
            dot.setStyleSheet(f"color: {PIPELINE_COLORS['inactive']}; font-size: 16px;")
            row.addWidget(dot)

            lbl = QLabel(phase_name)
            lbl.setStyleSheet("color: #777; font-size: 11px;")
            row.addWidget(lbl, 1)

            self.phase_dots[phase_id] = dot
            self.phase_labels[phase_id] = lbl
            pipeline_layout.addLayout(row)

        side_layout.addWidget(pipeline_frame)

        # ── Activity log toggle ──
        log_toggle_box = QHBoxLayout()
        self.lbl_activity_dot = QLabel("")
        self.lbl_activity_dot.setFixedSize(14, 14)
        self.lbl_activity_dot.setStyleSheet(
            "background-color: #555555; border-radius: 7px;"
        )
        log_toggle_box.addWidget(self.lbl_activity_dot)

        self.lbl_activity = QLabel("Ожидание")
        self.lbl_activity.setStyleSheet(
            "color: #888888; font-size: 12px; font-weight: bold;"
        )
        log_toggle_box.addWidget(self.lbl_activity, 1)

        self.btn_log_toggle = QPushButton("Лог")
        self.btn_log_toggle.setObjectName("btn_toggle_log")
        self.btn_log_toggle.setFixedWidth(50)
        self.btn_log_toggle.clicked.connect(self._toggle_log)
        log_toggle_box.addWidget(self.btn_log_toggle)
        side_layout.addLayout(log_toggle_box)

        # ── Summary banner ──
        self.summary_frame = QFrame()
        self.summary_frame.setObjectName("summary_frame")
        self.summary_frame.setVisible(False)
        summary_layout = QVBoxLayout(self.summary_frame)
        summary_layout.setContentsMargins(8, 6, 8, 6)

        self.lbl_summary = QLabel("")
        self.lbl_summary.setObjectName("lbl_summary")
        self.lbl_summary.setWordWrap(True)
        self.lbl_summary.setStyleSheet(
            "font-size: 12px; font-weight: bold; padding: 4px;"
        )
        summary_layout.addWidget(self.lbl_summary)

        side_layout.addWidget(self.summary_frame)

                # Главное оставляем на виду. Всё вторичное прячем в раскрываемый блок,
        # чтобы сайдбар не превращался в стену кнопок.
        self.btn_report = QPushButton("Скопировать отчёт для GPT")
        self.btn_report.setObjectName("btn_warning")
        self.btn_report.setToolTip(
            "Копирует полный текстовый отчёт: операции, ошибки, команды, stdout/stderr. "
            "Это удобнее для GPT, чем скриншоты."
        )
        self.btn_report.clicked.connect(self.copy_ai_report)
        side_layout.addWidget(self.btn_report)

        self.btn_workflow = QPushButton("Что сейчас делать?")
        self.btn_workflow.setObjectName("btn_purple")
        self.btn_workflow.setToolTip("Показывает один безопасный следующий шаг.")
        self.btn_workflow.clicked.connect(self.show_workflow_assistant)
        side_layout.addWidget(self.btn_workflow)

        self.btn_more_tools = QPushButton("Доп. инструменты ▼")
        self.btn_more_tools.setObjectName("btn_toggle_log")
        self.btn_more_tools.setToolTip("Git, профили, handoff, проверки и история бэкапов.")
        self.btn_more_tools.clicked.connect(self._toggle_advanced_tools)
        side_layout.addWidget(self.btn_more_tools)

        self.advanced_tools_frame = QFrame()
        self.advanced_tools_frame.setObjectName("advanced_tools_frame")
        self.advanced_tools_frame.setVisible(False)
        advanced_layout = QVBoxLayout(self.advanced_tools_frame)
        advanced_layout.setSpacing(6)
        advanced_layout.setContentsMargins(8, 8, 8, 8)

        self.btn_history = QPushButton("История бэкапов")
        self.btn_history.setObjectName("btn_copy")
        self.btn_history.clicked.connect(
            lambda: BackupManagerDialog(self, self.workspace).exec()
        )
        advanced_layout.addWidget(self.btn_history)

        self.btn_save_report = QPushButton("Сохранить PATCH_RESULT.md")
        self.btn_save_report.setObjectName("btn_copy")
        self.btn_save_report.setToolTip("Сохраняет понятный GPT отчёт в корень проекта.")
        self.btn_save_report.clicked.connect(self.save_ai_report_to_file)
        advanced_layout.addWidget(self.btn_save_report)

        self.btn_git_safety = QPushButton("Git Safety")
        self.btn_git_safety.setObjectName("btn_copy")
        self.btn_git_safety.setToolTip("Копирует Git Safety Report: branch, rebase, detached HEAD, diverged, dirty state.")
        self.btn_git_safety.clicked.connect(self.copy_git_safety_report)
        advanced_layout.addWidget(self.btn_git_safety)

        self.btn_project_profile = QPushButton("Project Profile")
        self.btn_project_profile.setObjectName("btn_copy")
        self.btn_project_profile.setToolTip("Создаёт/обновляет .ai_patcher/project_profile.json для текущего проекта.")
        self.btn_project_profile.clicked.connect(self.save_current_project_profile)
        advanced_layout.addWidget(self.btn_project_profile)

        self.btn_gpt_handoff = QPushButton("GPT handoff")
        self.btn_gpt_handoff.setObjectName("btn_copy")
        self.btn_gpt_handoff.setToolTip("Копирует стартовый пакет для продолжения работы с GPT.")
        self.btn_gpt_handoff.clicked.connect(self.copy_gpt_handoff)
        advanced_layout.addWidget(self.btn_gpt_handoff)

        self.check_profile_menu = QComboBox()
        self.check_profile_menu.setToolTip("Профиль проверок из .ai_patcher/project_profile.json или авто-профиля проекта.")
        advanced_layout.addWidget(self.check_profile_menu)
        self._refresh_check_profiles()

        self.btn_run_check_profile = QPushButton("Запустить проверку")
        self.btn_run_check_profile.setObjectName("btn_primary")
        self.btn_run_check_profile.setToolTip("Запускает выбранный набор проверочных команд.")
        self.btn_run_check_profile.clicked.connect(self.run_selected_check_profile)
        advanced_layout.addWidget(self.btn_run_check_profile)

        side_layout.addWidget(self.advanced_tools_frame)

        self.btn_apply = QPushButton("ПРИМЕНИТЬ ПАТЧ")
        self.btn_apply.setObjectName("btn_success")
        self.btn_apply.setMinimumHeight(50)
        self.btn_apply.setEnabled(False)
        self.btn_apply.setToolTip("Сначала выполните анализ. После успешного применения повторный запуск блокируется.")
        self.btn_apply.clicked.connect(self.apply_patch)
        side_layout.addWidget(self.btn_apply)

        splitter.addWidget(sidebar)

        # ════════════════ MAIN AREA ════════════════
        main_splitter = QSplitter(Qt.Orientation.Vertical)

        # Верхняя часть: карточки операций
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        top_bar = QHBoxLayout()
        self.lbl_status = QLabel("Статус: Ожидание")
        self.lbl_status.setObjectName("status_warning")
        top_bar.addWidget(self.lbl_status)

        top_bar.addStretch()

        self.sort_menu = QComboBox()
        self.sort_menu.addItems(["По умолчанию", "По файлам", "Сначала ошибки"])
        self.sort_menu.currentTextChanged.connect(self.apply_sorting)
        top_bar.addWidget(QLabel("Сортировка:"))
        top_bar.addWidget(self.sort_menu)

        right_layout.addLayout(top_bar)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        right_layout.addWidget(self.progress_bar)

        self.lbl_progress_text = QLabel("0 / 0")
        self.lbl_progress_text.setStyleSheet("color: #888; font-size: 11px;")
        right_layout.addWidget(self.lbl_progress_text)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("scroll_area")
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self.scroll_content)
        right_layout.addWidget(scroll, 1)

        main_splitter.addWidget(right_panel)

        # Нижняя часть: лог команд
        self.cmd_log_frame = QFrame()
        self.cmd_log_frame.setObjectName("cmd_log_frame")
        cmd_log_layout = QVBoxLayout(self.cmd_log_frame)
        cmd_log_layout.setContentsMargins(10, 8, 10, 8)

        log_header = QHBoxLayout()
        lbl_cmd = QLabel("Выполнение команд")
        lbl_cmd.setStyleSheet(
            "color: #00bcd4; font-size: 13px; font-weight: bold;"
        )
        log_header.addWidget(lbl_cmd)
        log_header.addStretch()

        self.btn_copy_cmd_log = QPushButton("Копировать лог")
        self.btn_copy_cmd_log.setObjectName("btn_copy")
        self.btn_copy_cmd_log.clicked.connect(self.copy_command_log)
        log_header.addWidget(self.btn_copy_cmd_log)

        cmd_log_layout.addLayout(log_header)

        self.cmd_log_text = QTextEdit()
        self.cmd_log_text.setReadOnly(True)
        self.cmd_log_text.setMaximumHeight(200)
        cmd_log_layout.addWidget(self.cmd_log_text)

        self.cmd_log_frame.setVisible(False)
        main_splitter.addWidget(self.cmd_log_frame)
        main_splitter.setSizes([600, 200])

        # Activity log panel (hidden by default)
        self.activity_log_frame = QFrame()
        self.activity_log_frame.setObjectName("activity_log_frame")
        activity_layout = QVBoxLayout(self.activity_log_frame)
        activity_layout.setContentsMargins(10, 8, 10, 8)

        log_header = QHBoxLayout()
        lbl_log = QLabel("Детальный лог")
        lbl_log.setStyleSheet(
            "color: #00bcd4; font-size: 13px; font-weight: bold;"
        )
        log_header.addWidget(lbl_log)
        log_header.addStretch()

        self.btn_clear_log = QPushButton("Очистить")
        self.btn_clear_log.setObjectName("btn_toggle_log")
        self.btn_clear_log.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_log.setFixedWidth(80)
        self.btn_clear_log.clicked.connect(self._clear_log)
        log_header.addWidget(self.btn_clear_log)
        activity_layout.addLayout(log_header)

        self.activity_log = QTextEdit()
        self.activity_log.setReadOnly(True)
        self.activity_log.setMaximumHeight(160)
        activity_layout.addWidget(self.activity_log)
        self.activity_log_frame.setVisible(False)
        main_splitter.addWidget(self.activity_log_frame)

        # Scanner tab
        self.scanner_tab = ScannerTab()
        self.scanner_tab.set_workspace(self.workspace)
        self.scanner_tab.setVisible(False)

        # Центральная область теперь не добавляет патчер и сканер рядом друг с другом.
        # Раньше scanner_tab был третьим виджетом в горизонтальном splitter:
        # при переключении он сжимал/растягивал layout, из-за чего окно съезжало вниз.
        # QStackedWidget держит патчер и сканер в одном и том же месте.
        self.patch_view = main_splitter
        self.content_stack = QStackedWidget()
        self.content_stack.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.content_stack.addWidget(self.patch_view)

        self.scanner_tab = ScannerTab()
        self.scanner_tab.set_workspace(self.workspace)
        self.content_stack.addWidget(self.scanner_tab)

        splitter.addWidget(self.content_stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([340, 840])

        self._set_pipeline_phase("parse")

    # ─────────────────── UI Navigation ───────────────────

    def _switch_tab(self, tab: str) -> None:
        """Переключает между патчером и сканером без перестройки размеров окна."""
        if tab == "patch":
            self.content_stack.setCurrentWidget(self.patch_view)
            self.btn_patch_tab.setObjectName("btn_toggle_active")
            self.btn_scan_tab.setObjectName("btn_toggle_log")
        else:
            self.scanner_tab.set_workspace(self.workspace)
            self.content_stack.setCurrentWidget(self.scanner_tab)
            self.btn_patch_tab.setObjectName("btn_toggle_log")
            self.btn_scan_tab.setObjectName("btn_toggle_active")

        self.btn_patch_tab.style().unpolish(self.btn_patch_tab)
        self.btn_patch_tab.style().polish(self.btn_patch_tab)
        self.btn_scan_tab.style().unpolish(self.btn_scan_tab)
        self.btn_scan_tab.style().polish(self.btn_scan_tab)

    def select_workspace(self) -> None:
        """Выбор рабочей директории."""
        directory = QFileDialog.getExistingDirectory(
            self, "Выберите папку проекта", self.workspace
        )
        if directory:
            self.workspace = directory
            self.lbl_workspace.setText(f"Папка: {os.path.basename(directory)}")
            self.backup_mgr = BackupManager(self.workspace)
            self.backup_mgr.init_backup_dir()
            self.scanner_tab.set_workspace(self.workspace)
            self._log("parse", f"Рабочая папка: {directory}")
            self._refresh_check_profiles()

    def _toggle_log(self) -> None:
        """Показывает/скрывает детальный лог."""
        visible = not self.activity_log_frame.isVisible()
        self.activity_log_frame.setVisible(visible)
        self.btn_log_toggle.setText("Скрыть" if visible else "Лог")


    def _toggle_advanced_tools(self) -> None:
        """Показывает/скрывает вторичные инструменты сайдбара."""
        # isVisible() зависит от видимости родительского окна, поэтому в тестах
        # и при не показанном top-level окне он может всегда возвращать False.
        # Для логики раскрытия блока нужен именно локальный hidden-state.
        visible = self.advanced_tools_frame.isHidden()
        self.advanced_tools_frame.setHidden(not visible)
        self.btn_more_tools.setText("Доп. инструменты ▲" if visible else "Доп. инструменты ▼")

    def _clear_log(self) -> None:
        """Очищает детальный лог."""
        self.activity_log.clear()

    # ─────────────────── Pipeline & Logging ───────────────────

    def _set_pipeline_phase(self, phase: str) -> None:
        """Обновляет визуальный индикатор пайплайна."""
        self._current_phase = phase
        phase_order = [p[0] for p in PHASES]
        current_idx = phase_order.index(phase) if phase in phase_order else -1

        for idx, (phase_id, phase_name) in enumerate(PHASES):
            dot = self.phase_dots[phase_id]
            lbl = self.phase_labels[phase_id]

            if idx < current_idx:
                color = PIPELINE_COLORS["completed"]
                dot.setText("✓")
                lbl.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: bold;")
            elif idx == current_idx:
                color = PIPELINE_COLORS["active"]
                dot.setText("●")
                lbl.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: bold;")
            else:
                color = PIPELINE_COLORS["inactive"]
                dot.setText("●")
                lbl.setStyleSheet("color: #777; font-size: 11px;")

            dot.setStyleSheet(f"color: {color}; font-size: 16px;")

    def _log(self, stage: str, message: str, detail: str = "") -> None:
        """Добавляет запись в детальный лог."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        icons = {
            "parse": "🔍",
            "load": "📂",
            "search": "🔎",
            "apply": "⚙️",
            "diff": "📝",
            "cmd": "💻",
            "cmd_stdout": "▶",
            "cmd_stderr": "⚠",
            "done": "✅",
            "error": "❌",
        }
        icon = icons.get(stage, "•")
        line = f"[{timestamp}] {icon} {message}"
        if detail:
            line += f"\n    {detail}"
        self.activity_log.append(line)

    def _show_summary(self, text: str, color: str = "#00bcd4") -> None:
        """Показывает сводный баннер."""
        self.lbl_summary.setText(text)
        self.summary_frame.setVisible(True)
        self.summary_frame.setStyleSheet(
            f"#summary_frame {{ background-color: {color}22; "
            f"border: 1px solid {color}44; "
            f"border-radius: 6px; }}"
        )

    def _hide_summary(self) -> None:
        """Скрывает сводный баннер."""
        self.summary_frame.setVisible(False)


    def _has_only_commands(self) -> bool:
        """True если текущий патч не содержит файловых операций, но содержит команды."""
        return (
            not self.raw_operations
            and bool(self.commands_after_analysis or self.commands_after_apply)
        )

    def _reset_main_action_button(self) -> None:
        """Возвращает главную кнопку в обычный режим ожидания патча."""
        self.btn_apply.setText("ПРИМЕНИТЬ ПАТЧ")
        self.btn_apply.setEnabled(False)

    def _set_command_only_ready(self) -> None:
        """Динамически превращает главную кнопку в кнопку запуска команд."""
        self.lbl_status.setText("Готово к выполнению команд")
        self.lbl_status.setObjectName("status_success")
        self.btn_apply.setText("Выполнить команды")
        self.btn_apply.setEnabled(True)
        self.lbl_status.style().unpolish(self.lbl_status)
        self.lbl_status.style().polish(self.lbl_status)

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
        self._patch_written = False
        self._is_applying = False

        self._current_patch_fingerprint = ""
        self._current_patch_registry_match = None

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

        self.btn_apply.setText("ПРИМЕНИТЬ ПАТЧ")
        self.btn_apply.setEnabled(False)
        self.btn_analyze.setEnabled(True)
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

        self._hide_summary()
        self._clear_log()
        self._set_pipeline_phase("parse")

    def _build_ai_report(self, note: str = "") -> str:
        """Создаёт полный текстовый отчёт для GPT без скриншотов."""
        return build_ai_patch_report(
            patch_name=self.patch_name,
            workspace=self.workspace,
            processed_operations=self.processed_operations,
            command_results=self.command_results,
            raw_operations=self.raw_operations,
            current_phase=self._current_phase,
            patch_written=self._patch_written,
            note=note,
        )

    def copy_ai_report(self) -> None:
        """Копирует полный AI-friendly отчёт в буфер обмена."""
        report = self._build_ai_report()
        QApplication.clipboard().setText(report)
        QMessageBox.information(
            self,
            "Отчёт скопирован",
            "Полный текстовый отчёт для GPT скопирован. Его можно отправлять вместо скриншотов.",
        )

    def save_ai_report_to_file(self) -> None:
        """Сохраняет полный AI-friendly отчёт в PATCH_RESULT.md."""
        path = os.path.join(self.workspace, "PATCH_RESULT.md")
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(self._build_ai_report())
            QMessageBox.information(
                self,
                "PATCH_RESULT.md сохранён",
                f"Отчёт сохранён:\n{path}",
            )
        except OSError as e:
            QMessageBox.critical(
                self,
                "Ошибка сохранения",
                f"Не удалось сохранить PATCH_RESULT.md:\n{e}",
            )

    def copy_error_report(self) -> None:
        """Совместимость со старым действием: теперь копирует полный отчёт."""
        self.copy_ai_report()


    def _refresh_check_profiles(self) -> None:
        """Обновляет список профилей проверок."""
        if not hasattr(self, "check_profile_menu"):
            return
        current = self.check_profile_menu.currentText()
        self.check_profile_menu.clear()
        profiles = get_check_profiles(self.workspace)
        for name in profiles.keys():
            self.check_profile_menu.addItem(name)
        if current:
            index = self.check_profile_menu.findText(current)
            if index >= 0:
                self.check_profile_menu.setCurrentIndex(index)

    def show_workflow_assistant(self) -> None:
        """Копирует и показывает Workflow Assistant отчёт."""
        report = workflow_status_report(
            self.workspace,
            self.patch_name,
            self.raw_operations,
            self.processed_operations,
            self.command_results,
            self._patch_written,
        )
        QApplication.clipboard().setText(report)
        self.txt_json.setPlainText(report)
        QMessageBox.information(
            self,
            "Workflow Assistant",
            "Отчёт о текущем состоянии и следующем безопасном шаге скопирован в буфер обмена.",
        )

    def copy_git_safety_report(self) -> None:
        """Копирует Git Safety Report."""
        report = format_git_safety_report(self.workspace)
        QApplication.clipboard().setText(report)
        self.txt_json.setPlainText(report)
        QMessageBox.information(
            self,
            "Git Safety",
            "Git Safety Report скопирован в буфер обмена.",
        )

    def save_current_project_profile(self) -> None:
        """Создаёт или обновляет профиль проекта."""
        try:
            path = save_project_profile(self.workspace)
            self._refresh_check_profiles()
            QMessageBox.information(
                self,
                "Project Profile",
                f"Профиль проекта сохранён:\n{path}",
            )
        except OSError as e:
            QMessageBox.critical(
                self,
                "Project Profile error",
                f"Не удалось сохранить профиль проекта:\n{e}",
            )

    def copy_gpt_handoff(self) -> None:
        """Копирует handoff-пакет для GPT."""
        report = gpt_handoff_text(self.workspace)
        QApplication.clipboard().setText(report)
        self.txt_json.setPlainText(report)
        QMessageBox.information(
            self,
            "GPT handoff",
            "GPT handoff скопирован в буфер обмена.",
        )

    def run_selected_check_profile(self) -> None:
        """Запускает выбранный профиль проверок как команды."""
        profile_name = self.check_profile_menu.currentText() if hasattr(self, "check_profile_menu") else ""
        if not profile_name:
            QMessageBox.information(self, "Проверка", "Нет доступных профилей проверок.")
            return
        commands = get_check_commands(self.workspace, profile_name)
        if not commands:
            QMessageBox.information(self, "Проверка", f"Профиль `{profile_name}` пуст.")
            return
        self._propose_commands(commands, f"check:{profile_name}")

    def action_copy(self, op_dict: dict) -> None:
        """Копирует JSON операции в буфер обмена."""
        QApplication.clipboard().setText(
            json.dumps(op_dict, indent=2, ensure_ascii=False)
        )
        QMessageBox.information(self, "Скопировано", "JSON блока скопирован.")

    # ─────────────────── Парсинг и анализ ───────────────────

    def parse_and_analyze(self) -> None:
        """Парсит JSON из текстового поля и запускает анализ."""
        self._patch_written = False
        self._is_applying = False
        self._current_patch_fingerprint = ""
        self._current_patch_registry_match = None
        self._set_pipeline_phase("parse")
        self._hide_summary()
        self._log("parse", "Парсинг JSON из текстового поля...")

        try:
            data = extract_all_json(self.txt_json.toPlainText().strip())
            self.patch_name = data["patch_name"]
            self.raw_operations = [
                {"id": i, "op": op} for i, op in enumerate(data["operations"])
            ]

            all_commands = data.get("commands", [])
            self.commands_after_analysis = [
                c for c in all_commands if c.get("run") == "after_analysis"
            ]
            self.commands_after_apply = [
                c for c in all_commands if c.get("run") == "after_apply"
            ]
            self.command_results.clear()

            normalized_for_hash = self.commands_after_analysis + self.commands_after_apply
            self._current_patch_fingerprint = patch_fingerprint(
                self.patch_name,
                self.raw_operations,
                normalized_for_hash,
            )
            self._current_patch_registry_match = find_applied_patch(
                self.workspace,
                self._current_patch_fingerprint,
            )

            if self._current_patch_registry_match:
                applied_at = self._current_patch_registry_match.get(
                    "applied_at",
                    "unknown time",
                )
                self._show_summary(
                    f"Внимание: этот патч уже применялся {applied_at}. "
                    "Повторное применение будет заблокировано.",
                    "#f39c12",
                )

            rule_warnings = project_rule_warnings(self.workspace, self.raw_operations)
            for warning in rule_warnings:
                self._log("error", "Project rule warning", warning)

            self._log(
                "parse",
                f"Найдено: {len(self.raw_operations)} операций, "
                f"{len(all_commands)} команд",
                f"Патч: {self.patch_name}",
            )

        except (ValueError, json.JSONDecodeError) as e:
            raw_text = self.txt_json.toPlainText().strip()
            details = [
                "# Ошибка парсинга AI Patcher Pro",
                "",
                "Инструмент не смог найти валидный JSON-патч в тексте.",
                "",
                "## Что нужно прислать GPT",
                "Попроси GPT вернуть только JSON-патч без пояснений, либо fenced-блок ~~~json с объектом/массивом операций.",
                "",
                "## Ошибка",
                str(e),
                "",
                "## Начало полученного текста",
                "~~~text",
                raw_text[:4000] if raw_text else "(пустой ввод)",
                "~~~",
            ]
            report = chr(10).join(details)
            QApplication.clipboard().setText(report)

            self._log("parse", f"Ошибка парсинга: {e}")
            self._stop_pulse(success=False)
            self._set_pipeline_phase("parse")
            self._show_summary(
                "JSON не найден. Текстовый отчёт об ошибке скопирован для GPT.",
                "#c0392b",
            )
            QMessageBox.critical(
                self,
                "Ошибка парсинга",
                "JSON-патч не найден или повреждён."
                + chr(10)
                + chr(10)
                + "Я скопировал подробный текстовый отчёт в буфер обмена — "
                + "отправь его GPT вместо скриншота.",
            )
            return

        self.processed_operations.clear()
        self.memory_files.clear()

        # Command-only patch: операций с файлами нет, но есть команды.
        # Раньше такие патчи зависели от пустого ProcessorThread и/или не давали
        # нормально дойти до after_apply. Теперь это отдельный явный сценарий.
        if not self.raw_operations:
            self.progress_bar.setMaximum(0)
            self.progress_bar.setValue(0)
            self.lbl_progress_text.setText("0 / 0")
            self.btn_analyze.setEnabled(True)

            total_commands = len(self.commands_after_analysis) + len(self.commands_after_apply)
            self._log(
                "parse",
                f"Command-only патч: файловых операций нет, команд: {total_commands}",
            )

            self._show_summary(
                f"Command-only патч: файловых операций нет, команд: {total_commands}",
                "#00bcd4",
            )

            if self.commands_after_analysis:
                self._propose_commands(
                    self.commands_after_analysis,
                    "after_analysis",
                )
            elif self.commands_after_apply:
                self._set_command_only_ready()
                self._set_pipeline_phase("analysis")
                self._stop_pulse(success=True)
            else:
                self.lbl_status.setText("Нет операций и команд")
                self.lbl_status.setObjectName("status_warning")
                self._reset_main_action_button()
                self._set_pipeline_phase("done")
                self._stop_pulse(success=True)

            self.lbl_status.style().unpolish(self.lbl_status)
            self.lbl_status.style().polish(self.lbl_status)
            return

        self._start_processing(self.raw_operations)

    def recalculate_file(self, filepath: str) -> None:
        """Пересчитывает операции для конкретного файла."""
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

    def _start_processing(self, ops: list, is_recalc: bool = False) -> None:
        """Запускает фоновую обработку операций."""
        if not is_recalc:
            self.processed_operations.clear()
            self.memory_files.clear()
            self.progress_bar.setMaximum(len(ops))
            self.progress_bar.setValue(0)
            self.lbl_progress_text.setText(f"0 / {len(ops)}")
            self._set_pipeline_phase("analysis")
            self._start_pulse("Анализ операций...")

            while self.scroll_layout.count():
                child = self.scroll_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

        self.btn_analyze.setEnabled(False)
        self.btn_apply.setEnabled(False)

        self.worker = ProcessorThread(self.workspace, ops, self.memory_files)
        self.worker.status_update.connect(self._on_status_update)
        self.worker.operation_done.connect(self._on_operation_done)
        self.worker.finished_all.connect(self._on_all_operations_done)
        self.worker.start()

    def _on_status_update(self, stage: str, message: str, detail: str) -> None:
        """Обновляет UI при промежуточном статусе."""
        self._log(stage, message, detail)
        if stage == "search":
            self._start_pulse("Поиск кода...")
        elif stage == "diff":
            self._start_pulse("Генерация diff...")

    def _on_operation_done(self, res: dict) -> None:
        """Обрабатывает результат одной операции."""
        self.processed_operations.append(res)
        self.progress_bar.setValue(len(self.processed_operations))
        self.lbl_progress_text.setText(
            f"{len(self.processed_operations)} / {len(self.raw_operations)}"
        )

        status = res["status"]
        op = res["op"]
        file_path = op.get("path") or op.get("file", "?")
        action = op.get("action") or op.get("op", "?")

        if status == "success":
            self._log("done", f"Найдено: {action} → {file_path}", res.get("search_method", ""))
        elif status == "already_applied":
            self._log("done", f"Уже применено: {file_path}", res.get("error", ""))
        else:
            self._log("error", f"Ошибка: {file_path}", res.get("error", ""))

        self.scroll_layout.addWidget(OperationCard(res, self))

    def _on_all_operations_done(self, cache: dict) -> None:
        """Обрабатывает завершение всех операций."""
        self.memory_files = cache
        self.btn_analyze.setEnabled(True)

        # Считаем результаты анализа
        total = len(self.processed_operations)
        found = sum(1 for op in self.processed_operations if op["status"] == "success")
        already = sum(1 for op in self.processed_operations if op["status"] == "already_applied")
        errors = sum(1 for op in self.processed_operations if op["status"] == "error")

        if errors > 0:
            self._show_summary(
                f"Анализ: {found} найдено, {already} уже было, {errors} ошибок",
                "#c0392b"
            )
            self._set_pipeline_phase("analysis")
            self._stop_pulse(success=False)
        else:
            self._show_summary(
                f"Анализ: {found} найдено, {already} уже было",
                "#00bcd4"
            )
            self._stop_pulse(success=True)

        # Если есть команды after_analysis — предлагаем выполнить
        if self.commands_after_analysis:
            self._propose_commands(
                self.commands_after_analysis,
                "after_analysis",
            )

        self._check_ready_status()

    # ─────────────────── Применение патча ───────────────────

    def apply_patch(self) -> None:
        """Применяет все успешные операции патча — запись файлов на диск."""
        if self._is_applying:
            self._log("done", "Применение уже выполняется. Повторный клик проигнорирован.")
            self._show_summary(
                "Применение уже выполняется. Повторный клик проигнорирован.",
                "#f39c12",
            )
            return

        if self._patch_written:
            self.btn_apply.setEnabled(False)
            self.btn_apply.setText("Команды выполнены" if self._has_only_commands() else "Патч уже применён")
            self._log("done", "Этот сценарий уже выполнен. Повторный запуск заблокирован.")
            self._show_summary(
                "Этот сценарий уже выполнен. Повторный запуск заблокирован.",
                "#f39c12",
            )
            return


        if self._current_patch_registry_match:
            applied_at = self._current_patch_registry_match.get("applied_at", "unknown time")
            self.btn_apply.setEnabled(False)
            self.btn_apply.setText("Уже применялся")
            self._log("done", "Patch Registry: повторное применение заблокировано.")
            self._show_summary(
                f"Patch Registry: этот патч уже применялся {applied_at}. Повторное применение заблокировано.",
                "#f39c12",
            )
            return

        self._is_applying = True
        self.btn_apply.setEnabled(False)
        self.btn_apply.setText("Применяется...")
        self.btn_analyze.setEnabled(False)
        QApplication.processEvents()

        self._set_pipeline_phase("write")
        self._log("apply", "Запись файлов на диск...")

        try:
            written_count = 0

            if not self.memory_files and not self.raw_operations:
                # Command-only патч: файловых операций нет, но after_apply-команды есть.
                self._log("done", "Файловых операций нет — выполняются только команды.")
            else:
                # Создаём бэкап только перед реальной записью файлов.
                self.backup_mgr.create_backup(self.patch_name, self.memory_files)

                for abs_p, content in self.memory_files.items():
                    os.makedirs(os.path.dirname(abs_p), exist_ok=True)
                    with open(abs_p, "w", encoding="utf-8") as f:
                        f.write(content)
                    written_count += 1

            # ── Обновляем статусы карточек: success → applied ──
            self._patch_written = True
            self._is_applying = False
            self.btn_analyze.setEnabled(True)
            self.btn_apply.setEnabled(False)
            self.btn_apply.setText("Команды выполнены" if self._has_only_commands() else "Патч уже применён")

            for op in self.processed_operations:
                if op["status"] == "success":
                    op["status"] = "applied"

            # Перерисовываем карточки
            self.apply_sorting()

            # Считаем результаты
            applied = sum(1 for op in self.processed_operations if op["status"] == "applied")
            already = sum(1 for op in self.processed_operations if op["status"] == "already_applied")
            errors = sum(1 for op in self.processed_operations if op["status"] == "error")

            if self._has_only_commands():
                self._log("done", "Командный сценарий подготовлен к выполнению.")
            else:
                self._log("done", f"Патч применён! Файлов записано: {written_count}")

            changed_files = []
            for item in self.raw_operations:
                op = item.get("op", {})
                path = op.get("path") or op.get("file")
                if path:
                    changed_files.append(path)
            if self._current_patch_fingerprint:
                mark_patch_applied(
                    self.workspace,
                    self._current_patch_fingerprint,
                    self.patch_name,
                    changed_files,
                    f"written_count={written_count}",
                )

            if self._has_only_commands():
                self._show_summary(
                    "Файловых операций нет. Выполняются команды.",
                    "#00bcd4",
                )
                self.lbl_status.setText("Выполняются команды")
            else:
                self._show_summary(
                    f"Код применён: {applied} файлов изменено, {already} без изменений, {errors} ошибок",
                    "#27ae60" if errors == 0 else "#f39c12"
                )
                self.lbl_status.setText("Патч применён")
            self.lbl_status.setObjectName("status_success")
            self.lbl_status.style().unpolish(self.lbl_status)
            self.lbl_status.style().polish(self.lbl_status)

            # Если есть команды after_apply — показываем диалог
            if self.commands_after_apply:
                self._propose_commands(
                    self.commands_after_apply,
                    "after_apply",
                )
            else:
                self._set_pipeline_phase("done")
                self._stop_pulse(success=True)
                self._show_final_summary()

        except (OSError, IOError) as e:
            self._is_applying = False
            self.btn_analyze.setEnabled(True)
            if not self._patch_written:
                self.btn_apply.setEnabled(True)
                self.btn_apply.setText("Повторить применение")

            self._log("cmd_stderr", f"Ошибка записи: {e}")
            self._stop_pulse(success=False)
            self._set_pipeline_phase("write")
            self._show_summary(f"Ошибка записи файлов: {e}", "#c0392b")
            QMessageBox.critical(
                self, "Ошибка записи", f"Не удалось записать файлы:\n{e}"
            )

    # ─────────────────── Выполнение команд ───────────────────

    def _propose_commands(self, commands: list, phase: str) -> None:
        """Предлагает выполнить команды с подтверждением."""
        if not commands:
            return

        self._current_cmd_phase = phase

        msg_lines = [f"Выполнить команды {phase}?"]
        msg_lines.append("")
        for i, cmd_info in enumerate(commands, 1):
            cmd = cmd_info.get("cmd", "")
            desc = cmd_info.get("description", "")
            warnings = cmd_info.get("warnings", [])
            msg_lines.append(f"{i}. {cmd}")
            if desc:
                msg_lines.append(f"   {desc}")
            if warnings:
                msg_lines.append("   ⚠ " + "; ".join(warnings))

        reply = QMessageBox.question(
            self,
            "Выполнение команд",
            "\n".join(msg_lines),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self._execute_commands(commands, phase)
        else:
            self._log("cmd", f"Команды {phase} отменены пользователем")
            if phase == "after_apply" and self._patch_written:
                self._set_pipeline_phase("done")
                self._show_final_summary()

    def _execute_commands(self, commands: list, phase: str) -> None:
        """Запускает выполнение команд."""
        self._set_pipeline_phase("commands")
        self._start_pulse(f"Выполнение команд {phase}...")
        self.cmd_log_frame.setVisible(True)
        self.cmd_log_text.clear()
        self.btn_analyze.setEnabled(False)
        self.btn_apply.setEnabled(False)

        self.cmd_log_text.append(f"=== Выполнение команд {phase} ===\n")
        self._log("cmd", f"Запуск {len(commands)} команд ({phase})")

        self.cmd_worker = CommandExecutorThread(commands, self.workspace)
        self.cmd_worker.command_started.connect(self._on_command_started)
        self.cmd_worker.command_output.connect(self._on_command_output)
        self.cmd_worker.command_done.connect(self._on_command_done)
        self.cmd_worker.finished_all.connect(self._on_commands_finished)
        self.cmd_worker.start()

    def _on_command_started(self, index: int, cmd: str, description: str) -> None:
        """Команда начала выполняться."""
        self.cmd_log_text.append(f"\n[{index + 1}] $ {cmd}")
        if description:
            self.cmd_log_text.append(f"    {description}")
        self._log("cmd", f"Запуск: {cmd}", description)

    def _on_command_output(self, index: int, stream_type: str, data: str) -> None:
        """Получен потоковый вывод команды."""
        prefix = "" if stream_type == "stdout" else "[stderr] "
        self.cmd_log_text.moveCursor(self.cmd_log_text.textCursor().MoveOperation.End)
        self.cmd_log_text.insertPlainText(prefix + data)
        self.cmd_log_text.moveCursor(self.cmd_log_text.textCursor().MoveOperation.End)

        # Логируем только stderr или важные строки stdout, чтобы не засорять
        if stream_type == "stderr":
            self._log("cmd_stderr", data.strip())

    def _on_command_done(self, result: dict) -> None:
        """Команда завершилась."""
        self.command_results.append(result)
        status = result.get("status", "unknown")
        returncode = result.get("returncode", -1)
        cmd = result.get("cmd", "")

        if status == "success":
            self.cmd_log_text.append(f"\n✓ Завершено успешно (код {returncode})\n")
            self._log("done", f"Команда успешна: {cmd}")
        else:
            self.cmd_log_text.append(f"\n✗ Ошибка (код {returncode})\n")
            self._log("error", f"Команда завершилась ошибкой: {cmd}", result.get("stderr", ""))

        self._check_ready_status()

    def _on_commands_finished(self) -> None:
        """Все команды завершены."""
        self.btn_analyze.setEnabled(True)
        QApplication.restoreOverrideCursor()

        has_cmd_errors = any(
            r.get("status") == "error"
            for r in self.command_results
        )

        self._set_pipeline_phase("done")
        self._stop_pulse(success=not has_cmd_errors)
        self._show_final_summary()

        # Обновляем статус главной кнопки.
        # Для command-only сценария она временно была "Выполнить команды";
        # после завершения возвращаем обычный вид, чтобы UI не залипал.
        self._reset_main_action_button()

        self._log(
            "done",
            f"Все команды выполнены. Успешно: "
            f"{sum(1 for r in self.command_results if r.get('status') == 'success')}, "
            f"Ошибки: {sum(1 for r in self.command_results if r.get('status') == 'error')}"
        )

    def _show_final_summary(self) -> None:
        """Показывает итоговую сводку."""
        applied = sum(1 for op in self.processed_operations if op["status"] == "applied")
        already = sum(1 for op in self.processed_operations if op["status"] == "already_applied")
        errors = sum(1 for op in self.processed_operations if op["status"] == "error")
        cmd_ok = sum(1 for r in self.command_results if r.get("status") == "success")
        cmd_err = sum(1 for r in self.command_results if r.get("status") == "error")

        parts = []
        if applied:
            parts.append(f"{applied} применено")
        if already:
            parts.append(f"{already} уже было")
        if errors:
            parts.append(f"{errors} ошибок")
        if self.command_results:
            parts.append(f"команды: {cmd_ok} OK, {cmd_err} ошибок")

        text = "Готово: " + ", ".join(parts) if parts else "Готово"
        color = "#27ae60" if errors == 0 and cmd_err == 0 else "#f39c12"
        self._show_summary(text, color)

    def copy_command_log(self) -> None:
        """Копирует лог команд в буфер обмена."""
        if not self.command_results:
            QMessageBox.information(self, "Лог", "Команды ещё не выполнялись.")
            return

        lines = ["=== Лог выполнения команд ===\n"]
        for i, result in enumerate(self.command_results, 1):
            lines.append(f"--- Команда {i}: {result.get('cmd', '')} ---")
            lines.append(f"Описание: {result.get('description', '')}")
            lines.append(f"Статус: {result.get('status', '')}")
            lines.append(f"Код возврата: {result.get('returncode', '')}")
            stdout = result.get("stdout", "")
            stderr = result.get("stderr", "")
            if stdout:
                lines.append(f"stdout:\n{stdout}")
            if stderr:
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
        has_errors = any(
            op["status"] == "error" for op in self.processed_operations
        )
        has_cmd_errors = any(
            r.get("status") == "error"
            for r in self.command_results
        )

        if not has_errors and not has_cmd_errors and self.processed_operations and not self._patch_written:
            self.lbl_status.setText("Готово к применению")
            self.lbl_status.setObjectName("status_success")
            self.btn_apply.setText("ПРИМЕНИТЬ ПАТЧ")
            self.btn_apply.setEnabled(True)

            if self._current_patch_registry_match:
                self.lbl_status.setText("Патч уже применялся")
                self.lbl_status.setObjectName("status_warning")
                self.btn_apply.setText("Уже применялся")
                self.btn_apply.setEnabled(False)
        elif not self.processed_operations:
            if self.commands_after_apply and not self.raw_operations and not self._patch_written:
                self._set_command_only_ready()
            else:
                self.lbl_status.setText("Статус: Ожидание")
                self.lbl_status.setObjectName("status_warning")
                self.btn_apply.setText("ПРИМЕНИТЬ ПАТЧ")
                self.btn_apply.setEnabled(False)
        elif self._patch_written:
            self.lbl_status.setText("Патч применён")
            self.lbl_status.setObjectName("status_success")
            self.btn_apply.setText("Патч уже применён")
            self.btn_apply.setEnabled(False)
        else:
            self.lbl_status.setText("Есть ошибки")
            self.lbl_status.setObjectName("status_error")
            self.btn_apply.setText("Исправьте ошибки")
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

        if target_processed["status"] not in ("success", "applied"):
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
        editor = QTextEdit()
        editor.setPlainText(json.dumps(target_raw["op"], indent=2, ensure_ascii=False))
        layout.addWidget(editor)

        btn_box = QHBoxLayout()
        btn_save = QPushButton("Сохранить")
        btn_cancel = QPushButton("Отмена")
        btn_box.addStretch()
        btn_box.addWidget(btn_save)
        btn_box.addWidget(btn_cancel)
        layout.addLayout(btn_box)

        btn_cancel.clicked.connect(dialog.reject)

        def save_edit():
            try:
                new_op = json.loads(editor.toPlainText())
                target_raw["op"] = new_op
                dialog.accept()

                filepath = new_op.get("path") or new_op.get("file", "unknown")
                self.recalculate_file(filepath)
            except json.JSONDecodeError as e:
                QMessageBox.critical(dialog, "Ошибка JSON", str(e))

        btn_save.clicked.connect(save_edit)
        dialog.exec()

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
