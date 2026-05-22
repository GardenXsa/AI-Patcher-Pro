"""
Карточка операции — визуальное отображение одной операции патча.

Визуальные статусы:
- НАЙДЕНО (голубой) — код найден при анализе, патч ещё НЕ применён к диску
- ПРИМЕНЕНО (зелёный) — патч записан на диск
- УЖЕ БЫЛО (серый) — изменения уже присутствовали
- ОШИБКА (красный) — не удалось найти или применить
"""

import json

from PyQt6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QTextEdit,
    QSizePolicy,
)
from PyQt6.QtCore import Qt

from ai_patcher_pro.gui.code_viewer import CodeViewerFactory


# ─────────────── Цвета и тексты статусов ───────────────

ST_STYLES = {
    "success": {
        "card_obj": "card_preview",       # голубая рамка — превью
        "color": "#00bcd4",               # циан
        "text": "НАЙДЕНО",
        "icon": "?",
        "sub": "Изменения в превью (ещё не записаны на диск)",
    },
    "applied": {
        "card_obj": "card_success",       # зелёная рамка — применено
        "color": "#27ae60",
        "text": "ПРИМЕНЕНО",
        "icon": "?",
        "sub": "Патч успешно записан на диск",
    },
    "already_applied": {
        "card_obj": "card_info",          # синяя рамка
        "color": "#3498db",
        "text": "УЖЕ БЫЛО",
        "icon": "i",
        "sub": "Изменения уже присутствовали в файле",
    },
    "error": {
        "card_obj": "card_error",         # красная рамка
        "color": "#c0392b",
        "text": "ОШИБКА",
        "icon": "X",
        "sub": "Не удалось применить операцию",
    },
}


class OperationCard(QFrame):
    """Карточка одной операции с diff-превью и кнопками управления."""

    def __init__(self, item: dict, parent_app):
        """
        Args:
            item: Словарь результата операции.
            parent_app: Ссылка на главное окно для вызова действий.
        """
        super().__init__()
        self.item = item
        self.app = parent_app
        self._viewer_factory = CodeViewerFactory()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMaximumWidth(1100)
        self._init_ui()

    def _create_code_viewer(self, text: str, max_h: int = 250) -> QTextEdit:
        """Создаёт виджет просмотра кода через фабрику (без бага GC)."""
        return self._viewer_factory.create_code_viewer(text, max_h)

    def _init_ui(self) -> None:
        """Инициализация UI карточки."""
        op = self.item["op"]
        status = self.item["status"]

        style = ST_STYLES.get(status, ST_STYLES["error"])
        self.setObjectName(style["card_obj"])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # ── Заголовок ──
        header = QHBoxLayout()

        path_str = op.get("path") or op.get("file", "???")
        action_str = op.get("action") or op.get("op", "???")
        lbl_title = QLabel(f"{path_str}  |  {action_str}")
        lbl_title.setStyleSheet(
            "font-weight: bold; font-size: 14px; font-family: 'Consolas';"
        )
        header.addWidget(lbl_title)

        # Бейдж статуса
        lbl_status = QLabel(style["text"])
        lbl_status.setStyleSheet(
            f"color: {style['color']}; "
            f"font-weight: bold; font-size: 12px; margin-left: 10px; "
            f"background-color: {style['color']}22; "
            f"padding: 2px 10px; border-radius: 4px; "
            f"border: 1px solid {style['color']}44;"
        )
        header.addWidget(lbl_status)
        header.addStretch()

        # Кнопки
        btn_edit = QPushButton("Редактировать")
        btn_edit.setObjectName("btn_edit")
        btn_edit.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_edit.clicked.connect(
            lambda checked=False, id=self.item["id"]: self.app.action_edit(id)
        )
        header.addWidget(btn_edit)

        btn_copy = QPushButton("Копировать")
        btn_copy.setObjectName("btn_copy")
        btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copy.clicked.connect(lambda checked=False: self.app.action_copy(op))
        header.addWidget(btn_copy)

        btn_del = QPushButton("Удалить")
        btn_del.setObjectName("btn_danger")
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.clicked.connect(
            lambda checked=False, id=self.item["id"]: self.app.action_delete(id)
        )
        header.addWidget(btn_del)

        layout.addLayout(header)

        # ── Подсказка под бейджем ──
        lbl_sub = QLabel(style["sub"])
        lbl_sub.setStyleSheet(
            f"color: {style['color']}88; font-size: 11px; font-style: italic; margin-top: -8px;"
        )
        layout.addWidget(lbl_sub)

        # ── Содержимое по статусу ──
        if status == "success":
            self._render_success(layout)
        elif status == "applied":
            self._render_applied(layout)
        elif status == "already_applied":
            self._render_already_applied(layout)
        elif status == "error":
            self._render_error(layout)

    def _render_success(self, layout: QVBoxLayout) -> None:
        """Отрисовка карточки найденной операции (превью, ещё не на диске)."""
        if self.item.get("search_method"):
            lbl_method = QLabel(f"Метод поиска: {self.item['search_method']}")
            lbl_method.setStyleSheet(
                "color: #8e44ad; font-style: italic; font-size: 12px;"
            )
            layout.addWidget(lbl_method)

        diff_text = QTextEdit()
        diff_text.setReadOnly(True)
        diff_text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)

        html = "<pre style='font-family: Consolas, monospace; font-size: 13px; margin: 0;'>"
        for line in self.item["diff"]:
            line = line.replace("<", "&lt;").replace(">", "&gt;")
            if line.startswith("---") or line.startswith("+++") or line.startswith("@@"):
                continue
            if line.startswith("+"):
                html += (
                    f"<div style='background-color: rgba(39, 174, 96, 0.15); "
                    f"color: #2ecc71; padding: 2px;'>{line}</div>"
                )
            elif line.startswith("-"):
                html += (
                    f"<div style='background-color: rgba(192, 57, 43, 0.15); "
                    f"color: #e74c3c; padding: 2px;'>{line}</div>"
                )
            else:
                html += f"<div style='color: #d4d4d4; padding: 2px;'>{line}</div>"
        html += "</pre>"

        diff_text.setHtml(html)

        diff_lines = len(
            [
                l
                for l in self.item["diff"]
                if not (l.startswith("---") or l.startswith("+++") or l.startswith("@@"))
            ]
        )
        extra_h = 22 if any(len(l) > 100 for l in self.item["diff"]) else 0
        diff_text.setFixedHeight(min(400, max(50, diff_lines * 18 + 24 + extra_h)))

        layout.addWidget(diff_text)

    def _render_applied(self, layout: QVBoxLayout) -> None:
        """Отрисовка карточки применённой операции (записано на диск)."""
        if self.item.get("search_method"):
            lbl_method = QLabel(f"Метод поиска: {self.item['search_method']}")
            lbl_method.setStyleSheet(
                "color: #8e44ad; font-style: italic; font-size: 12px;"
            )
            layout.addWidget(lbl_method)

        diff_text = QTextEdit()
        diff_text.setReadOnly(True)
        diff_text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)

        html = "<pre style='font-family: Consolas, monospace; font-size: 13px; margin: 0;'>"
        for line in self.item["diff"]:
            line = line.replace("<", "&lt;").replace(">", "&gt;")
            if line.startswith("---") or line.startswith("+++") or line.startswith("@@"):
                continue
            if line.startswith("+"):
                html += (
                    f"<div style='background-color: rgba(39, 174, 96, 0.15); "
                    f"color: #2ecc71; padding: 2px;'>{line}</div>"
                )
            elif line.startswith("-"):
                html += (
                    f"<div style='background-color: rgba(192, 57, 43, 0.15); "
                    f"color: #e74c3c; padding: 2px;'>{line}</div>"
                )
            else:
                html += f"<div style='color: #d4d4d4; padding: 2px;'>{line}</div>"
        html += "</pre>"

        diff_text.setHtml(html)

        diff_lines = len(
            [
                l
                for l in self.item["diff"]
                if not (l.startswith("---") or l.startswith("+++") or l.startswith("@@"))
            ]
        )
        extra_h = 22 if any(len(l) > 100 for l in self.item["diff"]) else 0
        diff_text.setFixedHeight(min(400, max(50, diff_lines * 18 + 24 + extra_h)))

        layout.addWidget(diff_text)

    def _render_already_applied(self, layout: QVBoxLayout) -> None:
        """Отрисовка карточки уже применённой операции."""
        info_layout = QHBoxLayout()
        icon_lbl = QLabel("i")
        icon_lbl.setStyleSheet("font-size: 28px; color: #3498db;")
        info_layout.addWidget(icon_lbl)

        text_layout = QVBoxLayout()
        lbl_msg = QLabel("Изменения не требуются")
        lbl_msg.setStyleSheet("color: #3498db; font-weight: bold; font-size: 14px;")
        text_layout.addWidget(lbl_msg)

        lbl_sub = QLabel(self.item["error"])
        lbl_sub.setStyleSheet("color: #aaaaaa; font-size: 12px;")
        text_layout.addWidget(lbl_sub)

        info_layout.addLayout(text_layout)
        info_layout.addStretch()
        layout.addLayout(info_layout)

    def _render_error(self, layout: QVBoxLayout) -> None:
        """Отрисовка карточки операции с ошибкой."""
        err_layout = QHBoxLayout()
        err_icon = QLabel("X")
        err_icon.setStyleSheet("font-size: 28px; color: #c0392b;")
        err_layout.addWidget(err_icon)

        err_text_layout = QVBoxLayout()
        lbl_err_title = QLabel("Ошибка применения патча")
        lbl_err_title.setStyleSheet("color: #c0392b; font-weight: bold; font-size: 14px;")
        err_text_layout.addWidget(lbl_err_title)

        lbl_err_desc = QLabel(f"Причина: {self.item['error']}")
        lbl_err_desc.setStyleSheet("color: #e74c3c; font-size: 12px;")
        lbl_err_desc.setWordWrap(True)
        err_text_layout.addWidget(lbl_err_desc)

        err_layout.addLayout(err_text_layout)
        err_layout.addStretch()
        layout.addLayout(err_layout)

        op = self.item["op"]
        search_txt = op.get("search") or op.get("original", "")
        if search_txt:
            lbl_search = QLabel("Искомый текст (от ИИ):")
            lbl_search.setStyleSheet("color: #f39c12; font-weight: bold;")
            layout.addWidget(lbl_search)
            layout.addWidget(self._create_code_viewer(search_txt, max_h=200))

        if self.item["suggestions"]:
            lbl_sug = QLabel("Возможные совпадения в файле:")
            lbl_sug.setStyleSheet("color: #27ae60; font-weight: bold;")
            layout.addWidget(lbl_sug)

            for idx, (ratio, sug_text) in enumerate(self.item["suggestions"]):
                sug_frame = QFrame()
                sug_frame.setStyleSheet(
                    "background-color: #1a1a1a; "
                    "border: 1px solid #3c3c3c; border-radius: 6px;"
                )
                sug_layout = QVBoxLayout(sug_frame)

                top_bar = QHBoxLayout()
                lbl_var = QLabel(
                    f"Вариант {idx + 1} (Совпадение: {int(ratio * 100)}%)"
                )
                lbl_var.setStyleSheet(
                    "color: #aaaaaa; border: none; font-weight: bold;"
                )
                top_bar.addWidget(lbl_var)
                top_bar.addStretch()

                btn_apply_sug = QPushButton("Применить")
                btn_apply_sug.setObjectName("btn_success")
                btn_apply_sug.clicked.connect(
                    lambda checked=False, i=self.item["id"], t=sug_text:
                    self.app.action_apply_suggestion(i, t)
                )
                top_bar.addWidget(btn_apply_sug)
                sug_layout.addLayout(top_bar)

                te_sug = self._create_code_viewer(sug_text, max_h=200)
                te_sug.setStyleSheet(
                    "border: none; padding: 0px; background-color: transparent;"
                )
                sug_layout.addWidget(te_sug)
                layout.addWidget(sug_frame)
