"""
Парсер JSON из ответов ИИ.

Умеет извлекать JSON из Markdown-блоков, автофиксить висячие запятые,
поддерживать альтернативные имена полей и извлекать консольные команды.
"""

import json
import re
from typing import Any, Dict, List

from ai_patcher_pro.core.command_utils import normalize_command


def extract_all_json(raw_text: str) -> Dict[str, Any]:
    """
    Умный Markdown-парсер: извлекает ВСЕ JSON блоки и склеивает их.

    ИИ может писать текст до, после и между блоками. Эта функция
    находит все JSON-структуры и объединяет их в один набор операций.

    Обрабатывает следующие форматы:
    - Markdown code blocks: ```json ... ```
    - Raw JSON arrays: [...]
    - Raw JSON objects with "operations" key
    - Single operation objects with "action"/"op" key

    Args:
        raw_text: Сырой текст ответа ИИ.

    Returns:
        Словарь с ключами:
        - patch_name: Имя патча.
        - operations: Список операций.
        - commands: Список нормализованных консольных команд.

    Raises:
        ValueError: Если JSON структура не найдена.
    """
    operations: List[Dict] = []
    patch_name = "Сборный патч"
    raw_commands: List = []

    # Ищем все блоки кода
    blocks = re.findall(
        r"```(?:json)?\s*([\s\S]*?)\s*```", raw_text, re.IGNORECASE
    )

    # Если блоков нет, пытаемся найти структуру просто в тексте
    if not blocks:
        start_candidates = [
            x for x in [raw_text.find("["), raw_text.find("{")] if x != -1
        ]
        if start_candidates:
            start_idx = min(start_candidates)
            end_idx = max(raw_text.rfind("]"), raw_text.rfind("}"))
            if start_idx != -1 and end_idx > start_idx:
                blocks = [raw_text[start_idx : end_idx + 1]]

    for block in blocks:
        # Фикс висячих запятых от ИИ (частая ошибка LLM)
        block = re.sub(r",(\s*[\]}])", r"\1", block)
        try:
            data = json.loads(block, strict=False)
            if isinstance(data, list):
                operations.extend(data)
            elif isinstance(data, dict):
                if "operations" in data:
                    operations.extend(data["operations"])
                    if "patch_name" in data:
                        patch_name = data["patch_name"]
                    # Извлекаем команды из верхнего уровня
                    raw_commands.extend(_extract_raw_commands(data))
                elif "action" in data or "op" in data:
                    operations.append(data)
                elif "commands" in data or "cmds" in data or "exec" in data:
                    # Объект содержит только команды без операций
                    raw_commands.extend(_extract_raw_commands(data))
        except json.JSONDecodeError:
            continue

    if not operations and not raw_commands:
        raise ValueError(
            "JSON структура не найдена. "
            "Убедитесь, что текст содержит валидный JSON."
        )

    # Нормализуем команды
    commands = []
    for cmd_raw in raw_commands:
        normalized = normalize_command(cmd_raw)
        if normalized["cmd"]:  # Пропускаем пустые команды
            commands.append(normalized)

    return {
        "patch_name": patch_name,
        "operations": operations,
        "commands": commands,
    }


def _extract_raw_commands(data: dict) -> List:
    """
    Извлекает сырые команды из объекта верхнего уровня.

    Поддерживаемые ключи: commands, cmds, exec, run_commands, post_commands.
    Форматы значений:
    - Строка: "npm install"
    - Массив строк: ["cmd1", "cmd2"]
    - Массив объектов: [{"cmd": "...", "run": "..."}]
    - Один объект: {"cmd": "...", "run": "..."}

    Args:
        data: Словарь верхнего уровня патча.

    Returns:
        Список сырых команд (строки или словари).
    """
    commands_value = (
        data.get("commands")
        or data.get("cmds")
        or data.get("exec")
        or data.get("run_commands")
        or data.get("post_commands")
    )

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

    return []
