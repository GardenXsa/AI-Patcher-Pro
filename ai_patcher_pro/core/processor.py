"""
Фоновый поток обработки операций.

Выполняет оценку каждой операции (поиск, вычисление diff) в фоне,
чтобы не блокировать GUI. Использует виртуальную файловую систему
для накопления изменений в памяти перед записью на диск.

Сигналы реального времени:
- status_update: промежуточные статусы каждой стадии обработки
- operation_done: завершение обработки одной операции
- finished_all: завершение всех операций
"""

import os
import difflib
from typing import Dict, List

from PyQt6.QtCore import QThread, pyqtSignal

from ai_patcher_pro.core.search import SearchEngine
from ai_patcher_pro.core.patcher import apply_single_operation, normalize_operation_fields
from ai_patcher_pro.core.security import secure_path_join
from ai_patcher_pro.utils.file_io import read_file_safe


class ProcessorThread(QThread):
    """
    Фоновый поток для обработки операций патча.

    Сигналы:
        status_update: Промежуточный статус (stage, message, detail).
            stage: "parse" | "load" | "search" | "apply" | "diff" | "done"
            message: Человекочитаемое описание текущего шага.
            detail: Дополнительная информация (путь к файлу и т.д.)
        operation_done: Отправляется после обработки каждой операции.
        finished_all: Отправляется после завершения всех операций.
    """

    status_update = pyqtSignal(str, str, str)  # stage, message, detail
    operation_done = pyqtSignal(dict)
    finished_all = pyqtSignal(dict)

    def __init__(
        self,
        workspace: str,
        pending_ops: List[Dict],
        current_cache: Dict[str, str],
    ):
        """
        Args:
            workspace: Рабочая директория проекта.
            pending_ops: Список операций для обработки.
            current_cache: Текущий кэш виртуальной файловой системы.
        """
        super().__init__()
        self.workspace = workspace
        self.pending_ops = pending_ops
        self._cache = current_cache.copy()

    def run(self) -> None:
        """Выполняет обработку всех операций."""
        total = len(self.pending_ops)
        self.status_update.emit(
            "parse",
            f"Начинаем анализ {total} операций...",
            ""
        )

        for i, item in enumerate(self.pending_ops):
            op = item["op"]
            file_hint = op.get("path") or op.get("file", "?")
            action_hint = op.get("action") or op.get("op", "?")

            self.status_update.emit(
                "load",
                f"Анализ операции {i + 1}/{total}",
                f"{action_hint} → {file_hint}"
            )

            res = self._evaluate_single_op(item)
            self.operation_done.emit(res)

        self.status_update.emit(
            "done",
            f"Анализ завершён: {total} операций обработано",
            ""
        )
        self.finished_all.emit(self._cache)

    def _evaluate_single_op(self, item: Dict) -> Dict:
        """
        Оценивает одну операцию патча.

        Выполняет:
        1. Безопасное разрешение пути
        2. Чтение файла (с фоллбэком кодировки)
        3. Поиск целевого кода (5-уровневый алгоритм)
        4. Применение операции в виртуальной файловой системе
        5. Генерацию unified diff

        Args:
            item: Словарь операции {'id': int, 'op': dict}.

        Returns:
            Результат операции с полями:
            id, op, status, error, diff, suggestions, search_method.
        """
        op = item["op"]
        normalized = normalize_operation_fields(op)
        rel_path = normalized["path"]

        res: Dict = {
            "id": item["id"],
            "op": op,
            "status": "success",
            "error": "",
            "diff": [],
            "suggestions": [],
            "search_method": "",
        }

        # Безопасное разрешение пути
        try:
            abs_p = secure_path_join(self.workspace, rel_path)
        except (PermissionError, ValueError) as e:
            res["status"] = "error"
            res["error"] = str(e)
            return res

        # Загрузка файла в виртуальную файловую систему
        if abs_p not in self._cache:
            self.status_update.emit(
                "load",
                f"Загрузка файла: {rel_path}",
                abs_p
            )
            if os.path.exists(abs_p):
                try:
                    self._cache[abs_p] = read_file_safe(abs_p)
                except (OSError, ValueError) as e:
                    res["status"] = "error"
                    res["error"] = f"Ошибка чтения: {e}"
                    return res
            else:
                self._cache[abs_p] = ""

        old_c = self._cache[abs_p]
        action = normalized["action"]
        search = normalized["search"]
        content = normalized["content"]

        virtual_exists = bool(old_c) or os.path.exists(abs_p)

        if action != "create_file" and not virtual_exists:
            res["status"] = "error"
            res["error"] = "Файл не найден на диске."
            return res

        try:
            # Поиск кода
            if action not in ("create_file", "append", "prepend") and search:
                self.status_update.emit(
                    "search",
                    f"Поиск кода в {rel_path}",
                    f"Длина запроса: {len(search)} символов"
                )

            new_c = self._apply_action(
                old_c, action, search, content, res
            )

            # Генерация diff
            self.status_update.emit(
                "diff",
                f"Генерация diff: {rel_path}",
                ""
            )

            diff_lines = list(
                difflib.unified_diff(
                    old_c.splitlines(), new_c.splitlines(), n=2, lineterm=""
                )
            )

            if not diff_lines and action != "create_file":
                res["status"] = "already_applied"
                res["error"] = "Изменений нет. Код идентичен."

            res["diff"] = diff_lines
            self._cache[abs_p] = new_c

        except ValueError as e:
            res["status"] = "error"
            res["error"] = str(e)
        except Exception as e:
            res["status"] = "error"
            res["error"] = f"Непредвиденная ошибка: {e}"

        return res

    def _apply_action(
        self,
        old_c: str,
        action: str,
        search: str,
        content: str,
        res: Dict,
    ) -> str:
        """
        Применяет действие к содержимому файла.

        Args:
            old_c: Текущее содержимое.
            action: Тип действия.
            search: Искомый текст.
            content: Новый контент.
            res: Словарь результата (модифицируется in-place).

        Returns:
            Новое содержимое файла.
        """
        if action == "create_file":
            res["search_method"] = "Создание файла"
            return content

        elif action in ("replace", "insert_after", "insert_before", "delete"):
            if not search and action != "delete":
                raise ValueError("Отсутствует поле 'search'")

            # Для delete с пустым search — текст уже отсутствует
            if not search and action == "delete":
                res["status"] = "already_applied"
                res["error"] = "Текст уже отсутствует."
                return old_c

            actual_search, suggestions, method_name = SearchEngine.multi_tier_search(
                old_c, search
            )
            res["search_method"] = method_name

            if not actual_search:
                # Проверяем, не применены ли уже изменения
                if content and content.strip() and content.strip() in old_c:
                    res["status"] = "already_applied"
                    res["error"] = "Изменения уже присутствуют."
                    return old_c
                elif action == "delete":
                    res["status"] = "already_applied"
                    res["error"] = "Текст уже отсутствует."
                    return old_c
                else:
                    res["suggestions"] = suggestions
                    raise ValueError("Текст не найден. ИИ галлюцинирует.")

            # ИСПРАВЛЕНО: используем apply_single_operation вместо str.replace()
            return apply_single_operation(old_c, action, search, content, actual_search)

        elif action == "append":
            res["search_method"] = "Добавление в конец"
            return old_c + "\n" + content

        elif action == "prepend":
            res["search_method"] = "Добавление в начало"
            return content + "\n" + old_c

        else:
            raise ValueError(f"Неизвестное действие: {action}")
