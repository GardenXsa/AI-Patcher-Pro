"""
Модуль применения патчей.

КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: оригинальный код использовал str.replace(),
который заменяет ВСЕ вхождения. Теперь используется replace_first_occurrence(),
которая заменяет только ПЕРВОЕ вхождение, предотвращая повреждение файлов
с повторяющимися фрагментами кода.
"""

from typing import Optional


def replace_first_occurrence(text: str, old: str, new: str) -> str:
    """
    Заменяет ТОЛЬКО первое вхождение подстроки.

    Это критически важно для патчинга кода, где один и тот же фрагмент
    может встречаться несколько раз (например, одинаковые импорты,
    повторяющиеся паттерны и т.д.). Оригинальный str.replace() заменяет
    ВСЕ вхождения, что может привести к непреднамеренному повреждению файлов.

    Args:
        text: Исходный текст.
        old: Искомый фрагмент (найденный SearchEngine).
        new: Заменяющий фрагмент.

    Returns:
        Текст с заменённым первым вхождением.

    Raises:
        ValueError: Если искомый фрагмент не найден.
    """
    idx = text.find(old)
    if idx == -1:
        raise ValueError(
            "Внутренняя ошибка: SearchEngine вернул фрагмент, "
            "который не найден в файле. Это баг — сообщите разработчикам."
        )
    return text[:idx] + new + text[idx + len(old):]


def apply_single_operation(
    old_content: str,
    action: str,
    search_text: str,
    content: str,
    actual_search: Optional[str] = None,
) -> str:
    """
    Применяет одну операцию патча к содержимому файла.

    Использует replace_first_occurrence() вместо str.replace() для
    безопасного патчинга — заменяется только первое вхождение.

    Args:
        old_content: Текущее содержимое файла.
        action: Тип действия (replace, insert_after, insert_before, delete,
                append, prepend, create_file).
        search_text: Оригинальный искомый текст (от ИИ).
        content: Новый контент для вставки/замены.
        actual_search: Реально найденный в файле текст (от SearchEngine).
            Если None, используется search_text.

    Returns:
        Новое содержимое файла после применения операции.

    Raises:
        ValueError: Если действие неизвестно или некорректно.
    """
    search = actual_search if actual_search is not None else search_text

    if action == "replace":
        return replace_first_occurrence(old_content, search, content)

    elif action == "insert_after":
        replacement = search + "\n" + content
        return replace_first_occurrence(old_content, search, replacement)

    elif action == "insert_before":
        replacement = content + "\n" + search
        return replace_first_occurrence(old_content, search, replacement)

    elif action == "delete":
        return replace_first_occurrence(old_content, search, "")

    elif action == "append":
        return old_content + "\n" + content

    elif action == "prepend":
        return content + "\n" + old_content

    elif action == "create_file":
        return content

    else:
        raise ValueError(f"Неизвестное действие: {action}")


def normalize_operation_fields(op: dict) -> dict:
    """
    Нормализует имена полей операции от ИИ.

    ИИ может использовать разные имена полей: path/file, action/op,
    search/original/find, content/text/code. Эта функция приводит их
    к стандартному виду.

    Args:
        op: Словарь операции от ИИ.

    Returns:
        Нормализованный словарь с едиными ключами.
    """
    return {
        "path": op.get("path") or op.get("file", "unknown"),
        "action": op.get("action") or op.get("op", "unknown"),
        "search": op.get("search") or op.get("original") or op.get("find", ""),
        "content": op.get("content") or op.get("text") or op.get("code", ""),
    }
