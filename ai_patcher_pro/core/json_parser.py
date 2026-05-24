"""
Парсер JSON из ответов ИИ.

Цель: принимать не только идеальный JSON, но и типичные кривые ответы LLM:
- Markdown-блоки ```json, ```json id="...", ~~~json;
- текст до/после JSON;
- несколько JSON-блоков в одном ответе;
- висячие запятые;
- // и /* */ комментарии вне строк;
- Python-style dict/list: одинарные кавычки, True/False/None;
- случайные реальные переводы строк внутри JSON-строк;
- command-only патчи без operations.
"""

from __future__ import annotations

import ast
import json
import re
from typing import Any, Dict, Iterable, List, Tuple

from ai_patcher_pro.core.command_utils import normalize_command


COMMAND_KEYS = ("commands", "cmds", "exec", "run_commands", "post_commands")
OPERATION_KEYS = ("operations", "ops", "patch", "changes", "edits")


class JSONRepairError(ValueError):
    """Ошибка восстановления JSON."""


def extract_all_json(raw_text: str) -> Dict[str, Any]:
    """
    Умный Markdown/JSON-парсер: извлекает все JSON-like структуры и склеивает их.

    Args:
        raw_text: Сырой текст ответа ИИ.

    Returns:
        Словарь с ключами:
        - patch_name: Имя патча.
        - operations: Список операций.
        - commands: Список нормализованных консольных команд.

    Raises:
        ValueError: Если JSON/Python-like структура не найдена или не распознана.
    """
    raw_text = _strip_invisible_chars(raw_text or "")

    operations: List[Dict[str, Any]] = []
    patch_name = "Сборный патч"
    raw_commands: List[Any] = []
    parse_errors: List[str] = []

    blocks = list(_iter_candidate_blocks(raw_text))

    for block in blocks:
        try:
            data = _loads_lenient(block)
        except Exception as e:
            parse_errors.append(str(e))
            continue

        patch_name = _collect_patch_data(
            data=data,
            operations=operations,
            raw_commands=raw_commands,
            current_patch_name=patch_name,
        )

    if not operations and not raw_commands:
        details = ""
        if parse_errors:
            unique_errors = []
            for err in parse_errors:
                if err not in unique_errors:
                    unique_errors.append(err)
            details = "\n\nПоследние ошибки парсинга:\n- " + "\n- ".join(unique_errors[:5])

        raise ValueError(
            "JSON структура не найдена. "
            "Вставьте JSON-патч, массив операций или command-only объект."
            + details
        )

    commands = []
    for cmd_raw in raw_commands:
        normalized = normalize_command(cmd_raw)
        if normalized["cmd"]:
            commands.append(normalized)

    return {
        "patch_name": patch_name,
        "operations": operations,
        "commands": commands,
    }


def _iter_candidate_blocks(raw_text: str) -> Iterable[str]:
    """Возвращает кандидаты на JSON: fenced-блоки, затем balanced raw JSON."""
    yielded = set()

    # Markdown fences: ```json, ```json id="...", ~~~json, без языка тоже.
    fence_re = re.compile(
        r"(?ms)(`{3}|~{3})[^\r\n]*(?:\r?\n)(.*?)(?:\r?\n)?\1"
    )
    for match in fence_re.finditer(raw_text):
        block = match.group(2).strip()
        if block and block not in yielded:
            yielded.add(block)
            yield block

    # Если fenced-блоков нет или внутри текста есть ещё JSON — ищем сбалансированные
    # объекты/массивы. Это лучше, чем raw_text[min([,{]) : max(]})].
    for block in _extract_balanced_structures(raw_text):
        block = block.strip()
        if block and block not in yielded:
            yielded.add(block)
            yield block

    # Последняя попытка: весь текст как единый JSON-like блок.
    whole = raw_text.strip()
    if whole and whole not in yielded:
        yield whole


def _extract_balanced_structures(text: str) -> List[str]:
    """Извлекает сбалансированные {...} и [...] с учётом строк."""
    result: List[str] = []
    stack: List[str] = []
    start = None
    quote = ""
    escaped = False

    pairs = {"{": "}", "[": "]"}
    closers = set(pairs.values())

    for i, ch in enumerate(text):
        if quote:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = ""
            continue

        if ch in ('"', "'"):
            quote = ch
            continue

        if ch in pairs:
            if not stack:
                start = i
            stack.append(pairs[ch])
            continue

        if ch in closers and stack:
            expected = stack.pop()
            if ch != expected:
                stack.clear()
                start = None
                continue
            if not stack and start is not None:
                result.append(text[start : i + 1])
                start = None

    return result


def _loads_lenient(block: str) -> Any:
    """Парсит JSON/Python-like блок несколькими стратегиями."""
    candidates = _build_repair_candidates(block)
    errors: List[str] = []

    for candidate in candidates:
        try:
            return json.loads(candidate, strict=False)
        except json.JSONDecodeError as e:
            errors.append(f"json: {e.msg} at line {e.lineno} col {e.colno}")

    for candidate in candidates:
        try:
            value = ast.literal_eval(_json_literals_to_python(candidate))
            return _convert_python_literals(value)
        except (SyntaxError, ValueError, TypeError) as e:
            errors.append(f"python-like: {e}")

    unique = []
    for err in errors:
        if err not in unique:
            unique.append(err)
    raise JSONRepairError("Не удалось распарсить блок: " + "; ".join(unique[:3]))


def _build_repair_candidates(block: str) -> List[str]:
    """Создаёт варианты восстановления от менее агрессивного к более агрессивному."""
    text = _strip_invisible_chars(block).strip()
    text = _strip_surrounding_language_line(text)

    candidates = []

    def add(value: str) -> None:
        value = value.strip()
        if value and value not in candidates:
            candidates.append(value)

    add(text)

    repaired = _normalize_smart_quotes(text)
    repaired = _strip_json_comments(repaired)
    repaired = _escape_control_chars_inside_strings(repaired)
    repaired = _remove_trailing_commas(repaired)
    repaired = _python_literals_to_json(repaired)
    add(repaired)

    # Более агрессивно: поддержка action: "..." при забытых кавычках у ключей.
    quoted_keys = _quote_unquoted_object_keys(repaired)
    add(quoted_keys)

    return candidates


def _strip_surrounding_language_line(text: str) -> str:
    """Убирает одиночную строку языка, если пользователь скопировал внутренности fence криво."""
    lines = text.splitlines()
    if len(lines) > 1 and re.fullmatch(r"\s*(json|javascript|js|python|py)\b.*", lines[0], re.I):
        return "\n".join(lines[1:]).strip()
    return text


def _strip_invisible_chars(text: str) -> str:
    """Убирает BOM и zero-width символы."""
    return (
        text.replace("\ufeff", "")
        .replace("\u200b", "")
        .replace("\u200c", "")
        .replace("\u200d", "")
    )


def _normalize_smart_quotes(text: str) -> str:
    """Нормализует типографские кавычки."""
    return (
        text.replace("“", '"')
        .replace("”", '"')
        .replace("„", '"')
        .replace("«", '"')
        .replace("»", '"')
        .replace("‘", "'")
        .replace("’", "'")
    )


def _strip_json_comments(text: str) -> str:
    """Удаляет //, # и /* */ комментарии вне строк."""
    out: List[str] = []
    i = 0
    quote = ""
    escaped = False

    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""

        if quote:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = ""
            i += 1
            continue

        if ch in ('"', "'"):
            quote = ch
            out.append(ch)
            i += 1
            continue

        if ch == "/" and nxt == "/":
            i += 2
            while i < len(text) and text[i] not in "\r\n":
                i += 1
            continue

        if ch == "#":
            i += 1
            while i < len(text) and text[i] not in "\r\n":
                i += 1
            continue

        if ch == "/" and nxt == "*":
            i += 2
            while i + 1 < len(text) and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue

        out.append(ch)
        i += 1

    return "".join(out)


def _escape_control_chars_inside_strings(text: str) -> str:
    """Экранирует реальные \n/\r/\t внутри строк, частую ошибку LLM."""
    out: List[str] = []
    quote = ""
    escaped = False

    for ch in text:
        if quote:
            if escaped:
                out.append(ch)
                escaped = False
                continue
            if ch == "\\":
                out.append(ch)
                escaped = True
                continue
            if ch == quote:
                out.append(ch)
                quote = ""
                continue
            if ch == "\n":
                out.append("\\n")
                continue
            if ch == "\r":
                out.append("\\r")
                continue
            if ch == "\t":
                out.append("\\t")
                continue
            out.append(ch)
            continue

        if ch in ('"', "'"):
            quote = ch
        out.append(ch)

    return "".join(out)


def _remove_trailing_commas(text: str) -> str:
    """Удаляет висячие запятые перед } или ]."""
    return re.sub(r",\s*([}\]])", r"\1", text)


def _replace_literals_outside_strings(text: str, replacements: Dict[str, str]) -> str:
    """Заменяет токены вне строк."""
    out: List[str] = []
    token: List[str] = []
    quote = ""
    escaped = False

    def flush_token() -> None:
        if not token:
            return
        value = "".join(token)
        out.append(replacements.get(value, value))
        token.clear()

    for ch in text:
        if quote:
            flush_token()
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = ""
            continue

        if ch in ('"', "'"):
            flush_token()
            quote = ch
            out.append(ch)
            continue

        if ch.isalpha() or ch == "_":
            token.append(ch)
        else:
            flush_token()
            out.append(ch)

    flush_token()
    return "".join(out)


def _python_literals_to_json(text: str) -> str:
    """True/False/None -> true/false/null вне строк."""
    return _replace_literals_outside_strings(
        text,
        {"True": "true", "False": "false", "None": "null"},
    )


def _json_literals_to_python(text: str) -> str:
    """true/false/null -> True/False/None вне строк для ast.literal_eval."""
    return _replace_literals_outside_strings(
        text,
        {"true": "True", "false": "False", "null": "None"},
    )


def _quote_unquoted_object_keys(text: str) -> str:
    """Кавычит простые unquoted object keys вне строк: { path: ... } -> { "path": ... }."""
    out: List[str] = []
    i = 0
    quote = ""
    escaped = False
    expecting_key = False

    while i < len(text):
        ch = text[i]

        if quote:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = ""
            i += 1
            continue

        if ch in ('"', "'"):
            quote = ch
            out.append(ch)
            i += 1
            continue

        if ch in "{,":
            expecting_key = True
            out.append(ch)
            i += 1
            continue

        if expecting_key and ch.isspace():
            out.append(ch)
            i += 1
            continue

        if expecting_key and (ch.isalpha() or ch == "_"):
            start = i
            i += 1
            while i < len(text) and (text[i].isalnum() or text[i] in "_-"):
                i += 1
            key = text[start:i]
            j = i
            while j < len(text) and text[j].isspace():
                j += 1
            if j < len(text) and text[j] == ":":
                out.append(f'"{key}"')
                expecting_key = False
                continue
            out.append(key)
            expecting_key = False
            continue

        if ch == "}":
            expecting_key = False

        out.append(ch)
        i += 1

    return "".join(out)


def _convert_python_literals(value: Any) -> Any:
    """Рекурсивно нормализует ast.literal_eval результат."""
    if isinstance(value, tuple):
        return [_convert_python_literals(v) for v in value]
    if isinstance(value, list):
        return [_convert_python_literals(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _convert_python_literals(v) for k, v in value.items()}
    return value


def _collect_patch_data(
    data: Any,
    operations: List[Dict[str, Any]],
    raw_commands: List[Any],
    current_patch_name: str,
) -> str:
    """Собирает операции и команды из распарсенной структуры."""
    patch_name = current_patch_name

    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                if _looks_like_operation(item):
                    operations.append(item)
                elif _has_command_key(item):
                    raw_commands.extend(_extract_raw_commands(item))
        return patch_name

    if not isinstance(data, dict):
        return patch_name

    if isinstance(data.get("patch_name"), str):
        patch_name = data["patch_name"]

    op_values = []
    for key in OPERATION_KEYS:
        if key in data:
            op_values.append(data[key])

    for value in op_values:
        if isinstance(value, list):
            operations.extend(item for item in value if isinstance(item, dict))
        elif isinstance(value, dict):
            operations.append(value)

    if _looks_like_operation(data):
        operations.append(data)

    raw_commands.extend(_extract_raw_commands(data))
    return patch_name


def _looks_like_operation(data: Dict[str, Any]) -> bool:
    """Проверяет, похож ли объект на одну операцию патча."""
    return bool(
        ("action" in data or "op" in data)
        and ("path" in data or "file" in data)
    )


def _has_command_key(data: Dict[str, Any]) -> bool:
    return any(key in data for key in COMMAND_KEYS)


def _extract_raw_commands(data: dict) -> List[Any]:
    """
    Извлекает сырые команды из объекта верхнего уровня.

    Поддерживаемые ключи: commands, cmds, exec, run_commands, post_commands.
    Форматы значений:
    - Строка: "npm install"
    - Массив строк: ["cmd1", "cmd2"]
    - Массив объектов: [{"cmd": "...", "run": "..."}]
    - Один объект: {"cmd": "...", "run": "..."}
    """
    commands_value = None
    for key in COMMAND_KEYS:
        if key in data:
            commands_value = data.get(key)
            break

    if commands_value is None:
        return []

    if isinstance(commands_value, str):
        return [commands_value]

    if isinstance(commands_value, dict):
        return [commands_value]

    if isinstance(commands_value, list):
        result = []
        for item in commands_value:
            if isinstance(item, (str, dict)):
                result.append(item)
            else:
                result.append(str(item))
        return result

    return [str(commands_value)]
