"""
Тесты для модуля патчинга.

Проверяет КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: replace_first_occurrence()
заменяет только первое вхождение, а не все.
"""

import unittest
from ai_patcher_pro.core.patcher import (
    replace_first_occurrence,
    apply_single_operation,
    normalize_operation_fields,
)


class TestReplaceFirstOccurrence(unittest.TestCase):
    """КРИТИЧЕСКИЙ ТЕСТ: замена только первого вхождения."""

    def test_single_occurrence(self):
        """Один вхождение — работает как обычный replace."""
        text = "hello world"
        result = replace_first_occurrence(text, "hello", "hi")
        self.assertEqual(result, "hi world")

    def test_multiple_occurrences(self):
        """
        КРИТИЧЕСКИЙ ТЕСТ: несколько вхождений — заменяется ТОЛЬКО первое.

        В оригинальном коде str.replace() заменял ВСЕ вхождения,
        что могло повредить файлы с повторяющимися фрагментами.
        """
        text = "import os\nimport sys\nimport os"
        result = replace_first_occurrence(text, "import os", "import pathlib")
        # Только ПЕРВОЕ вхождение заменено!
        self.assertEqual(result, "import pathlib\nimport sys\nimport os")
        # Старый str.replace() дал бы: "import pathlib\nimport sys\nimport pathlib"
        self.assertNotEqual(
            result,
            "import pathlib\nimport sys\nimport pathlib",
            "replace_first_occurrence НЕ должен заменять все вхождения!"
        )

    def test_duplicate_code_blocks(self):
        """
        Реальный сценарий: повторяющийся код в файле.

        Частая ситуация: одинаковые паттерны в разных функциях.
        """
        text = (
            "def foo():\n"
            "    result = 0\n"
            "    return result\n"
            "\n"
            "def bar():\n"
            "    result = 0\n"
            "    return result"
        )
        # Заменяем только в первой функции
        result = replace_first_occurrence(text, "    result = 0", "    result = 1")
        expected = (
            "def foo():\n"
            "    result = 1\n"
            "    return result\n"
            "\n"
            "def bar():\n"
            "    result = 0\n"
            "    return result"
        )
        self.assertEqual(result, expected)

    def test_not_found_raises(self):
        """Исключение при ненахождении фрагмента."""
        with self.assertRaises(ValueError):
            replace_first_occurrence("hello", "world", "test")


class TestApplySingleOperation(unittest.TestCase):
    """Тесты применения различных типов операций."""

    def test_replace_action(self):
        old = "def old_func():\n    pass"
        result = apply_single_operation(old, "replace", "def old_func():", "def new_func():")
        self.assertEqual(result, "def new_func():\n    pass")

    def test_insert_after(self):
        old = "line1\nline3"
        result = apply_single_operation(old, "insert_after", "line1", "line2")
        self.assertIn("line1\nline2", result)

    def test_insert_before(self):
        old = "line1\nline3"
        result = apply_single_operation(old, "insert_before", "line3", "line2")
        self.assertIn("line2\nline3", result)

    def test_delete_action(self):
        old = "line1\nline2\nline3"
        result = apply_single_operation(old, "delete", "line2", "")
        self.assertEqual(result, "line1\n\nline3")

    def test_append_action(self):
        old = "line1"
        result = apply_single_operation(old, "append", "", "line2")
        self.assertEqual(result, "line1\nline2")

    def test_prepend_action(self):
        old = "line2"
        result = apply_single_operation(old, "prepend", "", "line1")
        self.assertEqual(result, "line1\nline2")

    def test_create_file_action(self):
        result = apply_single_operation("", "create_file", "", "new content")
        self.assertEqual(result, "new content")

    def test_unknown_action_raises(self):
        with self.assertRaises(ValueError):
            apply_single_operation("text", "unknown_action", "", "")


class TestNormalizeOperationFields(unittest.TestCase):
    """Тесты нормализации полей операции."""

    def test_standard_fields(self):
        op = {"path": "test.py", "action": "replace", "search": "old", "content": "new"}
        result = normalize_operation_fields(op)
        self.assertEqual(result["path"], "test.py")
        self.assertEqual(result["action"], "replace")

    def test_alternative_fields(self):
        op = {"file": "test.py", "op": "replace", "original": "old", "text": "new"}
        result = normalize_operation_fields(op)
        self.assertEqual(result["path"], "test.py")
        self.assertEqual(result["action"], "replace")
        self.assertEqual(result["search"], "old")
        self.assertEqual(result["content"], "new")

    def test_missing_fields(self):
        op = {"path": "test.py"}
        result = normalize_operation_fields(op)
        self.assertEqual(result["action"], "unknown")
        self.assertEqual(result["search"], "")
        self.assertEqual(result["content"], "")


if __name__ == "__main__":
    unittest.main()
