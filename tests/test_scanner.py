"""Тесты для сканера проекта."""

import os
import tempfile
import unittest

from ai_patcher_pro.core.scanner import ScannerEngine, ScanResult


class TestScannerEngine(unittest.TestCase):
    """Тесты движка сканирования."""

    def setUp(self):
        """Создаёт временную директорию с тестовыми файлами."""
        self.tmpdir = tempfile.mkdtemp(prefix="ai_patcher_test_")

        # Создаём структуру файлов
        os.makedirs(os.path.join(self.tmpdir, "src"), exist_ok=True)
        os.makedirs(os.path.join(self.tmpdir, "src", "utils"), exist_ok=True)
        os.makedirs(os.path.join(self.tmpdir, "tests"), exist_ok=True)
        os.makedirs(os.path.join(self.tmpdir, "__pycache__"), exist_ok=True)

        # Python файлы
        with open(os.path.join(self.tmpdir, "main.py"), "w") as f:
            f.write("def main():\n    print('hello')\n\nif __name__ == '__main__':\n    main()\n")
        with open(os.path.join(self.tmpdir, "src", "app.py"), "w") as f:
            f.write("class App:\n    pass\n")
        with open(os.path.join(self.tmpdir, "src", "utils", "helpers.py"), "w") as f:
            f.write("def helper():\n    return True\n")

        # JavaScript файл
        with open(os.path.join(self.tmpdir, "src", "index.js"), "w") as f:
            f.write("console.log('hello');\n")

        # Тестовый файл
        with open(os.path.join(self.tmpdir, "tests", "test_app.py"), "w") as f:
            f.write("def test_app():\n    assert True\n")

        # Конфиг
        with open(os.path.join(self.tmpdir, "config.json"), "w") as f:
            f.write('{"name": "test"}\n')

        # __pycache__ файл — должен быть проигнорирован
        with open(os.path.join(self.tmpdir, "__pycache__", "main.cpython-39.pyc"), "wb") as f:
            f.write(b"\x00" * 100)

        # Бинарный файл — должен быть проигнорирован
        with open(os.path.join(self.tmpdir, "image.png"), "wb") as f:
            f.write(b"\x89PNG" + b"\x00" * 100)

        # .git файл — должен быть проигнорирован (директория)
        git_dir = os.path.join(self.tmpdir, ".git")
        os.makedirs(git_dir, exist_ok=True)
        with open(os.path.join(git_dir, "HEAD"), "w") as f:
            f.write("ref: refs/heads/main\n")

    def tearDown(self):
        """Удаляет временную директорию."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_scan_basic(self):
        """Базовое сканирование находит файлы."""
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir)
        self.assertIsInstance(result, ScanResult)
        self.assertGreater(result.total_files, 0)

    def test_scan_ignores_pycache(self):
        """Сканирование игнорирует __pycache__."""
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir)
        pycache_files = [f for f in result.files if "__pycache__" in f.rel_path]
        self.assertEqual(len(pycache_files), 0)

    def test_scan_ignores_git_dir(self):
        """Сканирование игнорирует .git директорию."""
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir)
        git_files = [f for f in result.files if ".git/" in f.rel_path]
        self.assertEqual(len(git_files), 0)

    def test_scan_ignores_binary_files(self):
        """Сканирование игнорирует бинарные файлы (.png)."""
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir)
        png_files = [f for f in result.files if f.rel_path.endswith(".png")]
        self.assertEqual(len(png_files), 0)

    def test_scan_detects_languages(self):
        """Сканирование определяет языки программирования."""
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir)
        self.assertIn("Python", result.languages)
        self.assertIn("JavaScript", result.languages)

    def test_scan_counts_files(self):
        """Сканирование правильно подсчитывает файлы."""
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir)
        # main.py, src/app.py, src/utils/helpers.py, src/index.js, tests/test_app.py, config.json
        self.assertEqual(result.total_files, 6)

    def test_scan_counts_lines(self):
        """Сканирование подсчитывает строки."""
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir)
        self.assertGreater(result.total_lines, 0)

    def test_scan_estimates_tokens(self):
        """Сканирование оценивает токены."""
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir)
        self.assertGreater(result.total_tokens, 0)

    def test_scan_builds_tree(self):
        """Сканирование строит дерево файлов."""
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir)
        self.assertIn("main.py", result.directory_tree)
        self.assertIn("src/", result.directory_tree)

    def test_scan_nonexistent_dir(self):
        """Сканирование несуществующей директории возвращает пустой результат."""
        engine = ScannerEngine()
        result = engine.scan("/nonexistent/path/12345")
        self.assertEqual(result.total_files, 0)

    def test_custom_ignore_dirs(self):
        """Пользовательские игнорируемые директории."""
        engine = ScannerEngine(ignore_dirs=["tests"])
        result = engine.scan(self.tmpdir)
        test_files = [f for f in result.files if "tests/" in f.rel_path]
        self.assertEqual(len(test_files), 0)

    def test_custom_ignore_files(self):
        """Пользовательские glob-шаблоны игнорирования."""
        engine = ScannerEngine(ignore_files=["*.json"])
        result = engine.scan(self.tmpdir)
        json_files = [f for f in result.files if f.rel_path.endswith(".json")]
        self.assertEqual(len(json_files), 0)

    def test_max_file_size(self):
        """Ограничение максимального размера файла."""
        # Создаём большой файл
        big_file = os.path.join(self.tmpdir, "big_file.py")
        with open(big_file, "w") as f:
            f.write("x" * 1024)  # 1KB

        engine = ScannerEngine(max_file_size=512)  # 512 байт
        result = engine.scan(self.tmpdir)
        big_found = [f for f in result.files if f.rel_path == "big_file.py"]
        self.assertEqual(len(big_found), 0)


class TestGenerateContext(unittest.TestCase):
    """Тесты генерации контекста."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="ai_patcher_ctx_")
        os.makedirs(os.path.join(self.tmpdir, "src"), exist_ok=True)
        with open(os.path.join(self.tmpdir, "main.py"), "w") as f:
            f.write("print('hello world')\n")
        with open(os.path.join(self.tmpdir, "src", "app.py"), "w") as f:
            f.write("class App:\n    pass\n")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_context_with_tree(self):
        """Контекст содержит дерево файлов."""
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir)
        context = engine.generate_context(result, include_tree=True, include_contents=False)
        self.assertIn("Project:", context)
        self.assertIn("File Tree", context)
        self.assertIn("main.py", context)

    def test_context_with_contents(self):
        """Контекст содержит содержимое файлов."""
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir)
        context = engine.generate_context(result, include_tree=True, include_contents=True)
        self.assertIn("hello world", context)
        self.assertIn("class App:", context)

    def test_context_without_tree(self):
        """Контекст без дерева файлов."""
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir)
        context = engine.generate_context(result, include_tree=False, include_contents=False)
        self.assertNotIn("File Tree", context)
        self.assertIn("Project:", context)

    def test_context_selected_files(self):
        """Контекст только для выбранных файлов."""
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir)
        context = engine.generate_context(
            result, include_tree=False, include_contents=True,
            selected_files=["main.py"]
        )
        self.assertIn("hello world", context)
        self.assertNotIn("class App:", context)

    def test_context_token_limit(self):
        """Ограничение токенов в контексте."""
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir)
        context = engine.generate_context(
            result, include_contents=True, max_tokens=5
        )
        # Контекст должен быть обрезан (грубая проверка)
        self.assertLess(len(context) // 4, 80)

    def test_context_languages_in_header(self):
        """Заголовок контекста содержит информацию о языках."""
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir)
        context = engine.generate_context(result, include_contents=False)
        self.assertIn("Languages:", context)
        self.assertIn("Python", context)


class TestScannerUtilities(unittest.TestCase):
    """Тесты утилит сканера."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="ai_patcher_util_")
        with open(os.path.join(self.tmpdir, "a.py"), "w") as f:
            f.write("x = 1\n")
        with open(os.path.join(self.tmpdir, "b.js"), "w") as f:
            f.write("var x = 1;\n")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_get_files_by_language(self):
        """Группировка файлов по языку."""
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir)
        grouped = engine.get_files_by_language(result)
        self.assertIn("Python", grouped)
        self.assertIn("JavaScript", grouped)
        self.assertEqual(len(grouped["Python"]), 1)
        self.assertEqual(len(grouped["JavaScript"]), 1)

    def test_estimate_tokens_for_files(self):
        """Оценка токенов для указанных файлов."""
        engine = ScannerEngine()
        engine.scan(self.tmpdir)  # Необязательно, но для полноты
        tokens = engine.estimate_tokens_for_files(["a.py", "b.js"], self.tmpdir)
        self.assertGreater(tokens, 0)


if __name__ == "__main__":
    unittest.main()
