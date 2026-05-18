"""Тесты для парсера JSON."""

import unittest
from ai_patcher_pro.core.json_parser import extract_all_json


class TestExtractAllJson(unittest.TestCase):
    """Тесты извлечения JSON из ответов ИИ."""

    def test_markdown_json_block(self):
        """JSON внутри markdown блока."""
        raw = 'Вот патч:\n```json\n[{"action": "replace", "path": "test.py", "search": "old", "content": "new"}]\n```'
        result = extract_all_json(raw)
        self.assertEqual(len(result["operations"]), 1)
        self.assertEqual(result["operations"][0]["action"], "replace")

    def test_raw_json_array(self):
        """JSON массив без markdown обёртки."""
        raw = '[{"action": "replace", "path": "test.py", "search": "old", "content": "new"}]'
        result = extract_all_json(raw)
        self.assertEqual(len(result["operations"]), 1)

    def test_json_with_operations_key(self):
        """JSON объект с ключом operations."""
        raw = '{"patch_name": "My Patch", "operations": [{"action": "replace", "path": "a.py", "search": "x", "content": "y"}]}'
        result = extract_all_json(raw)
        self.assertEqual(result["patch_name"], "My Patch")
        self.assertEqual(len(result["operations"]), 1)

    def test_single_operation_object(self):
        """Одиночный объект операции."""
        raw = '{"action": "create_file", "path": "new.py", "content": "hello"}'
        result = extract_all_json(raw)
        self.assertEqual(len(result["operations"]), 1)

    def test_trailing_comma_fix(self):
        """Автофикс висячих запятых (частая ошибка LLM)."""
        raw = '```json\n[{"action": "replace", "path": "test.py", "search": "old", "content": "new",}]\n```'
        result = extract_all_json(raw)
        self.assertEqual(len(result["operations"]), 1)

    def test_multiple_blocks(self):
        """Несколько JSON блоков в одном ответе."""
        raw = (
            'Вот первый патч:\n```json\n[{"action": "replace", "path": "a.py", "search": "x", "content": "y"}]\n```\n'
            'А вот второй:\n```json\n[{"action": "create_file", "path": "b.py", "content": "new"}]\n```'
        )
        result = extract_all_json(raw)
        self.assertEqual(len(result["operations"]), 2)

    def test_no_json_raises(self):
        """Исключение при отсутствии JSON."""
        with self.assertRaises(ValueError):
            extract_all_json("Просто текст без JSON")

    def test_alternative_field_names(self):
        """Альтернативные имена полей: file, op, original, text, code."""
        raw = '[{"op": "replace", "file": "test.py", "original": "old", "code": "new"}]'
        result = extract_all_json(raw)
        self.assertEqual(len(result["operations"]), 1)
        op = result["operations"][0]
        self.assertEqual(op.get("op"), "replace")
        self.assertEqual(op.get("file"), "test.py")


class TestExtractAllJsonEdgeCases(unittest.TestCase):
    """Граничные случаи парсера."""

    def test_empty_operations_raises(self):
        """Пустой массив операций вызывает ошибку."""
        with self.assertRaises(ValueError):
            extract_all_json("[]")

    def test_mixed_valid_invalid_blocks(self):
        """Смесь валидных и невалидных JSON блоков."""
        raw = (
            '```json\ninvalid json here\n```\n'
            '```json\n[{"action": "replace", "path": "test.py", "search": "x", "content": "y"}]\n```'
        )
        result = extract_all_json(raw)
        self.assertEqual(len(result["operations"]), 1)


if __name__ == "__main__":
    unittest.main()
