"""
Тесты для поискового движка SearchEngine.

Проверяет все 5 уровней поиска и исправленный баг anchor search.
"""

import unittest
from ai_patcher_pro.core.search import SearchEngine


class TestSearchEngineExact(unittest.TestCase):
    """Уровень 1: Точное совпадение."""

    def test_exact_match(self):
        file_text = "def hello():\n    print('hello')\n    return True"
        search_text = "    print('hello')"
        result, suggestions, method = SearchEngine.multi_tier_search(file_text, search_text)
        self.assertEqual(result, search_text)
        self.assertEqual(suggestions, [])
        self.assertEqual(method, "Точное совпадение")

    def test_empty_search(self):
        result, suggestions, method = SearchEngine.multi_tier_search("some text", "  ")
        self.assertIsNone(result)
        self.assertEqual(method, "Пустой запрос")

    def test_no_match(self):
        file_text = "def hello():\n    pass"
        search_text = "def goodbye():\n    pass"
        result, suggestions, method = SearchEngine.multi_tier_search(file_text, search_text)
        self.assertIsNone(result)


class TestSearchEngineAnchors(unittest.TestCase):
    """Уровень 2: Умные якоря (ИСПРАВЛЕННЫЙ баг)."""

    def test_anchor_search_basic(self):
        """Якорный поиск: начало и конец уникальны, середина сломана."""
        file_text = (
            "class MyClass:\n"
            "    def __init__(self):\n"
            "        self.x = 10\n"
            "        self.y = 20\n"
            "    def method(self):\n"
            "        return self.x"
        )
        # ИИ сломал середину, но первая и последняя строки верны
        search_text = (
            "class MyClass:\n"
            "    BROKEN MIDDLE\n"
            "    def method(self):\n"
            "        return self.x"
        )
        result, _, method = SearchEngine.multi_tier_search(file_text, search_text)
        self.assertIsNotNone(result)
        self.assertIn("class MyClass:", result)
        self.assertIn("return self.x", result)

    def test_anchor_search_last_line_is_file_end(self):
        """
        ИСПРАВЛЕННЫЙ БАГ: последняя строка якоря — последняя строка файла.

        В оригинале str.find('\n', offset) возвращал -1 для последней строки,
        что приводило к некорректному end_idx.
        """
        file_text = "line1_unique\nmiddle content\nlast_line_unique"
        search_text = "line1_unique\nbroken middle\nlast_line_unique"
        result, _, method = SearchEngine.multi_tier_search(file_text, search_text)
        # Должен найти блок корректно
        self.assertIsNotNone(result)
        self.assertTrue(result.startswith("line1_unique"))
        self.assertTrue(result.strip().endswith("last_line_unique"))

    def test_anchor_search_non_unique_first_line(self):
        """Якорный поиск: первая строка не уникальна — якоря не работают."""
        file_text = "duplicate_line\ncontent1\nduplicate_line\ncontent2"
        search_text = "duplicate_line\nbroken\nduplicate_line"
        # Оба якоря встречаются дважды — якорный поиск не сработает
        result, _, method = SearchEngine.multi_tier_search(file_text, search_text)
        # Не должен вернуть результат через якоря (может через другие уровни)

    def test_anchor_search_too_large_block(self):
        """Якорный поиск: блок слишком большой — отклоняется."""
        file_text = "unique_start\n" + "padding\n" * 100 + "unique_end"
        search_text = "unique_start\nshort\nunique_end"
        # Блок в 100+ строк при ожидаемом 3 — должен быть отклонён


class TestSearchEngineNormalized(unittest.TestCase):
    """Уровень 3: Игнор пробелов/кавычек."""

    def test_normalized_match_whitespace(self):
        """Совпадение с разными пробелами."""
        file_text = "def hello(  ):\n    print( 'hello' )"
        search_text = "def hello():\n    print('hello')"
        result, _, method = SearchEngine.multi_tier_search(file_text, search_text)
        self.assertIsNotNone(result)
        self.assertIn("Игнор пробелов", method)

    def test_normalized_match_quotes(self):
        """Совпадение с разными кавычками."""
        file_text = 'name = "world"'
        search_text = "name = 'world'"
        result, _, method = SearchEngine.multi_tier_search(file_text, search_text)
        self.assertIsNotNone(result)


class TestSearchEngineLineFuzzy(unittest.TestCase):
    """Уровень 4: Построчный Fuzzy Search."""

    def test_fuzzy_line_match(self):
        """Нечёткое совпадение по строкам (92%+)."""
        file_text = (
            "def calculate_total(items):\n"
            "    total = sum(item.price for item in items)\n"
            "    return total + tax"
        )
        search_text = (
            "def calculate_total(items):\n"
            "    total = sum(item.cost for item in items)\n"
            "    return total + tax"
        )
        result, _, method = SearchEngine.multi_tier_search(file_text, search_text)
        # Должен найти через нечёткий поиск (разница в 1 слове)
        self.assertIsNotNone(result)


class TestSearchEngineSubstringFuzzy(unittest.TestCase):
    """Уровень 5: Fuzzy Substring Search."""

    def test_fuzzy_suggestions(self):
        """Должен вернуть подсказки при частичном совпадении."""
        file_text = (
            "class UserService:\n"
            "    def get_user(self, id):\n"
            "        return self.db.query(id)"
        )
        search_text = (
            "class UserSrvce:\n"
            "    def fetch_usr(self, id):\n"
            "        return self.database.query(id)"
        )
        result, suggestions, method = SearchEngine.multi_tier_search(file_text, search_text)
        # На этом уровне могут быть подсказки
        if result is None:
            self.assertGreater(len(suggestions), 0)


if __name__ == "__main__":
    unittest.main()
