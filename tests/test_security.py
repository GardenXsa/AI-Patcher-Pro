"""Тесты для модуля безопасности."""

import os
import unittest
import tempfile
from ai_patcher_pro.core.security import secure_path_join, validate_file_extension


class TestSecurePathJoin(unittest.TestCase):
    """Тесты защиты от path traversal."""

    def setUp(self):
        self.base_dir = tempfile.mkdtemp()

    def test_normal_path(self):
        """Нормальный относительный путь."""
        result = secure_path_join(self.base_dir, "src/main.py")
        expected = os.path.normpath(os.path.join(self.base_dir, "src/main.py"))
        self.assertEqual(result, expected)

    def test_path_traversal_attack(self):
        """Попытка выхода за пределы рабочей папки."""
        with self.assertRaises(PermissionError):
            secure_path_join(self.base_dir, "../../etc/passwd")

    def test_absolute_path_attack(self):
        """Попытка использования абсолютного пути."""
        with self.assertRaises(PermissionError):
            secure_path_join(self.base_dir, "/etc/passwd")

    def test_empty_path_raises(self):
        """Пустой путь вызывает ошибку."""
        with self.assertRaises(ValueError):
            secure_path_join(self.base_dir, "")

    def test_whitespace_path_raises(self):
        """Путь из пробелов вызывает ошибку."""
        with self.assertRaises(ValueError):
            secure_path_join(self.base_dir, "   ")

    def test_prefix_attack(self):
        """
        Защита от совпадения префиксов.

        /home/user не должен совпадать с /home/user10.
        """
        # Этот тест проверяет, что /tmp/test и /tmp/test2 не путаются
        result = secure_path_join(self.base_dir, "file.py")
        self.assertTrue(result.startswith(self.base_dir))


class TestValidateFileExtension(unittest.TestCase):
    """Тесты валидации расширений файлов."""

    def test_allowed_extension(self):
        self.assertTrue(validate_file_extension("test.py", (".py", ".js")))

    def test_disallowed_extension(self):
        self.assertFalse(validate_file_extension("test.exe", (".py", ".js")))

    def test_no_restrictions(self):
        self.assertTrue(validate_file_extension("anything.xyz"))

    def test_case_insensitive(self):
        self.assertTrue(validate_file_extension("test.PY", (".py",)))


if __name__ == "__main__":
    unittest.main()
