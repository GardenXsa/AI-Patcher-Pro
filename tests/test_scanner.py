"""Тесты для сканера проекта."""

import os
import tempfile
import unittest

from ai_patcher_pro.core.scanner import (
    ScannerEngine,
    ScanResult,
    ScanFilter,
    ContextOptions,
    parse_gitignore,
    LANG_CATEGORIES,
)


class TestGitignoreParser(unittest.TestCase):
    """Тесты парсера .gitignore."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="gitignore_test_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_parse_basic_gitignore(self):
        """Парсинг простого .gitignore."""
        gitignore = os.path.join(self.tmpdir, ".gitignore")
        with open(gitignore, "w") as f:
            f.write("# Comment\nnode_modules/\n*.log\ndist/\n!keep.txt\n\n")
        dir_p, file_p = parse_gitignore(gitignore)
        self.assertIn("node_modules", dir_p)
        self.assertIn("dist", dir_p)
        self.assertIn("*.log", file_p)
        # Отрицания (!) пропускаются
        self.assertNotIn("keep.txt", file_p)
        self.assertNotIn("", file_p)  # пустые строки

    def test_parse_nonexistent_gitignore(self):
        """Несуществующий .gitignore возвращает пустые списки."""
        dir_p, file_p = parse_gitignore("/nonexistent/.gitignore")
        self.assertEqual(len(dir_p), 0)
        self.assertEqual(len(file_p), 0)

    def test_dir_pattern_detected(self):
        """Паттерн с / на конце распознаётся как директория."""
        gitignore = os.path.join(self.tmpdir, ".gitignore")
        with open(gitignore, "w") as f:
            f.write("build/\ncache/\n")
        dir_p, file_p = parse_gitignore(gitignore)
        self.assertIn("build", dir_p)
        self.assertIn("cache", dir_p)


class TestScannerEngine(unittest.TestCase):
    """Тесты движка сканирования."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="ai_patcher_test_")

        # Структура файлов
        os.makedirs(os.path.join(self.tmpdir, "src"), exist_ok=True)
        os.makedirs(os.path.join(self.tmpdir, "src", "utils"), exist_ok=True)
        os.makedirs(os.path.join(self.tmpdir, "tests"), exist_ok=True)
        os.makedirs(os.path.join(self.tmpdir, "__pycache__"), exist_ok=True)
        os.makedirs(os.path.join(self.tmpdir, "node_modules", "pkg"), exist_ok=True)
        os.makedirs(os.path.join(self.tmpdir, ".git"), exist_ok=True)

        # Python
        with open(os.path.join(self.tmpdir, "main.py"), "w") as f:
            f.write("def main():\n    print('hello')\n\nif __name__ == '__main__':\n    main()\n")
        with open(os.path.join(self.tmpdir, "src", "app.py"), "w") as f:
            f.write("class App:\n    pass\n")
        with open(os.path.join(self.tmpdir, "src", "utils", "helpers.py"), "w") as f:
            f.write("def helper():\n    return True\n")

        # JavaScript
        with open(os.path.join(self.tmpdir, "src", "index.js"), "w") as f:
            f.write("console.log('hello');\n")

        # Тесты
        with open(os.path.join(self.tmpdir, "tests", "test_app.py"), "w") as f:
            f.write("def test_app():\n    assert True\n")

        # Конфиг
        with open(os.path.join(self.tmpdir, "config.json"), "w") as f:
            f.write('{"name": "test"}\n')

        # .gitignore
        with open(os.path.join(self.tmpdir, ".gitignore"), "w") as f:
            f.write("*.log\ntemp/\n")

        # Файлы, которые должны быть проигнорированы
        with open(os.path.join(self.tmpdir, "__pycache__", "main.cpython-39.pyc"), "wb") as f:
            f.write(b"\x00" * 100)
        with open(os.path.join(self.tmpdir, "node_modules", "pkg", "index.js"), "w") as f:
            f.write("module.exports = {};\n")
        with open(os.path.join(self.tmpdir, ".git", "HEAD"), "w") as f:
            f.write("ref: refs/heads/main\n")
        with open(os.path.join(self.tmpdir, "image.png"), "wb") as f:
            f.write(b"\x89PNG" + b"\x00" * 100)
        with open(os.path.join(self.tmpdir, "app.log"), "w") as f:
            f.write("error: something\n")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_scan_basic(self):
        """Базовое сканирование находит файлы."""
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir)
        self.assertIsInstance(result, ScanResult)
        self.assertGreater(result.total_files, 0)

    def test_scan_ignores_pycache(self):
        """__pycache__ всегда игнорируется."""
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir)
        pycache_files = [f for f in result.files if "__pycache__" in f.rel_path]
        self.assertEqual(len(pycache_files), 0)

    def test_scan_ignores_git_dir(self):
        """.git всегда игнорируется."""
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir)
        git_files = [f for f in result.files if ".git/" in f.rel_path]
        self.assertEqual(len(git_files), 0)

    def test_scan_ignores_node_modules_by_default(self):
        """node_modules игнорируется по умолчанию."""
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir)
        nm_files = [f for f in result.files if "node_modules/" in f.rel_path]
        self.assertEqual(len(nm_files), 0)

    def test_scan_ignores_binary_files(self):
        """Бинарные файлы (.png) игнорируются."""
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir)
        png_files = [f for f in result.files if f.rel_path.endswith(".png")]
        self.assertEqual(len(png_files), 0)

    def test_scan_gitignore_loaded(self):
        """.gitignore загружается автоматически."""
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir)
        self.assertTrue(result.gitignore_loaded)

    def test_scan_gitignore_filters_log(self):
        """*.log из .gitignore фильтруется."""
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir)
        log_files = [f for f in result.files if f.rel_path.endswith(".log")]
        self.assertEqual(len(log_files), 0)

    def test_scan_disable_gitignore(self):
        """Отключение .gitignore."""
        sf = ScanFilter(use_gitignore=False)
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir, sf)
        log_files = [f for f in result.files if f.rel_path.endswith(".log")]
        # .log файл должен попасть в результаты
        self.assertEqual(len(log_files), 1)

    def test_scan_disable_default_ignores(self):
        """Отключение стандартных игноров (node_modules попадёт в результат)."""
        sf = ScanFilter(use_default_ignores=False)
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir, sf)
        nm_files = [f for f in result.files if "node_modules/" in f.rel_path]
        self.assertGreater(len(nm_files), 0)

    def test_scan_detects_languages(self):
        """Определение языков программирования."""
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir)
        self.assertIn("Python", result.languages)
        self.assertIn("JavaScript", result.languages)

    def test_scan_detects_extensions(self):
        """Определение расширений файлов."""
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir)
        self.assertIn(".py", result.extensions)
        self.assertIn(".js", result.extensions)

    def test_scan_counts_lines(self):
        """Подсчёт строк."""
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir)
        self.assertGreater(result.total_lines, 0)

    def test_scan_estimates_tokens(self):
        """Оценка токенов."""
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir)
        self.assertGreater(result.total_tokens, 0)

    def test_scan_builds_tree(self):
        """Построение дерева файлов."""
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir)
        self.assertIn("main.py", result.directory_tree)
        self.assertIn("src/", result.directory_tree)

    def test_scan_nonexistent_dir(self):
        """Сканирование несуществующей директории."""
        engine = ScannerEngine()
        result = engine.scan("/nonexistent/path/12345")
        self.assertEqual(result.total_files, 0)

    def test_filter_include_extensions(self):
        """Фильтр: только указанные расширения."""
        sf = ScanFilter(include_extensions={".py"})
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir, sf)
        for fi in result.files:
            self.assertEqual(fi.extension, ".py")

    def test_filter_exclude_extensions(self):
        """Фильтр: исключить расширения."""
        sf = ScanFilter(exclude_extensions={".json"})
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir, sf)
        json_files = [f for f in result.files if f.extension == ".json"]
        self.assertEqual(len(json_files), 0)

    def test_filter_include_languages(self):
        """Фильтр: только указанные языки."""
        sf = ScanFilter(include_languages={"Python"})
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir, sf)
        for fi in result.files:
            self.assertEqual(fi.language, "Python")

    def test_filter_exclude_languages(self):
        """Фильтр: исключить языки."""
        sf = ScanFilter(exclude_languages={"JSON"})
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir, sf)
        # JSON файлы не должны быть
        for fi in result.files:
            self.assertNotEqual(fi.language, "JSON")

    def test_filter_max_file_size(self):
        """Фильтр: максимальный размер файла."""
        big_file = os.path.join(self.tmpdir, "big.py")
        with open(big_file, "w") as f:
            f.write("x" * 2048)
        sf = ScanFilter(max_file_size=1024)
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir, sf)
        big_found = [f for f in result.files if f.rel_path == "big.py"]
        self.assertEqual(len(big_found), 0)

    def test_filter_include_regex(self):
        """Фильтр: regex включения."""
        sf = ScanFilter(include_regex=r"src/.*\.py$")
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir, sf)
        for fi in result.files:
            self.assertTrue("src/" in fi.rel_path and fi.rel_path.endswith(".py"))

    def test_filter_exclude_regex(self):
        """Фильтр: regex исключения."""
        sf = ScanFilter(exclude_regex=r"test")
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir, sf)
        test_files = [f for f in result.files if "test" in f.rel_path.lower()]
        self.assertEqual(len(test_files), 0)

    def test_filter_user_ignore_dirs(self):
        """Пользовательские игнорируемые директории."""
        sf = ScanFilter(user_ignore_dirs=["tests"])
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir, sf)
        test_files = [f for f in result.files if "tests/" in f.rel_path]
        self.assertEqual(len(test_files), 0)

    def test_filter_user_ignore_patterns(self):
        """Пользовательские glob-шаблоны."""
        sf = ScanFilter(user_ignore_patterns=["*.json"])
        engine = ScannerEngine()
        result = engine.scan(self.tmpdir, sf)
        json_files = [f for f in result.files if f.extension == ".json"]
        self.assertEqual(len(json_files), 0)


class TestGenerateContext(unittest.TestCase):
    """Тесты генерации контекста."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="ai_patcher_ctx_")
        os.makedirs(os.path.join(self.tmpdir, "src"), exist_ok=True)
        with open(os.path.join(self.tmpdir, "main.py"), "w") as f:
            f.write("print('hello world')\nx = 42\n")
        with open(os.path.join(self.tmpdir, "src", "app.py"), "w") as f:
            f.write("class App:\n    pass\n")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _scan(self) -> ScanResult:
        engine = ScannerEngine()
        return engine.scan(self.tmpdir)

    def test_context_with_tree(self):
        """Контекст содержит дерево файлов."""
        result = self._scan()
        opts = ContextOptions(include_tree=True, include_contents=False)
        engine = ScannerEngine()
        context = engine.generate_context(result, options=opts)
        self.assertIn("Project:", context)
        self.assertIn("File Tree", context)

    def test_context_with_contents(self):
        """Контекст содержит содержимое файлов."""
        result = self._scan()
        opts = ContextOptions(include_contents=True)
        engine = ScannerEngine()
        context = engine.generate_context(result, options=opts)
        self.assertIn("hello world", context)

    def test_context_with_line_numbers(self):
        """Контекст с нумерацией строк."""
        result = self._scan()
        opts = ContextOptions(include_contents=True, line_numbers=True)
        engine = ScannerEngine()
        context = engine.generate_context(result, options=opts)
        self.assertIn("1 |", context)
        self.assertIn("2 |", context)

    def test_context_without_line_numbers(self):
        """Контекст без нумерации строк."""
        result = self._scan()
        opts = ContextOptions(include_contents=True, line_numbers=False)
        engine = ScannerEngine()
        context = engine.generate_context(result, options=opts)
        # Не должно быть "1 |" в начале строки контента
        lines = context.split("\n")
        content_lines = [l for l in lines if "hello world" in l]
        for line in content_lines:
            self.assertFalse(line.strip().startswith("1 |"))

    def test_context_without_tree(self):
        """Контекст без дерева файлов."""
        result = self._scan()
        opts = ContextOptions(include_tree=False, include_contents=False)
        engine = ScannerEngine()
        context = engine.generate_context(result, options=opts)
        self.assertNotIn("File Tree", context)

    def test_context_selected_files(self):
        """Контекст только для выбранных файлов."""
        result = self._scan()
        opts = ContextOptions(include_contents=True, line_numbers=False)
        engine = ScannerEngine()
        context = engine.generate_context(result, selected_files=["main.py"], options=opts)
        self.assertIn("hello world", context)
        self.assertNotIn("class App:", context)

    def test_context_token_limit(self):
        """Ограничение токенов в контексте."""
        result = self._scan()
        opts = ContextOptions(include_contents=True, max_tokens=10)
        engine = ScannerEngine()
        context = engine.generate_context(result, options=opts)
        self.assertIn("обрезано", context)

    def test_context_languages_in_header(self):
        """Заголовок контекста содержит информацию о языках."""
        result = self._scan()
        opts = ContextOptions(include_contents=False)
        engine = ScannerEngine()
        context = engine.generate_context(result, options=opts)
        self.assertIn("Languages:", context)
        self.assertIn("Python", context)

    def test_context_sort_by_path(self):
        """Сортировка файлов по пути."""
        result = self._scan()
        opts = ContextOptions(include_contents=True, sort_by="path", line_numbers=False)
        engine = ScannerEngine()
        context = engine.generate_context(result, options=opts)
        # Файлы должны присутствовать в контексте
        self.assertIn("main.py", context)
        self.assertIn("app.py", context)

    def test_context_sort_by_tokens(self):
        """Сортировка файлов по токенам."""
        result = self._scan()
        opts = ContextOptions(include_contents=True, sort_by="tokens", line_numbers=False)
        engine = ScannerEngine()
        context = engine.generate_context(result, options=opts)
        self.assertIn("main.py", context)

    def test_context_file_stats(self):
        """Статистика файлов в заголовке."""
        result = self._scan()
        opts = ContextOptions(include_contents=True, show_file_stats=True, line_numbers=False)
        engine = ScannerEngine()
        context = engine.generate_context(result, options=opts)
        self.assertIn("tokens", context)

    def test_context_no_file_stats(self):
        """Без статистики файлов."""
        result = self._scan()
        opts = ContextOptions(include_contents=True, show_file_stats=False, line_numbers=False)
        engine = ScannerEngine()
        context = engine.generate_context(result, options=opts)
        # Не должно быть деталей статистики в заголовках файлов
        # (но может быть в глобальной статистике)


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

    def test_estimate_tokens_for_files(self):
        """Оценка токенов для указанных файлов."""
        engine = ScannerEngine()
        tokens = engine.estimate_tokens_for_files(["a.py", "b.js"], self.tmpdir)
        self.assertGreater(tokens, 0)

    def test_get_all_known_extensions(self):
        """Получение всех известных расширений."""
        exts = ScannerEngine.get_all_known_extensions()
        self.assertIn(".py", exts)
        self.assertIn(".js", exts)
        self.assertIn(".rs", exts)

    def test_get_all_known_languages(self):
        """Получение всех известных языков."""
        langs = ScannerEngine.get_all_known_languages()
        self.assertIn("Python", langs)
        self.assertIn("Rust", langs)

    def test_line_numbers(self):
        """Нумерация строк."""
        text = "line1\nline2\nline3"
        result = ScannerEngine._add_line_numbers(text, width=2)
        self.assertIn(" 1 | line1", result)
        self.assertIn(" 2 | line2", result)
        self.assertIn(" 3 | line3", result)

    def test_line_numbers_auto_width(self):
        """Автоматическая ширина номера строки."""
        lines = [f"line{i}" for i in range(1, 101)]
        text = "\n".join(lines)
        result = ScannerEngine._add_line_numbers(text, width=2)
        # Для 100 строк ширина должна быть минимум 3
        self.assertIn("100 | line100", result)

    def test_token_estimation_code(self):
        """Оценка токенов для кода."""
        code = "def hello():\n    print('world')\n"
        tokens = ScannerEngine._estimate_tokens(code)
        self.assertGreater(tokens, 0)
        # Код ~3.5 символа/токен
        self.assertAlmostEqual(tokens, len(code) / 3.5, delta=2)

    def test_token_estimation_empty(self):
        """Оценка токенов для пустого текста."""
        self.assertEqual(ScannerEngine._estimate_tokens(""), 0)


if __name__ == "__main__":
    unittest.main()
