"""
Диалог управления бэкапами (Машина Времени).

ИСПРАВЛЕНО: голые except: заменены на конкретные типы исключений.
"""

import os
import json

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QScrollArea,
    QFrame,
    QMessageBox,
    QWidget,
)
from PyQt6.QtCore import Qt

from ai_patcher_pro.core.backup import BackupManager


class BackupManagerDialog(QDialog):
    """Диалог просмотра и восстановления бэкапов."""

    def __init__(self, parent, workspace: str):
        """
        Args:
            parent: Родительский виджет.
            workspace: Рабочая директория проекта.
        """
        super().__init__(parent)
        self.workspace = workspace
        self.backup_mgr = BackupManager(workspace)
        self.setWindowTitle("Машина Времени (История патчей)")
        self.resize(650, 500)

        self.all_backups: list = []
        self.loaded_count = 0
        self.chunk_size = 20
        self.is_loading = False

        self._init_ui()
        self._init_backups_list()

    def _init_ui(self) -> None:
        """Инициализация UI диалога."""
        layout = QVBoxLayout(self)
        lbl = QLabel("История бэкапов:")
        lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #007acc;")
        layout.addWidget(lbl)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)

        content = QWidget()
        content.setStyleSheet("background-color: #252526;")
        self.list_layout = QVBoxLayout(content)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.scroll_area.setWidget(content)
        layout.addWidget(self.scroll_area)

        self.scroll_area.verticalScrollBar().valueChanged.connect(
            self._check_scroll_position
        )

    def _init_backups_list(self) -> None:
        """Загружает начальный список бэкапов."""
        self.all_backups = self.backup_mgr.list_backups()
        self._load_more_backups()

    def _load_more_backups(self) -> None:
        """Подгружает следующую порцию бэкапов (lazy loading)."""
        if self.is_loading or self.loaded_count >= len(self.all_backups):
            return

        self.is_loading = True
        chunk = self.all_backups[self.loaded_count : self.loaded_count + self.chunk_size]

        for b_dir in chunk:
            full_path = self.backup_mgr.get_backup_path(b_dir)
            meta = self.backup_mgr.get_backup_meta(b_dir)

            if meta:
                name = f"[{meta['timestamp']}] {meta.get('patch_name', 'Патч')}"
            else:
                name = b_dir

            frame = QFrame()
            frame.setStyleSheet(
                "background-color: #1e1e1e; border-radius: 6px; padding: 5px;"
            )
            h_layout = QHBoxLayout(frame)

            h_layout.addWidget(QLabel(name))

            btn_restore = QPushButton("ОТКАТИТЬ")
            btn_restore.setObjectName("btn_danger")
            btn_restore.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_restore.setFixedWidth(80)
            btn_restore.clicked.connect(
                lambda checked=False, p=full_path: self._restore(p)
            )
            h_layout.addWidget(btn_restore)

            self.list_layout.addWidget(frame)

        self.loaded_count += len(chunk)
        self.is_loading = False

    def _check_scroll_position(self, value: int) -> None:
        """Проверяет позицию скролла для lazy loading."""
        scrollbar = self.scroll_area.verticalScrollBar()
        if value >= scrollbar.maximum() * 0.90:
            self._load_more_backups()

    def _restore(self, backup_path: str) -> None:
        """
        Восстанавливает файлы из бэкапа.

        ИСПРАВЛЕНО: используются конкретные типы исключений вместо bare except.
        """
        reply = QMessageBox.question(
            self,
            "Внимание",
            "Откатить файлы к этой версии?\nНесохраненные изменения будут утеряны.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.backup_mgr.restore_backup(backup_path, self.workspace)
                QMessageBox.information(self, "Успех", "Файлы успешно восстановлены!")
                self.accept()
            except (OSError, IOError) as e:
                QMessageBox.critical(
                    self, "Ошибка", f"Не удалось восстановить файлы: {e}"
                )
