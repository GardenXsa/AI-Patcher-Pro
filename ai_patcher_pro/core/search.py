"""
5-уровневый алгоритм нечёткого поиска кода.

Уровни поиска:
1. Точное совпадение — search_text в file_text
2. Умные якоря — поиск по уникальным первой и последней строкам
3. Игнор пробелов/кавычек — нормализованное сравнение
4. Построчный Fuzzy Search — SequenceMatcher с порогом 92%+
5. Fuzzy Substring Search — скользящее окно с порогом 80%+

ИСПРАВЛЕНО: баг в anchor search (уровень 2) — str.find() мог вернуть -1,
что приводило к некорректному вычислению end_idx.
"""

import re
import difflib
from typing import Optional, Tuple, List


class SearchEngine:
    """Многоуровневый поисковый движок для нахождения кода в файлах."""

    @staticmethod
    def multi_tier_search(
        file_text: str, search_text: str
    ) -> Tuple[Optional[str], List[Tuple[float, str]], str]:
        """
        Выполняет многоуровневый поиск фрагмента кода в файле.

        Последовательно применяет 5 уровней поиска, от точного к нечёткому.
        Возвращает первый успешный результат.

        Args:
            file_text: Полный текст файла для поиска.
            search_text: Искомый фрагмент (от ИИ).

        Returns:
            Кортеж (найденный_текст, подсказки, название_метода):
            - найденный_текст: Реальный текст из файла или None.
            - подсказки: Список (ratio, текст) для ручного выбора.
            - название_метода: Описание использованного метода поиска.
        """
        if not search_text.strip():
            return None, [], "Пустой запрос"

        # === УРОВЕНЬ 1: Точное совпадение ===
        if search_text in file_text:
            return search_text, [], "Точное совпадение"

        # === УРОВЕНЬ 2: Умные якоря ===
        result = SearchEngine._anchor_search(file_text, search_text)
        if result is not None:
            return result

        # Нормализация для уровней 3-5
        file_norm, file_map = SearchEngine._normalize_strict(file_text)
        search_norm, _ = SearchEngine._normalize_strict(search_text)

        # === УРОВЕНЬ 3: Игнор пробелов/кавычек ===
        if search_norm:
            idx = file_norm.find(search_norm)
            if idx != -1:
                end_map_idx = min(idx + len(search_norm) - 1, len(file_map) - 1)
                start_pos = file_map[idx]
                end_pos = file_map[end_map_idx] + 1
                return file_text[start_pos:end_pos], [], "Игнор пробелов/кавычек"

        # === УРОВЕНЬ 4: Построчный Fuzzy Search (92%+) ===
        result = SearchEngine._line_fuzzy_search(file_text, search_text)
        if result is not None:
            return result

        # === УРОВЕНЬ 5: Fuzzy Substring Search (80%+) ===
        suggestions = SearchEngine._substring_fuzzy_search(
            file_text, file_norm, file_map, search_norm
        )

        return None, suggestions, "Не найдено (Требуется ручной выбор)"

    @staticmethod
    def _anchor_search(
        file_text: str, search_text: str
    ) -> Optional[Tuple[Optional[str], List, str]]:
        """
        Уровень 2: Поиск по уникальным якорям.

        Если ИИ сломал середину фрагмента, но первая и последняя строки
        уникальны в файле — находим блок между ними.

        ИСПРАВЛЕНО: оригинальный код использовал str.find('\n', offset),
        который мог вернуть -1, что приводило к некорректному end_idx.
        Теперь используется безопасная логика определения конца строки.
        """
        search_lines = [l.strip() for l in search_text.splitlines() if len(l.strip()) > 5]
        if len(search_lines) < 3:
            return None

        first_line = search_lines[0]
        last_line = search_lines[-1]

        first_matches = [m.start() for m in re.finditer(re.escape(first_line), file_text)]
        last_matches = [m.start() for m in re.finditer(re.escape(last_line), file_text)]

        if len(first_matches) != 1 or len(last_matches) != 1:
            return None

        start_idx = first_matches[0]

        # ИСПРАВЛЕНО: безопасное вычисление конца блока
        # Ищем конец строки, содержащей last_line
        last_line_end = last_matches[0] + len(last_line)
        remaining = file_text[last_line_end:]

        newline_pos = remaining.find("\n")
        if newline_pos != -1:
            # Нашли перенос строки — включаем текст до него
            end_idx = last_line_end + newline_pos
        else:
            # Нет переноса — это последняя строка в файле, берём до конца
            end_idx = len(file_text)

        # Проверки валидности
        if start_idx >= end_idx:
            return None

        # Блок не должен быть слишком большим (не более 3x от ожидаемого)
        block_size = end_idx - start_idx
        if block_size > len(search_text) * 3:
            return None

        return file_text[start_idx:end_idx], [], "Умный поиск по якорям (начало и конец блока)"

    @staticmethod
    def _normalize_strict(text: str) -> Tuple[str, List[int]]:
        """
        Жёсткая нормализация текста: удаление пробелов и унификация кавычек.

        Возвращает нормализованную строку и карту индексов для обратного
        отображения на оригинальный текст.

        Args:
            text: Исходный текст.

        Returns:
            Кортеж (нормализованная_строка, карта_индексов).
        """
        norm_chars: list = []
        orig_indices: list = []

        for i, char in enumerate(text):
            if not char.isspace():
                # Унификация кавычек
                if char in ("'", '"', "`"):
                    char = '"'
                norm_chars.append(char)
                orig_indices.append(i)

        return "".join(norm_chars), orig_indices

    @staticmethod
    def _line_fuzzy_search(
        file_text: str, search_text: str
    ) -> Optional[Tuple[str, List, str]]:
        """
        Уровень 4: Построчный нечёткий поиск с порогом 92%.

        Сравнивает строки скользящим окном, учитывая небольшие
        различия в форматировании и содержимом.
        """
        file_lines = file_text.splitlines()
        search_lines = [line.strip() for line in search_text.splitlines() if line.strip()]

        if not search_lines:
            return None

        s_len = len(search_lines)
        for i in range(max(1, len(file_lines) - s_len + 1)):
            chunk = file_lines[i : i + s_len + 2]
            chunk_stripped = [l.strip() for l in chunk if l.strip()]

            ratio = difflib.SequenceMatcher(
                None, "\n".join(search_lines), "\n".join(chunk_stripped)
            ).ratio()

            if ratio > 0.92:
                start_idx = file_text.find(file_lines[i])
                end_line_idx = min(i + s_len + 1, len(file_lines) - 1)
                end_idx = file_text.find(file_lines[end_line_idx]) + len(file_lines[end_line_idx])
                return file_text[start_idx:end_idx], [], "Построчный Fuzzy Search (92%+)"

        return None

    @staticmethod
    def _substring_fuzzy_search(
        file_text: str,
        file_norm: str,
        file_map: List[int],
        search_norm: str,
    ) -> List[Tuple[float, str]]:
        """
        Уровень 5: Нечёткий поиск подстрок с порогом 80%.

        Использует скользящее окно по нормализованному тексту.
        Возвращает до 4 лучших кандидатов для ручного выбора.
        """
        suggestions: list = []
        search_len = len(search_norm)

        if search_len == 0:
            return suggestions

        step = max(1, search_len // 3)
        window_extra = int(search_len * 0.3)

        for i in range(0, max(1, len(file_norm) - search_len + 1), step):
            window = file_norm[i : i + search_len + window_extra]
            if not window:
                continue

            ratio = difflib.SequenceMatcher(None, search_norm, window).ratio()

            if ratio > 0.80:
                match = difflib.SequenceMatcher(
                    None, search_norm, window
                ).find_longest_match(0, len(search_norm), 0, len(window))

                if match.size > 0:
                    map_start = i + match.b
                    map_end = min(i + match.b + match.size - 1, len(file_map) - 1)

                    if map_start < len(file_map) and map_end < len(file_map):
                        candidate = file_text[file_map[map_start] : file_map[map_end] + 1]
                        # Дедупликация подсказок
                        if candidate not in [s[1] for s in suggestions]:
                            suggestions.append((ratio, candidate))

        suggestions.sort(key=lambda x: x[0], reverse=True)
        return suggestions[:4]
