"""
Фоновый поток обработки операций.

Выполняет оценку каждой операции (поиск, вычисление diff) в фоне,
чтобы не блокировать GUI. Использует виртуальную файловую систему
для накопления изменений в памяти перед записью на диск.
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
        operation_done: Отправляется после обработки каждой операции.
        finished_all: Отправляется после завершения всех операций.
    """

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
        for item in self.pending_ops:
            res = self._evaluate_single_op(item)
            self.operation_done.emit(res)
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
            new_c = self._apply_action(
                old_c, action, search, content, res
            )

            # Генерация diff
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
