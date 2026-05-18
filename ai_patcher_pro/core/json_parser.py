"""
Парсер JSON из ответов ИИ.

Умеет извлекать JSON из Markdown-блоков, автофиксить висячие запятые
и поддерживать альтернативные имена полей.
"""

import json
import re
from typing import Any, Dict, List


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

    Raises:
        ValueError: Если JSON структура не найдена.
    """
    operations: List[Dict] = []
    patch_name = "Сборный патч"

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
                elif "action" in data or "op" in data:
                    operations.append(data)
        except json.JSONDecodeError:
            continue

    if not operations:
        raise ValueError(
            "JSON структура не найдена. "
            "Убедитесь, что текст содержит валидный JSON."
        )

    return {"patch_name": patch_name, "operations": operations}
