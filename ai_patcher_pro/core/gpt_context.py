"""
Утилиты GPT-контекста для AI Patcher Pro.

Система:
- GitHub остаётся главным источником актуального кода.
- local_diff.txt показывает локальные изменения, которых ещё нет в GitHub.
- Project_scan.txt нужен как полный резервный снимок проекта.
- GPT_TASK.md хранит текущую задачу для модели.
- PATCH_RESULT.md хранит результат применения патча/проверок.
"""

import os
import subprocess
from datetime import datetime
from typing import Dict, List, Optional, Tuple


CONTEXT_FILES = (
    "Project_scan.txt",
    "local_diff.txt",
    "GPT_TASK.md",
    "PATCH_RESULT.md",
)

GITIGNORE_HEADER = "# AI Patcher Pro GPT context files"


def write_text_file(root_path: str, filename: str, content: str) -> str:
    """Записывает текстовый файл в корень проекта и возвращает полный путь."""
    path = os.path.join(root_path, filename)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    return path


def write_text_file_if_missing(root_path: str, filename: str, content: str) -> str:
    """Создаёт файл только если его ещё нет, чтобы не затереть заметки пользователя."""
    path = os.path.join(root_path, filename)
    if not os.path.exists(path):
        write_text_file(root_path, filename, content)
    return path


def _run_git(root_path: str, args: List[str], timeout: int = 30) -> Tuple[int, str, str]:
    """Безопасно выполняет git-команду и возвращает returncode/stdout/stderr."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=root_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except FileNotFoundError:
        return 127, "", "git не найден в PATH. Установите Git или запускайте без local_diff.txt."
    except subprocess.TimeoutExpired:
        return 124, "", f"git {' '.join(args)} превысил таймаут {timeout} сек."
    except OSError as e:
        return 1, "", f"Ошибка запуска git: {e}"


def _fence(language: str, content: str) -> str:
    """Возвращает markdown-блок на тильдах, чтобы не ломать парсер JSON-патчей."""
    return f"~~~{language}\n{content.rstrip()}\n~~~"


def build_local_diff_text(root_path: str) -> str:
    """Формирует local_diff.txt: статус git + unstaged/staged diff."""
    project_name = os.path.basename(os.path.normpath(root_path)) or root_path
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    parts = [
        "# local_diff.txt",
        "",
        f"Project: {project_name}",
        f"Created: {created_at}",
        "",
        "Этот файл показывает локальные изменения, которых может не быть в GitHub.",
        "Если GitHub уже актуален и локальных изменений нет, этот файл можно не давать GPT.",
        "",
    ]

    status_rc, status_out, status_err = _run_git(root_path, ["status", "--short"])
    if status_rc != 0:
        parts.extend([
            "## Git status недоступен",
            "",
            "AI Patcher Pro не смог получить git status для этой папки.",
            "Возможно, это не git-репозиторий или Git не установлен.",
            "",
        ])
        if status_err.strip():
            parts.extend([_fence("text", status_err), ""])
        return "\n".join(parts).rstrip() + "\n"

    parts.extend([
        "## Git status --short",
        "",
        _fence("text", status_out or "(локальных изменений нет)"),
        "",
    ])

    diff_rc, diff_out, diff_err = _run_git(root_path, ["diff", "--"])
    parts.extend(["## Git diff", ""])
    if diff_rc == 0:
        parts.extend([_fence("diff", diff_out or "(нет unstaged изменений)"), ""])
    else:
        parts.extend([_fence("text", diff_err or "Не удалось получить git diff."), ""])

    staged_rc, staged_out, staged_err = _run_git(root_path, ["diff", "--cached", "--"])
    parts.extend(["## Git diff --cached", ""])
    if staged_rc == 0:
        parts.extend([_fence("diff", staged_out or "(нет staged изменений)"), ""])
    else:
        parts.extend([_fence("text", staged_err or "Не удалось получить staged diff."), ""])

    return "\n".join(parts).rstrip() + "\n"


def build_task_template(project_name: str) -> str:
    """Шаблон GPT_TASK.md для текущей задачи."""
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"""# GPT_TASK.md

Project: {project_name}
Created: {created_at}

## Задача
Опиши здесь, что нужно сделать.

## Источник контекста
- GitHub — основной источник актуального кода.
- local_diff.txt — локальные незакоммиченные изменения.
- Project_scan.txt — полный снимок проекта, если GitHub-контекста недостаточно.
- PATCH_RESULT.md — результат прошлого применения патча и тестов.

## Правила для GPT
- Отвечай JSON-патчем для AI Patcher Pro.
- Не предлагай Codex.
- Для команд используй `py -m ...` на Windows, если нужна команда Python.
- Не ломай существующую архитектуру без необходимости.
- Если нужно изменить несколько файлов, делай это одним патчем.

## Что проверить после патча
- Запустить релевантные тесты.
- Проверить, что команда работает из корня проекта.
"""


def build_patch_result_template(project_name: str) -> str:
    """Шаблон PATCH_RESULT.md, если реального отчёта ещё нет."""
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"""# PATCH_RESULT.md

Project: {project_name}
Created: {created_at}

Пока нет результата применения патча.

После применения патча сюда можно сохранить:
- какие операции были применены;
- какие команды запускались;
- stdout/stderr;
- список ошибок, если они были.
"""


def ensure_context_gitignore(root_path: str) -> str:
    """Добавляет GPT context files в .gitignore без дублей."""
    gitignore_path = os.path.join(root_path, ".gitignore")

    try:
        with open(gitignore_path, "r", encoding="utf-8", errors="replace") as f:
            existing = f.read()
    except OSError:
        existing = ""

    existing_lines = {line.strip() for line in existing.splitlines()}
    missing = [name for name in CONTEXT_FILES if name not in existing_lines]

    if not missing:
        return gitignore_path

    new_text = existing
    if new_text and not new_text.endswith("\n"):
        new_text += "\n"

    if GITIGNORE_HEADER not in existing:
        if new_text:
            new_text += "\n"
        new_text += GITIGNORE_HEADER + "\n"

    for name in missing:
        new_text += name + "\n"

    with open(gitignore_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(new_text)

    return gitignore_path


def save_gpt_context_bundle(
    root_path: str,
    scan_context: Optional[str] = None,
    patch_result_text: Optional[str] = None,
) -> Dict[str, str]:
    """
    Создаёт GPT-пакет в корне проекта.

    Project_scan.txt и local_diff.txt перезаписываются, потому что это снимки.
    GPT_TASK.md и PATCH_RESULT.md не затираются, если пользователь уже внёс туда заметки.
    """
    project_name = os.path.basename(os.path.normpath(root_path)) or root_path
    written: Dict[str, str] = {}

    if scan_context is not None:
        written["Project_scan.txt"] = write_text_file(
            root_path,
            "Project_scan.txt",
            scan_context,
        )

    written["local_diff.txt"] = write_text_file(
        root_path,
        "local_diff.txt",
        build_local_diff_text(root_path),
    )

    written["GPT_TASK.md"] = write_text_file_if_missing(
        root_path,
        "GPT_TASK.md",
        build_task_template(project_name),
    )

    if patch_result_text is not None:
        written["PATCH_RESULT.md"] = write_text_file(
            root_path,
            "PATCH_RESULT.md",
            patch_result_text,
        )
    else:
        written["PATCH_RESULT.md"] = write_text_file_if_missing(
            root_path,
            "PATCH_RESULT.md",
            build_patch_result_template(project_name),
        )

    written[".gitignore"] = ensure_context_gitignore(root_path)
    return written
