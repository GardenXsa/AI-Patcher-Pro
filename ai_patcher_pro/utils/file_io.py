"""Утилиты для работы с файлами: мульти-кодировочное чтение и запись."""

from typing import Optional


# Поддерживаемые кодировки в порядке приоритета
DEFAULT_ENCODINGS = ("utf-8", "cp1251", "latin-1")


def read_file_safe(path: str, encodings: tuple = DEFAULT_ENCODINGS) -> str:
    """
    Безопасное чтение файла с автоматическим определением кодировки.

    Пробует кодировки по порядку, пока не найдёт подходящую.
    Это необходимо, так как ИИ может работать с файлами
    в различных кодировках (особенно на Windows).

    Args:
        path: Абсолютный путь к файлу.
        encodings: Кортеж кодировок для попытки чтения.

    Returns:
        Содержимое файла как строка.

    Raises:
        FileNotFoundError: Если файл не существует.
        ValueError: Если ни одна кодировка не подошла.
    """
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue

    raise ValueError(f"Не удалось определить кодировку файла: {path}")


def write_file_safe(path: str, content: str, encoding: str = "utf-8") -> None:
    """
    Безопасная запись файла с созданием директорий.

    Args:
        path: Абсолютный путь к файлу.
        content: Содержимое для записи.
        encoding: Кодировка для записи (по умолчанию utf-8).
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding=encoding) as f:
        f.write(content)


import os
