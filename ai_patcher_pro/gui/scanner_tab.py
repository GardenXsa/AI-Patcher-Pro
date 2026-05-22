"""
Вкладка сканера проекта.

Полнофункциональный интерфейс:
- Выбор папки и сканирование
- Фильтры: расширения, языки, размер, regex, .gitignore
- Пользовательские исключения (glob и директории)
- Дерево файлов с чекбоксами
- Нумерация строк в контексте
- Выбор файлов для включения
- Оценка токенов в реальном времени
- Генерация и копирование контекста
"""

import os

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QLabel,
    QProgressBar,
    QCheckBox,
    QTreeWidget,
    QTreeWidgetItem,
    QFileDialog,
    QSplitter,
    QApplication,
    QGroupBox,
    QLineEdit,
    QSpinBox,
    QComboBox,
    QListWidget,
    QListWidgetItem,
    QTabWidget,
    QMessageBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from ai_patcher_pro.core.scanner import (
    ScannerEngine,
    ScanResult,
    ScanFilter,
    ContextOptions,
    LANG_CATEGORIES,
)


class ScannerThread(QThread):
    """Фоновый поток для сканирования проекта."""

    scan_done = pyqtSignal(object)

    def __init__(self, engine: ScannerEngine, root_path: str, scan_filter: ScanFilter):
        super().__init__()
        self.engine = engine
        self.root_path = root_path
        self.scan_filter = scan_filter

    def run(self) -> None:
        result = self.engine.scan(self.root_path, self.scan_filter)
        self.scan_done.emit(result)


class ScannerTab(QWidget):
    """
    Полнофункциональная вкладка сканера проекта.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._engine = ScannerEngine()
        self._scan_result: ScanResult | None = None
        self._scan_path = ""
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # ── Верхняя панель: выбор папки ──
        top_bar = QHBoxLayout()

        self.btn_select_folder = QPushButton("Выбрать папку проекта")
        self.btn_select_folder.setObjectName("btn_workspace")
        self.btn_select_folder.setMinimumHeight(35)
        self.btn_select_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_select_folder.clicked.connect(self._select_folder)
        top_bar.addWidget(self.btn_select_folder)

        self.lbl_path = QLabel("Папка не выбрана")
        self.lbl_path.setStyleSheet("color: #888; font-size: 12px;")
        top_bar.addWidget(self.lbl_path, 1)

        self.btn_scan = QPushButton("Сканировать")
        self.btn_scan.setObjectName("btn_success")
        self.btn_scan.setMinimumHeight(35)
        self.btn_scan.setEnabled(False)
        self.btn_scan.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_scan.clicked.connect(self._start_scan)
        top_bar.addWidget(self.btn_scan)

        layout.addLayout(top_bar)

        # ── Прогресс ──
        self.progress = QProgressBar()
        self.progress.setFixedHeight(6)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # ── Статистика ──
        self.lbl_stats = QLabel("Статистика: —")
        self.lbl_stats.setStyleSheet(
            "color: #d4d4d4; font-size: 12px; padding: 6px; "
            "background-color: #1a1a1a; border-radius: 6px;"
        )
        self.lbl_stats.setWordWrap(True)
        layout.addWidget(self.lbl_stats)

        # ── Основная область ──
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ─── Левая часть: фильтры + дерево ───
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        # ── Вкладки фильтров ──
        filter_tabs = QTabWidget()
        filter_tabs.setMaximumHeight(220)
        filter_tabs.setStyleSheet(
            "QTabWidget::pane { border: 1px solid #3c3c3c; background-color: #1e1e1e; border-radius: 4px; }"
            "QTabBar::tab { background-color: #2d2d2d; color: #aaa; padding: 4px 10px; font-size: 11px; }"
            "QTabBar::tab:selected { background-color: #1e1e1e; color: #3498db; }"
        )

        # ─── Вкладка: Исключения ───
        excl_widget = QWidget()
        excl_layout = QVBoxLayout(excl_widget)
        excl_layout.setContentsMargins(6, 6, 6, 6)

        self.chk_gitignore = QCheckBox("Использовать .gitignore")
        self.chk_gitignore.setChecked(True)
        self.chk_gitignore.setStyleSheet("color: #d4d4d4; font-size: 12px;")
        excl_layout.addWidget(self.chk_gitignore)

        self.chk_default_ignores = QCheckBox("Стандартные исключения (node_modules, venv, .idea...)")
        self.chk_default_ignores.setChecked(True)
        self.chk_default_ignores.setStyleSheet("color: #d4d4d4; font-size: 12px;")
        excl_layout.addWidget(self.chk_default_ignores)

        lbl_excl_dirs = QLabel("Исключить директории (через запятую):")
        lbl_excl_dirs.setStyleSheet("color: #aaa; font-size: 11px; margin-top: 4px;")
        excl_layout.addWidget(lbl_excl_dirs)
        self.txt_excl_dirs = QLineEdit()
        self.txt_excl_dirs.setPlaceholderText("custom_dir, temp, logs")
        self.txt_excl_dirs.setStyleSheet(
            "QLineEdit { background: #151515; color: #d4d4d4; border: 1px solid #3c3c3c; "
            "border-radius: 4px; padding: 4px; font-size: 12px; }"
        )
        excl_layout.addWidget(self.txt_excl_dirs)

        lbl_excl_patterns = QLabel("Исключить файлы (glob, через запятую):")
        lbl_excl_patterns.setStyleSheet("color: #aaa; font-size: 11px; margin-top: 4px;")
        excl_layout.addWidget(lbl_excl_patterns)
        self.txt_excl_patterns = QLineEdit()
        self.txt_excl_patterns.setPlaceholderText("*.log, *.tmp, test_*.py")
        self.txt_excl_patterns.setStyleSheet(
            "QLineEdit { background: #151515; color: #d4d4d4; border: 1px solid #3c3c3c; "
            "border-radius: 4px; padding: 4px; font-size: 12px; }"
        )
        excl_layout.addWidget(self.txt_excl_patterns)

        excl_layout.addStretch()
        filter_tabs.addTab(excl_widget, "Исключения")

        # ─── Вкладка: Фильтры ───
        filters_widget = QWidget()
        filters_layout = QVBoxLayout(filters_widget)
        filters_layout.setContentsMargins(6, 6, 6, 6)

        # Расширения
        ext_row = QHBoxLayout()
        lbl_ext = QLabel("Расширения:")
        lbl_ext.setStyleSheet("color: #aaa; font-size: 11px;")
        ext_row.addWidget(lbl_ext)
        self.cmb_ext_mode = QComboBox()
        self.cmb_ext_mode.addItems(["Все", "Только...", "Кроме..."])
        self.cmb_ext_mode.setStyleSheet(
            "QComboBox { background: #151515; color: #d4d4d4; border: 1px solid #3c3c3c; "
            "border-radius: 4px; padding: 4px; font-size: 11px; }"
            "QComboBox QAbstractItemView { background: #1a1a1a; color: #d4d4d4; }"
        )
        self.cmb_ext_mode.setFixedWidth(90)
        ext_row.addWidget(self.cmb_ext_mode)
        self.txt_extensions = QLineEdit()
        self.txt_extensions.setPlaceholderText(".py, .js, .ts")
        self.txt_extensions.setStyleSheet(
            "QLineEdit { background: #151515; color: #d4d4d4; border: 1px solid #3c3c3c; "
            "border-radius: 4px; padding: 4px; font-size: 12px; }"
        )
        ext_row.addWidget(self.txt_extensions)
        filters_layout.addLayout(ext_row)

        # Языки
        lang_row = QHBoxLayout()
        lbl_lang = QLabel("Языки:")
        lbl_lang.setStyleSheet("color: #aaa; font-size: 11px;")
        lang_row.addWidget(lbl_lang)
        self.cmb_lang_mode = QComboBox()
        self.cmb_lang_mode.addItems(["Все", "Только...", "Кроме..."])
        self.cmb_lang_mode.setStyleSheet(
            "QComboBox { background: #151515; color: #d4d4d4; border: 1px solid #3c3c3c; "
            "border-radius: 4px; padding: 4px; font-size: 11px; }"
            "QComboBox QAbstractItemView { background: #1a1a1a; color: #d4d4d4; }"
        )
        self.cmb_lang_mode.setFixedWidth(90)
        lang_row.addWidget(self.cmb_lang_mode)
        self.txt_languages = QLineEdit()
        self.txt_languages.setPlaceholderText("Python, TypeScript")
        self.txt_languages.setStyleSheet(
            "QLineEdit { background: #151515; color: #d4d4d4; border: 1px solid #3c3c3c; "
            "border-radius: 4px; padding: 4px; font-size: 12px; }"
        )
        lang_row.addWidget(self.txt_languages)
        filters_layout.addLayout(lang_row)

        # Размер файла
        size_row = QHBoxLayout()
        lbl_size = QLabel("Размер файла:")
        lbl_size.setStyleSheet("color: #aaa; font-size: 11px;")
        size_row.addWidget(lbl_size)
        self.spn_min_size = QSpinBox()
        self.spn_min_size.setRange(0, 100_000)
        self.spn_min_size.setValue(0)
        self.spn_min_size.setSuffix(" KB мин")
        self.spn_min_size.setStyleSheet(
            "QSpinBox { background: #151515; color: #d4d4d4; border: 1px solid #3c3c3c; "
            "border-radius: 4px; padding: 4px; font-size: 11px; }"
        )
        size_row.addWidget(self.spn_min_size)
        self.spn_max_size = QSpinBox()
        self.spn_max_size.setRange(1, 100_000)
        self.spn_max_size.setValue(512)
        self.spn_max_size.setSuffix(" KB макс")
        self.spn_max_size.setStyleSheet(
            "QSpinBox { background: #151515; color: #d4d4d4; border: 1px solid #3c3c3c; "
            "border-radius: 4px; padding: 4px; font-size: 11px; }"
        )
        size_row.addWidget(self.spn_max_size)
        filters_layout.addLayout(size_row)

        # Regex
        regex_row = QHBoxLayout()
        lbl_regex = QLabel("Regex:")
        lbl_regex.setStyleSheet("color: #aaa; font-size: 11px;")
        regex_row.addWidget(lbl_regex)
        self.txt_include_regex = QLineEdit()
        self.txt_include_regex.setPlaceholderText("Включить (regex)")
        self.txt_include_regex.setStyleSheet(
            "QLineEdit { background: #151515; color: #d4d4d4; border: 1px solid #3c3c3c; "
            "border-radius: 4px; padding: 4px; font-size: 12px; }"
        )
        regex_row.addWidget(self.txt_include_regex)
        self.txt_exclude_regex = QLineEdit()
        self.txt_exclude_regex.setPlaceholderText("Исключить (regex)")
        self.txt_exclude_regex.setStyleSheet(
            "QLineEdit { background: #151515; color: #d4d4d4; border: 1px solid #3c3c3c; "
            "border-radius: 4px; padding: 4px; font-size: 12px; }"
        )
        regex_row.addWidget(self.txt_exclude_regex)
        filters_layout.addLayout(regex_row)

        filters_layout.addStretch()
        filter_tabs.addTab(filters_widget, "Фильтры")

        # ─── Вкладка: Вывод ───
        output_widget = QWidget()
        output_layout = QVBoxLayout(output_widget)
        output_layout.setContentsMargins(6, 6, 6, 6)

        self.chk_tree = QCheckBox("Включить дерево файлов")
        self.chk_tree.setChecked(True)
        self.chk_tree.setStyleSheet("color: #d4d4d4; font-size: 12px;")
        output_layout.addWidget(self.chk_tree)

        self.chk_contents = QCheckBox("Включить содержимое файлов")
        self.chk_contents.setChecked(False)
        self.chk_contents.setStyleSheet("color: #d4d4d4; font-size: 12px;")
        output_layout.addWidget(self.chk_contents)

        self.chk_line_numbers = QCheckBox("Нумерация строк")
        self.chk_line_numbers.setChecked(True)
        self.chk_line_numbers.setStyleSheet("color: #d4d4d4; font-size: 12px;")
        output_layout.addWidget(self.chk_line_numbers)

        self.chk_file_stats = QCheckBox("Показывать статистику файлов")
        self.chk_file_stats.setChecked(True)
        self.chk_file_stats.setStyleSheet("color: #d4d4d4; font-size: 12px;")
        output_layout.addWidget(self.chk_file_stats)

        # Сортировка
        sort_row = QHBoxLayout()
        lbl_sort = QLabel("Сортировка:")
        lbl_sort.setStyleSheet("color: #aaa; font-size: 11px;")
        sort_row.addWidget(lbl_sort)
        self.cmb_sort = QComboBox()
        self.cmb_sort.addItems(["По пути", "По размеру", "По токенам"])
        self.cmb_sort.setStyleSheet(
            "QComboBox { background: #151515; color: #d4d4d4; border: 1px solid #3c3c3c; "
            "border-radius: 4px; padding: 4px; font-size: 11px; }"
            "QComboBox QAbstractItemView { background: #1a1a1a; color: #d4d4d4; }"
        )
        sort_row.addWidget(self.cmb_sort)
        output_layout.addLayout(sort_row)

        # Лимит токенов
        token_row = QHBoxLayout()
        lbl_tokens = QLabel("Лимит токенов:")
        lbl_tokens.setStyleSheet("color: #aaa; font-size: 11px;")
        token_row.addWidget(lbl_tokens)
        self.spn_max_tokens = QSpinBox()
        self.spn_max_tokens.setRange(1_000, 1_000_000)
        self.spn_max_tokens.setValue(200_000)
        self.spn_max_tokens.setSingleStep(10_000)
        self.spn_max_tokens.setStyleSheet(
            "QSpinBox { background: #151515; color: #d4d4d4; border: 1px solid #3c3c3c; "
            "border-radius: 4px; padding: 4px; font-size: 11px; }"
        )
        token_row.addWidget(self.spn_max_tokens)
        output_layout.addLayout(token_row)

        output_layout.addStretch()
        filter_tabs.addTab(output_widget, "Вывод")

        left_layout.addWidget(filter_tabs)

        # ── Дерево файлов ──
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Файл", "Строк", "Токенов", "Язык", "Размер"])
        self.tree.setColumnWidth(0, 280)
        self.tree.setColumnWidth(1, 60)
        self.tree.setColumnWidth(2, 70)
        self.tree.setColumnWidth(3, 90)
        self.tree.setColumnWidth(4, 70)
        self.tree.setAlternatingRowColors(True)
        self.tree.setStyleSheet(
            "QTreeWidget { background-color: #1a1a1a; color: #d4d4d4; "
            "border: 1px solid #3c3c3c; border-radius: 6px; font-size: 12px; }"
            "QTreeWidget::item { padding: 2px; }"
            "QTreeWidget::item:selected { background-color: #264f78; }"
            "QHeaderView::section { background-color: #2d2d2d; color: #d4d4d4; "
            "border: 1px solid #3c3c3c; padding: 4px; font-weight: bold; font-size: 11px; }"
        )
        left_layout.addWidget(self.tree, 1)

        # Управление деревом
        tree_btns = QHBoxLayout()
        self.btn_select_all = QPushButton("Выбрать все")
        self.btn_select_all.clicked.connect(self._select_all_files)
        tree_btns.addWidget(self.btn_select_all)

        self.btn_deselect_all = QPushButton("Снять выбор")
        self.btn_deselect_all.clicked.connect(self._deselect_all_files)
        tree_btns.addWidget(self.btn_deselect_all)

        self.lbl_selected_info = QLabel("Выбрано: 0 файлов, 0 токенов")
        self.lbl_selected_info.setStyleSheet("color: #f39c12; font-size: 11px;")
        tree_btns.addWidget(self.lbl_selected_info, 1)

        left_layout.addLayout(tree_btns)
        splitter.addWidget(left_widget)

        # ─── Правая часть: контекст ───
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        ctx_header = QHBoxLayout()
        lbl_ctx = QLabel("Контекст для ИИ")
        lbl_ctx.setObjectName("accent_title")
        ctx_header.addWidget(lbl_ctx)
        ctx_header.addStretch()
        right_layout.addLayout(ctx_header)

        self.txt_context = QTextEdit()
        self.txt_context.setReadOnly(True)
        self.txt_context.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.txt_context.setStyleSheet(
            "QTextEdit { font-family: Consolas, monospace; font-size: 12px; "
            "background-color: #0d0d0d; border: 1px solid #3c3c3c; border-radius: 6px; "
            "padding: 8px; color: #d4d4d4; }"
        )
        right_layout.addWidget(self.txt_context)

        # Кнопки генерации
        gen_btns = QHBoxLayout()

        self.btn_generate = QPushButton("Сгенерировать контекст")
        self.btn_generate.setObjectName("btn_purple")
        self.btn_generate.setMinimumHeight(35)
        self.btn_generate.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_generate.setEnabled(False)
        self.btn_generate.clicked.connect(self._generate_context)
        gen_btns.addWidget(self.btn_generate)

        self.btn_copy = QPushButton("Скопировать в буфер")
        self.btn_copy.setObjectName("btn_copy")
        self.btn_copy.setMinimumHeight(35)
        self.btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy.setEnabled(False)
        self.btn_copy.clicked.connect(self._copy_context)
        gen_btns.addWidget(self.btn_copy)

        right_layout.addLayout(gen_btns)
        splitter.addWidget(right_widget)

        splitter.setSizes([500, 500])
        layout.addWidget(splitter, 1)

    # ─────────────────── Действия ───────────────────

    def _select_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку проекта")
        if folder:
            self._scan_path = folder
            self.lbl_path.setText(folder)
            self.lbl_path.setStyleSheet("color: #2ecc71; font-size: 12px;")
            self.btn_scan.setEnabled(True)

    def _build_scan_filter(self) -> ScanFilter:
        """Собирает ScanFilter из UI-элементов."""
        sf = ScanFilter(
            use_gitignore=self.chk_gitignore.isChecked(),
            use_default_ignores=self.chk_default_ignores.isChecked(),
            min_file_size=self.spn_min_size.value() * 1024,
            max_file_size=self.spn_max_size.value() * 1024,
        )

        # Пользовательские исключения директорий
        dirs_text = self.txt_excl_dirs.text().strip()
        if dirs_text:
            sf.user_ignore_dirs = [d.strip() for d in dirs_text.split(",") if d.strip()]

        # Пользовательские glob-исключения
        patterns_text = self.txt_excl_patterns.text().strip()
        if patterns_text:
            sf.user_ignore_patterns = [p.strip() for p in patterns_text.split(",") if p.strip()]

        # Расширения
        ext_text = self.txt_extensions.text().strip()
        if ext_text:
            exts = {e.strip() if e.strip().startswith(".") else f".{e.strip()}"
                    for e in ext_text.split(",") if e.strip()}
            mode = self.cmb_ext_mode.currentText()
            if mode == "Только...":
                sf.include_extensions = exts
            elif mode == "Кроме...":
                sf.exclude_extensions = exts

        # Языки
        lang_text = self.txt_languages.text().strip()
        if lang_text:
            langs = {l.strip() for l in lang_text.split(",") if l.strip()}
            mode = self.cmb_lang_mode.currentText()
            if mode == "Только...":
                sf.include_languages = langs
            elif mode == "Кроме...":
                sf.exclude_languages = langs

        # Regex
        inc_re = self.txt_include_regex.text().strip()
        if inc_re:
            sf.include_regex = inc_re
        exc_re = self.txt_exclude_regex.text().strip()
        if exc_re:
            sf.exclude_regex = exc_re

        return sf

    def _start_scan(self) -> None:
        if not self._scan_path:
            return

        self.btn_scan.setEnabled(False)
        self.btn_select_folder.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)

        scan_filter = self._build_scan_filter()
        self._scan_thread = ScannerThread(self._engine, self._scan_path, scan_filter)
        self._scan_thread.scan_done.connect(self._on_scan_done)
        self._scan_thread.start()

    def _on_scan_done(self, result: ScanResult) -> None:
        self._scan_result = result
        self.btn_scan.setEnabled(True)
        self.btn_select_folder.setEnabled(True)
        self.progress.setVisible(False)

        # Статистика
        lang_parts = ", ".join(
            f"{lang} ({count})" for lang, count in list(result.languages.items())[:8]
        )
        gitignore_status = "Да" if result.gitignore_loaded else "Нет"
        self.lbl_stats.setText(
            f"Файлов: {result.total_files} | "
            f"Строк: {result.total_lines} | "
            f"Токенов: {result.total_tokens:,} | "
            f"Размер: {result.total_size / 1024:.1f} KB | "
            f".gitignore: {gitignore_status}\n"
            f"Языки: {lang_parts}"
        )

        self._populate_tree(result)
        self.btn_generate.setEnabled(True)
        self.btn_copy.setEnabled(True)

    def _populate_tree(self, result: ScanResult) -> None:
        self.tree.clear()
        dir_items: dict = {}

        for fi in sorted(result.files, key=lambda f: f.rel_path):
            dir_name = os.path.dirname(fi.rel_path)
            parent = self.tree.invisibleRootItem()

            if dir_name:
                parts = dir_name.split("/")
                current_path = ""
                current_parent = self.tree.invisibleRootItem()

                for part in parts:
                    current_path = f"{current_path}/{part}" if current_path else part
                    if current_path in dir_items:
                        current_parent = dir_items[current_path]
                    else:
                        dir_item = QTreeWidgetItem(current_parent, [part, "", "", "", ""])
                        dir_item.setFlags(
                            dir_item.flags()
                            | Qt.ItemFlag.ItemIsAutoTristate
                            | Qt.ItemFlag.ItemIsUserCheckable
                        )
                        dir_item.setCheckState(0, Qt.CheckState.Checked)
                        dir_item.setData(0, Qt.ItemDataRole.UserRole, "dir")
                        dir_items[current_path] = dir_item
                        current_parent = dir_item

                parent = current_parent

            size_str = f"{fi.size_bytes / 1024:.1f}KB" if fi.size_bytes < 1024 * 1024 else f"{fi.size_bytes / 1024 / 1024:.1f}MB"
            file_item = QTreeWidgetItem(
                parent,
                [os.path.basename(fi.rel_path), str(fi.line_count),
                 f"{fi.token_estimate:,}", fi.language, size_str],
            )
            file_item.setFlags(file_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            file_item.setCheckState(0, Qt.CheckState.Checked)
            file_item.setData(0, Qt.ItemDataRole.UserRole, fi.rel_path)

        self.tree.expandAll()

    def _get_selected_files(self) -> list[str]:
        selected = []
        self._collect_checked(self.tree.invisibleRootItem(), selected)
        return selected

    def _collect_checked(self, item: QTreeWidgetItem, result: list) -> None:
        for i in range(item.childCount()):
            child = item.child(i)
            if child.checkState(0) == Qt.CheckState.Checked:
                data = child.data(0, Qt.ItemDataRole.UserRole)
                if data and data != "dir":
                    result.append(data)
            self._collect_checked(child, result)

    def _select_all_files(self) -> None:
        self._set_all_checked(self.tree.invisibleRootItem(), Qt.CheckState.Checked)

    def _deselect_all_files(self) -> None:
        self._set_all_checked(self.tree.invisibleRootItem(), Qt.CheckState.Unchecked)

    def _set_all_checked(self, item: QTreeWidgetItem, state: Qt.CheckState) -> None:
        for i in range(item.childCount()):
            child = item.child(i)
            child.setCheckState(0, state)
            self._set_all_checked(child, state)

    def _build_context_options(self) -> ContextOptions:
        """Собирает ContextOptions из UI-элементов."""
        sort_map = {"По пути": "path", "По размеру": "size", "По токенам": "tokens"}
        return ContextOptions(
            include_tree=self.chk_tree.isChecked(),
            include_contents=self.chk_contents.isChecked(),
            line_numbers=self.chk_line_numbers.isChecked(),
            show_file_stats=self.chk_file_stats.isChecked(),
            max_tokens=self.spn_max_tokens.value(),
            sort_by=sort_map.get(self.cmb_sort.currentText(), "path"),
        )

    def _generate_context(self) -> None:
        if not self._scan_result:
            return

        selected = self._get_selected_files()
        options = self._build_context_options()

        context = self._engine.generate_context(
            self._scan_result,
            selected_files=selected if selected else None,
            options=options,
        )

        self.txt_context.setPlainText(context)
        self.btn_copy.setEnabled(True)

        # Обновляем инфо о выбранных файлах
        self._update_selected_info()

    def _update_selected_info(self) -> None:
        if not self._scan_result:
            return
        selected = self._get_selected_files()
        if not selected:
            self.lbl_selected_info.setText("Выбрано: 0 файлов")
            return
        total_tokens = sum(
            fi.token_estimate for fi in self._scan_result.files
            if fi.rel_path in set(selected)
        )
        self.lbl_selected_info.setText(
            f"Выбрано: {len(selected)} файлов, ~{total_tokens:,} токенов"
        )

    def _copy_context(self) -> None:
        text = self.txt_context.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self.btn_copy.setText("Скопировано!")
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(2000, lambda: self.btn_copy.setText("Скопировать в буфер"))
