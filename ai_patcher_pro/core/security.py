"""Безопасность: защита от path traversal и валидация путей."""

import os


def secure_path_join(base_dir: str, relative_path: str) -> str:
    """
    Безопасное объединение путей с защитой от path traversal.

    Проверяет, что результирующий путь находится внутри базовой директории.
    Предотвращает атаки вида '../../etc/passwd'.

    Args:
        base_dir: Базовая директория (рабочая папка проекта).
        relative_path: Относительный путь к файлу.

    Returns:
        Абсолютный безопасный путь.

    Raises:
        PermissionError: Если путь выходит за пределы базовой директории.
        ValueError: Если relative_path пустой.
    """
    if not relative_path or not relative_path.strip():
        raise ValueError("Путь к файлу не может быть пустым.")

    base_dir = os.path.abspath(base_dir)
    # Нормализуем для обработки '..' и символических ссылок
    target_path = os.path.normpath(os.path.abspath(os.path.join(base_dir, relative_path)))

    # Проверяем, что целевой путь начинается с базового
    # Добавляем os.sep чтобы избежать совпадения префиксов
    # например /home/user1 не должен совпадать с /home/user10
    if not (target_path == base_dir or target_path.startswith(base_dir + os.sep)):
        raise PermissionError(
            f"Попытка выхода за пределы рабочей папки: {relative_path}"
        )

    return target_path


def validate_file_extension(path: str, allowed_extensions: tuple | None = None) -> bool:
    """
    Проверяет расширение файла по белому списку.

    Args:
        path: Путь к файлу.
        allowed_extensions: Кортеж разрешённых расширений (с точкой).
            Если None, разрешены все расширения.

    Returns:
        True если расширение разрешено.
    """
    if allowed_extensions is None:
        return True

    ext = os.path.splitext(path)[1].lower()
    return ext in allowed_extensions
