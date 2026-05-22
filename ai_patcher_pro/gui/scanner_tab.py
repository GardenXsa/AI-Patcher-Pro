"""
Вкладка сканера проекта.

Отображает дерево файлов проекта, статистику по языкам,
оценку токенов и генерирует контекст для промпта ИИ.
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
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from ai_patcher_pro.core.scanner import ScannerEngine, ScanResult


class ScannerThread(QThread):
    """Фоновый поток для сканирования проекта."""

    scan_done = pyqtSignal(object)  # ScanResult

    def __init__(self, engine: ScannerEngine, root_path: str):
        super().__init__()
        self.engine = engine
        self.root_path = root_path

    def run(self) -> None:
        result = self.engine.scan(self.root_path)
        self.scan_done.emit(result)


class ScannerTab(QWidget):
    """
    Вкладка сканера проекта.

    Позволяет:
    - Выбрать папку проекта для сканирования
    - Просмотреть дерево файлов и статистику
    - Выбрать файлы для включения в контекст
    - Сгенерировать и скопировать контекст для ИИ
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._engine = ScannerEngine()
        self._scan_result: ScanResult | None = None
        self._scan_path = ""
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)

        # --- Верхняя панель: выбор папки ---
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

        # --- Прогресс ---
        self.progress = QProgressBar()
        self.progress.setFixedHeight(6)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # --- Основная область: сплиттер ---
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Левая часть: дерево файлов + статистика
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Статистика
        self.lbl_stats = QLabel("Статистика: —")
        self.lbl_stats.setStyleSheet(
            "color: #d4d4d4; font-size: 12px; padding: 5px; "
            "background-color: #1a1a1a; border-radius: 6px;"
        )
        self.lbl_stats.setWordWrap(True)
        left_layout.addWidget(self.lbl_stats)

        # Дерево файлов
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Файл", "Строк", "Токенов", "Язык"])
        self.tree.setColumnWidth(0, 300)
        self.tree.setColumnWidth(1, 70)
        self.tree.setColumnWidth(2, 80)
        self.tree.setColumnWidth(3, 100)
        self.tree.setAlternatingRowColors(True)
        self.tree.setStyleSheet(
            "QTreeWidget { background-color: #1a1a1a; color: #d4d4d4; "
            "border: 1px solid #3c3c3c; border-radius: 6px; font-size: 12px; }"
            "QTreeWidget::item { padding: 3px; }"
            "QTreeWidget::item:selected { background-color: #264f78; }"
            "QHeaderView::section { background-color: #2d2d2d; color: #d4d4d4; "
            "border: 1px solid #3c3c3c; padding: 5px; font-weight: bold; }"
        )
        left_layout.addWidget(self.tree)

        # Кнопки управления деревом
        tree_btns = QHBoxLayout()

        self.btn_select_all = QPushButton("Выбрать все")
        self.btn_select_all.clicked.connect(self._select_all_files)
        tree_btns.addWidget(self.btn_select_all)

        self.btn_deselect_all = QPushButton("Снять выбор")
        self.btn_deselect_all.clicked.connect(self._deselect_all_files)
        tree_btns.addWidget(self.btn_deselect_all)

        self.lbl_selected_tokens = QLabel("Выбрано: 0 токенов")
        self.lbl_selected_tokens.setStyleSheet("color: #f39c12; font-size: 11px;")
        tree_btns.addWidget(self.lbl_selected_tokens, 1)

        left_layout.addLayout(tree_btns)
        splitter.addWidget(left_widget)

        # Правая часть: контекст
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        ctx_header = QHBoxLayout()
        lbl_ctx = QLabel("Контекст для ИИ")
        lbl_ctx.setObjectName("accent_title")
        ctx_header.addWidget(lbl_ctx)
        ctx_header.addStretch()
        right_layout.addLayout(ctx_header)

        # Опции генерации
        opts_layout = QHBoxLayout()

        self.chk_tree = QCheckBox("Дерево файлов")
        self.chk_tree.setChecked(True)
        self.chk_tree.setStyleSheet("color: #d4d4d4; font-size: 12px;")
        opts_layout.addWidget(self.chk_tree)

        self.chk_contents = QCheckBox("Содержимое файлов")
        self.chk_contents.setChecked(False)
        self.chk_contents.setStyleSheet("color: #d4d4d4; font-size: 12px;")
        self.chk_contents.stateChanged.connect(self._on_contents_toggled)
        opts_layout.addWidget(self.chk_contents)

        opts_layout.addStretch()
        right_layout.addLayout(opts_layout)

        # Текстовое поле с контекстом
        self.txt_context = QTextEdit()
        self.txt_context.setReadOnly(True)
        self.txt_context.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.txt_context.setStyleSheet(
            "QTextEdit { font-family: Consolas, monospace; font-size: 12px; "
            "background-color: #0d0d0d; border: 1px solid #3c3c3c; border-radius: 6px; "
            "padding: 8px; color: #d4d4d4; }"
        )
        right_layout.addWidget(self.txt_context)

        # Кнопка генерации
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
        layout.addWidget(splitter)

    def _select_folder(self) -> None:
        """Открывает диалог выбора папки проекта."""
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку проекта")
        if folder:
            self._scan_path = folder
            self.lbl_path.setText(folder)
            self.lbl_path.setStyleSheet("color: #2ecc71; font-size: 12px;")
            self.btn_scan.setEnabled(True)

    def _start_scan(self) -> None:
        """Запускает сканирование проекта."""
        if not self._scan_path:
            return

        self.btn_scan.setEnabled(False)
        self.btn_select_folder.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)  # Неопределённый прогресс

        self._scan_thread = ScannerThread(self._engine, self._scan_path)
        self._scan_thread.scan_done.connect(self._on_scan_done)
        self._scan_thread.start()

    def _on_scan_done(self, result: ScanResult) -> None:
        """Обрабатывает завершение сканирования."""
        self._scan_result = result
        self.btn_scan.setEnabled(True)
        self.btn_select_folder.setEnabled(True)
        self.progress.setVisible(False)

        # Статистика
        lang_parts = ", ".join(
            f"{lang} ({count})" for lang, count in list(result.languages.items())[:6]
        )
        self.lbl_stats.setText(
            f"Файлов: {result.total_files} | "
            f"Строк: {result.total_lines} | "
            f"Токенов: {result.total_tokens:,} | "
            f"Размер: {result.total_size / 1024:.1f} KB\n"
            f"Языки: {lang_parts}"
        )

        # Заполняем дерево
        self._populate_tree(result)

        # Автогенерация контекста (только дерево)
        self.btn_generate.setEnabled(True)
        self.btn_copy.setEnabled(True)

    def _populate_tree(self, result: ScanResult) -> None:
        """Заполняет дерево файлов из результата сканирования."""
        self.tree.clear()

        # Группируем файлы по директориям
        dir_items: dict = {}  # rel_dir -> QTreeWidgetItem

        for fi in sorted(result.files, key=lambda f: f.rel_path):
            dir_name = os.path.dirname(fi.rel_path)

            # Находим или создаём родительский элемент
            parent = self.tree.invisibleRootItem()

            if dir_name:
                # Создаём все промежуточные директории
                parts = dir_name.split("/")
                current_path = ""
                current_parent = self.tree.invisibleRootItem()

                for part in parts:
                    current_path = f"{current_path}/{part}" if current_path else part
                    if current_path in dir_items:
                        current_parent = dir_items[current_path]
                    else:
                        dir_item = QTreeWidgetItem(current_parent, [part, "", "", ""])
                        dir_item.setFlags(
                            dir_item.flags()
                            | Qt.ItemFlag.ItemIsAutoTristate
                            | Qt.ItemFlag.ItemIsUserCheckable
                        )
                        dir_item.setCheckState(
                            0, Qt.CheckState.Checked
                        )
                        dir_item.setData(0, Qt.ItemDataRole.UserRole, "dir")
                        dir_items[current_path] = dir_item
                        current_parent = dir_item

                parent = current_parent

            # Элемент файла
            file_item = QTreeWidgetItem(
                parent,
                [os.path.basename(fi.rel_path), str(fi.line_count),
                 f"{fi.token_estimate:,}", fi.language],
            )
            file_item.setFlags(
                file_item.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            file_item.setCheckState(0, Qt.CheckState.Checked)
            file_item.setData(0, Qt.ItemDataRole.UserRole, fi.rel_path)

        self.tree.expandAll()

    def _get_selected_files(self) -> list[str]:
        """Возвращает список путей выбранных файлов."""
        selected = []
        root = self.tree.invisibleRootItem()
        self._collect_checked(root, selected)
        return selected

    def _collect_checked(self, item: QTreeWidgetItem, result: list) -> None:
        """Рекурсивно собирает выбранные файлы."""
        for i in range(item.childCount()):
            child = item.child(i)
            if child.checkState(0) == Qt.CheckState.Checked:
                data = child.data(0, Qt.ItemDataRole.UserRole)
                if data and data != "dir":
                    result.append(data)
            self._collect_checked(child, result)

    def _select_all_files(self) -> None:
        """Выбирает все файлы в дереве."""
        self._set_all_checked(self.tree.invisibleRootItem(), Qt.CheckState.Checked)

    def _deselect_all_files(self) -> None:
        """Снимает выбор со всех файлов."""
        self._set_all_checked(self.tree.invisibleRootItem(), Qt.CheckState.Unchecked)

    def _set_all_checked(self, item: QTreeWidgetItem, state: Qt.CheckState) -> None:
        """Рекурсивно устанавливает состояние чекбоксов."""
        for i in range(item.childCount()):
            child = item.child(i)
            child.setCheckState(0, state)
            self._set_all_checked(child, state)

    def _on_contents_toggled(self) -> None:
        """Обновляет оценку токенов при переключении чекбокса."""
        self._update_selected_tokens()

    def _update_selected_tokens(self) -> None:
        """Обновляет метку с оценкой токенов для выбранных файлов."""
        if not self._scan_result:
            return

        selected = self._get_selected_files()
        if not selected:
            self.lbl_selected_tokens.setText("Выбрано: 0 файлов")
            return

        total = 0
        for fi in self._scan_result.files:
            if fi.rel_path in selected:
                total += fi.token_estimate

        self.lbl_selected_tokens.setText(
            f"Выбрано: {len(selected)} файлов, ~{total:,} токенов"
        )

    def _generate_context(self) -> None:
        """Генерирует контекст для ИИ."""
        if not self._scan_result:
            return

        selected = self._get_selected_files()
        include_contents = self.chk_contents.isChecked()
        include_tree = self.chk_tree.isChecked()

        context = self._engine.generate_context(
            self._scan_result,
            include_tree=include_tree,
            include_contents=include_contents,
            selected_files=selected if selected else None,
        )

        self.txt_context.setPlainText(context)
        self.btn_copy.setEnabled(True)

    def _copy_context(self) -> None:
        """Копирует контекст в буфер обмена."""
        text = self.txt_context.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self.btn_copy.setText("Скопировано!")
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(2000, lambda: self.btn_copy.setText("Скопировать в буфер"))
