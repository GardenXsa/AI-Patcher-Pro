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



    def test_markdown_json_block_with_chatgpt_attributes(self):
        """JSON внутри markdown блока с атрибутами после языка."""
        fence = "`" * 3
        raw = (
            f'Вот патч:\n{fence}json id="abc123"\n'
            '[{"action": "replace", "path": "test.py", "search": "old", "content": "new"}]\n'
            f'{fence}'
        )
        result = extract_all_json(raw)
        self.assertEqual(len(result["operations"]), 1)
        self.assertEqual(result["operations"][0]["path"], "test.py")

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


class TestExtractCommands(unittest.TestCase):
    """Тесты извлечения консольных команд из JSON."""

    def test_commands_in_operations_object(self):
        """Команды извлекаются из объекта с operations."""
        raw = (
            '{"patch_name": "Test", "operations": ['
            '{"action": "replace", "path": "a.py", "search": "x", "content": "y"}'
            '], "commands": [{"cmd": "npm install", "run": "after_apply"}]}'
        )
        result = extract_all_json(raw)
        self.assertEqual(len(result["operations"]), 1)
        self.assertEqual(len(result["commands"]), 1)
        self.assertEqual(result["commands"][0]["cmd"], "npm install")
        self.assertEqual(result["commands"][0]["run"], "after_apply")

    def test_commands_string_shorthand(self):
        """Команда как строка преобразуется в after_apply."""
        raw = (
            '{"operations": ['
            '{"action": "replace", "path": "a.py", "search": "x", "content": "y"}'
            '], "commands": "pip install requests"}'
        )
        result = extract_all_json(raw)
        self.assertEqual(len(result["commands"]), 1)
        self.assertEqual(result["commands"][0]["cmd"], "pip install requests")
        self.assertEqual(result["commands"][0]["run"], "after_apply")

    def test_commands_list_of_strings(self):
        """Массив строк-команд преобразуется корректно."""
        raw = (
            '{"operations": ['
            '{"action": "replace", "path": "a.py", "search": "x", "content": "y"}'
            '], "commands": ["npm install", "npm run build"]}'
        )
        result = extract_all_json(raw)
        self.assertEqual(len(result["commands"]), 2)
        self.assertEqual(result["commands"][0]["cmd"], "npm install")
        self.assertEqual(result["commands"][1]["cmd"], "npm run build")

    def test_commands_with_after_analysis(self):
        """Команда с run=after_analysis правильно разбирается."""
        raw = (
            '{"operations": ['
            '{"action": "replace", "path": "a.py", "search": "x", "content": "y"}'
            '], "commands": [{"cmd": "pip install flask", "run": "after_analysis"}]}'
        )
        result = extract_all_json(raw)
        self.assertEqual(len(result["commands"]), 1)
        self.assertEqual(result["commands"][0]["run"], "after_analysis")

    def test_commands_with_description(self):
        """Описание команды сохраняется."""
        raw = (
            '{"operations": ['
            '{"action": "replace", "path": "a.py", "search": "x", "content": "y"}'
            '], "commands": [{"cmd": "pytest", "description": "Запуск тестов"}]}'
        )
        result = extract_all_json(raw)
        self.assertEqual(result["commands"][0]["description"], "Запуск тестов")

    def test_cmds_alias(self):
        """Альтернативный ключ cmds распознаётся."""
        raw = (
            '{"operations": ['
            '{"action": "replace", "path": "a.py", "search": "x", "content": "y"}'
            '], "cmds": "npm test"}'
        )
        result = extract_all_json(raw)
        self.assertEqual(len(result["commands"]), 1)
        self.assertEqual(result["commands"][0]["cmd"], "npm test")

    def test_exec_alias(self):
        """Альтернативный ключ exec распознаётся."""
        raw = (
            '{"operations": ['
            '{"action": "replace", "path": "a.py", "search": "x", "content": "y"}'
            '], "exec": "docker build ."}'
        )
        result = extract_all_json(raw)
        self.assertEqual(len(result["commands"]), 1)
        self.assertEqual(result["commands"][0]["cmd"], "docker build .")

    def test_no_commands_returns_empty_list(self):
        """Без команд возвращается пустой список."""
        raw = '[{"action": "replace", "path": "a.py", "search": "x", "content": "y"}]'
        result = extract_all_json(raw)
        self.assertEqual(result["commands"], [])

    def test_commands_only_no_operations(self):
        """JSON только с командами (без operations) тоже парсится."""
        raw = '{"commands": [{"cmd": "echo hello", "run": "after_apply"}]}'
        result = extract_all_json(raw)
        self.assertEqual(len(result["operations"]), 0)
        self.assertEqual(len(result["commands"]), 1)

    def test_empty_commands_filtered(self):
        """Пустые команды отфильтровываются."""
        raw = (
            '{"operations": ['
            '{"action": "replace", "path": "a.py", "search": "x", "content": "y"}'
            '], "commands": ["", "echo hello"]}'
        )
        result = extract_all_json(raw)
        self.assertEqual(len(result["commands"]), 1)
        self.assertEqual(result["commands"][0]["cmd"], "echo hello")

    def test_dangerous_command_has_warnings(self):
        """Опасная команда содержит предупреждения."""
        raw = (
            '{"operations": ['
            '{"action": "replace", "path": "a.py", "search": "x", "content": "y"}'
            '], "commands": ["rm -rf /tmp/test"]}'
        )
        result = extract_all_json(raw)
        self.assertTrue(len(result["commands"][0]["warnings"]) > 0)

    def test_mixed_commands_phases(self):
        """Смешанные фазы команд правильно разделяются."""
        raw = (
            '{"operations": ['
            '{"action": "replace", "path": "a.py", "search": "x", "content": "y"}'
            '], "commands": ['
            '{"cmd": "pip install flask", "run": "after_analysis"},'
            '{"cmd": "pytest", "run": "after_apply"}'
            ']}'
        )
        result = extract_all_json(raw)
        self.assertEqual(len(result["commands"]), 2)
        analysis_cmds = [c for c in result["commands"] if c["run"] == "after_analysis"]
        apply_cmds = [c for c in result["commands"] if c["run"] == "after_apply"]
        self.assertEqual(len(analysis_cmds), 1)
        self.assertEqual(len(apply_cmds), 1)


if __name__ == "__main__":
    unittest.main()
