"""
Утилиты для обработки консольных команд.

Содержит функции нормализации команд и обнаружения опасных паттернов.
Не зависит от Qt — может использоваться в парсере и тестах без GUI.
"""

import re
from typing import Dict, List


# Опасные паттерны команд, которые требуют особого внимания
DANGEROUS_PATTERNS = [
    (r"\brm\s+-rf\b", "Удаление директории без подтверждения (rm -rf)"),
    (r"\brmdir\s+/[sS]", "Рекурсивное удаление директории (rmdir /s)"),
    (r"\bdel\s+/[sS]", "Рекурсивное удаление файлов (del /s)"),
    (r"\bformat\s+[A-Za-z]:", "Форматирование диска (format)"),
    (r"\bshutdown\b", "Команда выключения системы (shutdown)"),
    (r"\breboot\b", "Команда перезагрузки системы (reboot)"),
    (r"\bmkfs\b", "Форматирование файловой системы (mkfs)"),
    (r"\bdd\s+if=", "Низкоуровневое копирование диска (dd)"),
    (r"\b>\s*/dev/sd", "Прямая запись на блочное устройство"),
    (r"\bchmod\s+-R\s+777\b", "Установка прав 777 на все файлы (chmod -R 777)"),
    (r"\bchown\s+-R\b", "Рекурсивная смена владельца (chown -R)"),
    (r"\bsudo\s+rm\b", "Удаление с правами суперпользователя (sudo rm)"),
    (r"\btaskkill\s+/[fF]", "Принудительное завершение процессов (taskkill /f)"),
    (r"\breg\s+delete\b", "Удаление записей реестра (reg delete)"),
    (r"\bnet\s+user\b", "Управление пользователями системы (net user)"),
]


def check_dangerous_command(cmd: str) -> List[str]:
    """
    Проверяет команду на наличие опасных паттернов.

    Args:
        cmd: Строка команды для проверки.

    Returns:
        Список описаний обнаруженных опасных паттернов.
    """
    warnings = []
    for pattern, description in DANGEROUS_PATTERNS:
        if re.search(pattern, cmd, re.IGNORECASE):
            warnings.append(description)
    return warnings


def normalize_command(cmd_raw) -> Dict:
    """
    Нормализует описание команды из ответа ИИ.

    Поддерживаемые форматы:
    - Строка: "npm install" → {"cmd": "npm install", "run": "after_apply"}
    - Словарь: {"cmd": "...", "run": "...", "description": "..."}
    - Альтернативные имена: command/exec/shell для cmd,
      timing/when/phase для run, desc/comment/note для description

    Args:
        cmd_raw: Команда в любом поддерживаемом формате.

    Returns:
        Нормализованный словарь команды с ключами:
        cmd, run, description, warnings.
    """
    if isinstance(cmd_raw, str):
        cmd_str = cmd_raw.strip()
        return {
            "cmd": cmd_str,
            "run": "after_apply",
            "description": "",
            "warnings": check_dangerous_command(cmd_str),
        }

    if isinstance(cmd_raw, dict):
        cmd_str = (
            cmd_raw.get("cmd")
            or cmd_raw.get("command")
            or cmd_raw.get("exec")
            or cmd_raw.get("shell")
            or ""
        )
        if isinstance(cmd_str, str):
            cmd_str = cmd_str.strip()
        else:
            cmd_str = str(cmd_str)

        run_val = (
            cmd_raw.get("run")
            or cmd_raw.get("timing")
            or cmd_raw.get("when")
            or cmd_raw.get("phase")
            or "after_apply"
        )
        # Нормализуем значения
        if run_val in ("after_analysis", "analysis", "analyze", "before_apply"):
            run_val = "after_analysis"
        else:
            run_val = "after_apply"

        description = (
            cmd_raw.get("description")
            or cmd_raw.get("desc")
            or cmd_raw.get("comment")
            or cmd_raw.get("note")
            or ""
        )

        return {
            "cmd": cmd_str,
            "run": run_val,
            "description": description,
            "warnings": check_dangerous_command(cmd_str),
        }

    # Неизвестный формат — пробуем как строку
    cmd_str = str(cmd_raw).strip()
    return {
        "cmd": cmd_str,
        "run": "after_apply",
        "description": "",
        "warnings": check_dangerous_command(cmd_str),
    }
