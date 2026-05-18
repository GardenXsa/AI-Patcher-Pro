"""
Виджет просмотра кода с подсветкой синтаксиса.

ИСПРАВЛЕНО: оригинальный код перезаписывал self.highlighter при каждом
вызове create_code_viewer(), что приводило к garbage collection
предыдущих хайлайтеров и потере подсветки. Теперь хайлайтеры хранятся
в списке _highlighters.
"""

import re
from typing import List

from PyQt6.QtWidgets import QTextEdit
from PyQt6.QtGui import (
    QFont,
    QColor,
    QSyntaxHighlighter,
    QTextCharFormat,
)
from PyQt6.QtCore import Qt


class CodeHighlighter(QSyntaxHighlighter):
    """Подсветка синтаксиса для JSON, Python и JavaScript."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rules: List[tuple] = []

        # Ключи JSON ("key":)
        fmt_key = QTextCharFormat()
        fmt_key.setForeground(QColor("#9cdcfe"))
        self.rules.append((re.compile(r'"[^"\\]*"\s*:'), fmt_key))

        # Строки ("value" или 'value')
        fmt_str = QTextCharFormat()
        fmt_str.setForeground(QColor("#ce9178"))
        self.rules.append((re.compile(r'"[^"\\]*"'), fmt_str))
        self.rules.append((re.compile(r"'[^'\\]*'"), fmt_str))

        # Ключевые слова Python / JS / JSON
        fmt_kw = QTextCharFormat()
        fmt_kw.setForeground(QColor("#569cd6"))
        fmt_kw.setFontWeight(QFont.Weight.Bold)
        kws = [
            r"\btrue\b", r"\bfalse\b", r"\bnull\b",
            r"\bdef\b", r"\bclass\b", r"\bimport\b",
            r"\breturn\b", r"\bif\b", r"\belse\b",
            r"\belif\b", r"\bfor\b",
        ]
        for kw in kws:
            self.rules.append((re.compile(kw), fmt_kw))

        # Комментарии (# или //)
        fmt_comment = QTextCharFormat()
        fmt_comment.setForeground(QColor("#6a9955"))
        fmt_comment.setFontItalic(True)
        self.rules.append((re.compile(r"#.*"), fmt_comment))
        self.rules.append((re.compile(r"//.*"), fmt_comment))

    def highlightBlock(self, text: str) -> None:
        """Применяет правила подсветки к блоку текста."""
        for regex, fmt in self.rules:
            for match in regex.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)


class CodeViewerFactory:
    """
    Фабрика для создания виджетов просмотра кода.

    ИСПРАВЛЕНО: хранит все созданные хайлайтеры в списке, предотвращая
    их garbage collection PyQt6 (который использует слабые ссылки).
    """

    def __init__(self):
        self._highlighters: List[CodeHighlighter] = []

    def create_code_viewer(self, text: str, max_h: int = 250) -> QTextEdit:
        """
        Создаёт виджет просмотра кода с подсветкой синтаксиса.

        Args:
            text: Текст для отображения.
            max_h: Максимальная высота виджета.

        Returns:
            Настроенный QTextEdit с подсветкой.
        """
        te = QTextEdit()
        te.setPlainText(text)
        te.setReadOnly(True)
        te.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)

        # Создаём новый хайлайтер и сохраняем ссылку
        highlighter = CodeHighlighter(te.document())
        self._highlighters.append(highlighter)

        # Автоподбор высоты
        lines = text.count("\n") + 1
        has_long_lines = any(len(line) > 100 for line in text.split("\n"))
        extra_h = 22 if has_long_lines else 0
        te.setFixedHeight(min(max_h, max(40, lines * 16 + 24 + extra_h)))

        return te

    def clear(self) -> None:
        """Очищает список хайлайтеров (при сбросе UI)."""
        self._highlighters.clear()
