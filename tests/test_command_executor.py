"""
Тесты для модуля command_executor.

Покрывает:
- normalize_command: строка, словарь, альтернативные имена, пустые значения
- check_dangerous_command: опасные и безопасные паттерны
- CommandExecutorThread: успешное выполнение, ошибка, таймаут
- Сигналы реального времени: command_started, command_output

ПРИМЕЧАНИЕ: Тесты CommandExecutorThread требуют QApplication для работы
сигналов/слотов Qt. Если QApplication не может быть создан (headless env),
эти тесты пропускаются.
"""

import os
import sys
import unittest

from ai_patcher_pro.core.command_utils import (
    normalize_command,
    check_dangerous_command,
)

# Проверяем доступность Qt для GUI-тестов
_QT_AVAILABLE = False
try:
    from PyQt6.QtWidgets import QApplication
    _QT_AVAILABLE = True
except ImportError:
    pass


class TestNormalizeCommand(unittest.TestCase):
    """Тесты нормализации команд из ответа ИИ."""

    def test_string_command(self):
        """Строка преобразуется в полный словарь с run=after_apply."""
        result = normalize_command("npm install")
        self.assertEqual(result["cmd"], "npm install")
        self.assertEqual(result["run"], "after_apply")
        self.assertEqual(result["description"], "")
        self.assertEqual(result["warnings"], [])

    def test_string_command_with_leading_spaces(self):
        """Пробелы обрезаются."""
        result = normalize_command("  pip install requests  ")
        self.assertEqual(result["cmd"], "pip install requests")

    def test_dict_command_basic(self):
        """Словарь с стандартными полями."""
        result = normalize_command({
            "cmd": "pytest tests/",
            "run": "after_analysis",
            "description": "Запуск тестов",
        })
        self.assertEqual(result["cmd"], "pytest tests/")
        self.assertEqual(result["run"], "after_analysis")
        self.assertEqual(result["description"], "Запуск тестов")

    def test_dict_command_after_apply(self):
        """run=after_apply остаётся after_apply."""
        result = normalize_command({"cmd": "npm run build", "run": "after_apply"})
        self.assertEqual(result["run"], "after_apply")

    def test_alternative_cmd_names(self):
        """Альтернативные имена для cmd: command, exec, shell."""
        for alias in ("command", "exec", "shell"):
            result = normalize_command({alias: "echo hello"})
            self.assertEqual(result["cmd"], "echo hello")

    def test_alternative_run_names(self):
        """Альтернативные имена для run: timing, when, phase."""
        for alias in ("timing", "when", "phase"):
            result = normalize_command({"cmd": "echo test", alias: "after_analysis"})
            self.assertEqual(result["run"], "after_analysis")

    def test_alternative_run_values_analysis(self):
        """Альтернативные значения run для after_analysis."""
        for val in ("analysis", "analyze", "before_apply"):
            result = normalize_command({"cmd": "echo test", "run": val})
            self.assertEqual(result["run"], "after_analysis")

    def test_default_run_is_after_apply(self):
        """По умолчанию run=after_apply."""
        result = normalize_command({"cmd": "echo test"})
        self.assertEqual(result["run"], "after_apply")

    def test_alternative_description_names(self):
        """Альтернативные имена для description: desc, comment, note."""
        for alias in ("desc", "comment", "note"):
            result = normalize_command({"cmd": "echo test", alias: "My description"})
            self.assertEqual(result["description"], "My description")

    def test_empty_cmd_string(self):
        """Пустая строка — пустая команда."""
        result = normalize_command("")
        self.assertEqual(result["cmd"], "")
        self.assertEqual(result["warnings"], [])

    def test_empty_cmd_dict(self):
        """Словарь без cmd/command/exec/shell — пустая команда."""
        result = normalize_command({"run": "after_apply"})
        self.assertEqual(result["cmd"], "")

    def test_unknown_format_fallback(self):
        """Неизвестный формат конвертируется в строку."""
        result = normalize_command(42)
        self.assertEqual(result["cmd"], "42")

    def test_dangerous_command_warnings_included(self):
        """Опасная команда содержит предупреждения."""
        result = normalize_command("rm -rf /tmp/test")
        self.assertTrue(len(result["warnings"]) > 0)

    def test_dangerous_cmd_in_dict(self):
        """Опасная команда в словаре тоже детектируется."""
        result = normalize_command({"cmd": "sudo rm -rf /", "run": "after_apply"})
        self.assertTrue(len(result["warnings"]) > 0)

    def test_safe_command_no_warnings(self):
        """Безопасная команда без предупреждений."""
        result = normalize_command("pip install requests")
        self.assertEqual(result["warnings"], [])


class TestCheckDangerousCommand(unittest.TestCase):
    """Тесты обнаружения опасных паттернов команд."""

    def test_rm_rf(self):
        """rm -rf обнаруживается."""
        warnings = check_dangerous_command("rm -rf /tmp/test")
        self.assertTrue(any("rm -rf" in w for w in warnings))

    def test_sudo_rm(self):
        """sudo rm обнаруживается."""
        warnings = check_dangerous_command("sudo rm /etc/passwd")
        self.assertTrue(any("sudo rm" in w for w in warnings))

    def test_format_drive(self):
        """format C: обнаруживается."""
        warnings = check_dangerous_command("format C:")
        self.assertTrue(any("format" in w for w in warnings))

    def test_shutdown(self):
        """shutdown обнаруживается."""
        warnings = check_dangerous_command("shutdown -h now")
        self.assertTrue(any("shutdown" in w for w in warnings))

    def test_chmod_777(self):
        """chmod -R 777 обнаруживается."""
        warnings = check_dangerous_command("chmod -R 777 /var/www")
        self.assertTrue(any("chmod" in w for w in warnings))

    def test_safe_command(self):
        """Безопасная команда не даёт предупреждений."""
        warnings = check_dangerous_command("pip install requests")
        self.assertEqual(warnings, [])

    def test_safe_npm_install(self):
        """npm install безопасна."""
        warnings = check_dangerous_command("npm install express")
        self.assertEqual(warnings, [])

    def test_safe_pytest(self):
        """pytest безопасен."""
        warnings = check_dangerous_command("pytest tests/")
        self.assertEqual(warnings, [])

    def test_taskkill(self):
        """taskkill /f обнаруживается."""
        warnings = check_dangerous_command("taskkill /f /im python.exe")
        self.assertTrue(any("taskkill" in w for w in warnings))

    def test_dd_command(self):
        """dd if= обнаруживается."""
        warnings = check_dangerous_command("dd if=/dev/zero of=/dev/sda")
        self.assertTrue(any("dd" in w for w in warnings))

    def test_case_insensitive(self):
        """Поиск опасных паттернов нечувствителен к регистру."""
        warnings = check_dangerous_command("RM -RF /tmp")
        self.assertTrue(len(warnings) > 0)


@unittest.skipUnless(_QT_AVAILABLE, "PyQt6 не доступен (headless окружение)")
class TestCommandExecutorThread(unittest.TestCase):
    """
    Тесты фонового выполнения команд.

    Требует QApplication для корректной работы сигналов Qt.
    """

    @classmethod
    def setUpClass(cls):
        """Создаёт QApplication если его нет."""
        from PyQt6.QtWidgets import QApplication
        if not QApplication.instance():
            try:
                cls._app = QApplication(sys.argv)
            except Exception:
                raise unittest.SkipTest("Не удалось создать QApplication (headless env)")

    def _run_thread_and_collect(self, thread, timeout=10000):
        """Запускает поток и собирает результаты через event loop."""
        results = []
        finished_flag = []
        started_events = []
        output_events = []

        thread.command_done.connect(lambda r: results.append(r))
        thread.finished_all.connect(lambda: finished_flag.append(True))
        thread.command_started.connect(lambda i, c, d: started_events.append((i, c, d)))
        thread.command_output.connect(lambda i, s, d: output_events.append((i, s, d)))
        thread.start()

        # Обработка событий Qt пока поток не завершится
        elapsed = 0
        while not finished_flag and elapsed < timeout:
            TestCommandExecutorThread._app.processEvents()
            thread.msleep(10)
            elapsed += 10

        thread.wait(timeout)
        return results, finished_flag, started_events, output_events

    def test_successful_command(self):
        """Успешная команда возвращает status=success и stdout."""
        from ai_patcher_pro.core.command_executor import CommandExecutorThread

        commands = [normalize_command("echo hello")]
        thread = CommandExecutorThread(commands, os.getcwd())

        results, finished, started, output = self._run_thread_and_collect(thread)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "success")
        self.assertIn("hello", results[0]["stdout"])
        self.assertEqual(results[0]["returncode"], 0)

    def test_failed_command(self):
        """Несуществующая команда возвращает status=error."""
        from ai_patcher_pro.core.command_executor import CommandExecutorThread

        commands = [normalize_command("nonexistent_command_xyz_12345")]
        thread = CommandExecutorThread(commands, os.getcwd())

        results, finished, started, output = self._run_thread_and_collect(thread)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "error")
        self.assertNotEqual(results[0]["returncode"], 0)

    def test_command_with_stderr(self):
        """Команда с stderr его захватывает."""
        from ai_patcher_pro.core.command_executor import CommandExecutorThread

        if sys.platform == "win32":
            cmd = "echo error 1>&2"
        else:
            cmd = "echo error >&2"

        commands = [normalize_command(cmd)]
        thread = CommandExecutorThread(commands, os.getcwd())

        results, finished, started, output = self._run_thread_and_collect(thread)
        self.assertEqual(len(results), 1)
        self.assertIn("error", results[0]["stderr"])

    def test_multiple_commands(self):
        """Несколько команд выполняются последовательно."""
        from ai_patcher_pro.core.command_executor import CommandExecutorThread

        commands = [
            normalize_command("echo first"),
            normalize_command("echo second"),
        ]
        thread = CommandExecutorThread(commands, os.getcwd())

        results, finished, started, output = self._run_thread_and_collect(thread)
        self.assertEqual(len(results), 2)
        self.assertIn("first", results[0]["stdout"])
        self.assertIn("second", results[1]["stdout"])

    def test_empty_command(self):
        """Пустая команда возвращает ошибку."""
        from ai_patcher_pro.core.command_executor import CommandExecutorThread

        commands = [normalize_command("")]
        thread = CommandExecutorThread(commands, os.getcwd())

        results, finished, started, output = self._run_thread_and_collect(thread)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "error")
        self.assertIn("Пустая команда", results[0]["stderr"])

    def test_description_preserved(self):
        """Описание сохраняется в результате."""
        from ai_patcher_pro.core.command_executor import CommandExecutorThread

        commands = [normalize_command({
            "cmd": "echo test",
            "description": "Тестовая команда",
        })]
        thread = CommandExecutorThread(commands, os.getcwd())

        results, finished, started, output = self._run_thread_and_collect(thread)
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0]["description"], "Тестовая команда")

    def test_warnings_preserved(self):
        """Предупреждения безопасности сохраняются в результате."""
        from ai_patcher_pro.core.command_executor import CommandExecutorThread

        commands = [normalize_command("rm -rf /tmp/test")]
        thread = CommandExecutorThread(commands, os.getcwd())

        results, finished, started, output = self._run_thread_and_collect(thread)
        self.assertTrue(len(results) > 0)
        self.assertTrue(len(results[0]["warnings"]) > 0)

    def test_finished_all_signal(self):
        """Сигнал finished_all отправляется после всех команд."""
        from ai_patcher_pro.core.command_executor import CommandExecutorThread

        commands = [normalize_command("echo done")]
        thread = CommandExecutorThread(commands, os.getcwd())

        results, finished, started, output = self._run_thread_and_collect(thread)
        self.assertTrue(finished)

    def test_command_started_signal(self):
        """Сигнал command_started отправляется перед выполнением команды."""
        from ai_patcher_pro.core.command_executor import CommandExecutorThread

        commands = [normalize_command({"cmd": "echo hello", "description": "test desc"})]
        thread = CommandExecutorThread(commands, os.getcwd())

        results, finished, started, output = self._run_thread_and_collect(thread)
        self.assertEqual(len(started), 1)
        self.assertEqual(started[0][0], 0)  # index
        self.assertIn("echo hello", started[0][1])  # cmd
        self.assertEqual(started[0][2], "test desc")  # description

    def test_command_output_signal_stdout(self):
        """Сигнал command_output отправляется с потоковым stdout."""
        from ai_patcher_pro.core.command_executor import CommandExecutorThread

        commands = [normalize_command("echo hello_world_output")]
        thread = CommandExecutorThread(commands, os.getcwd())

        results, finished, started, output = self._run_thread_and_collect(thread)
        # Должны получить хотя бы одно событие output со stdout
        stdout_events = [(i, s, d) for i, s, d in output if s == "stdout"]
        self.assertTrue(len(stdout_events) > 0, "Должен быть хотя бы один stdout output")
        combined_stdout = "".join(d for _, _, d in stdout_events)
        self.assertIn("hello_world_output", combined_stdout)

    def test_command_started_multiple(self):
        """command_started вызывается для каждой команды."""
        from ai_patcher_pro.core.command_executor import CommandExecutorThread

        commands = [
            normalize_command("echo a"),
            normalize_command("echo b"),
            normalize_command("echo c"),
        ]
        thread = CommandExecutorThread(commands, os.getcwd())

        results, finished, started, output = self._run_thread_and_collect(thread)
        self.assertEqual(len(started), 3)
        self.assertEqual(started[0][0], 0)
        self.assertEqual(started[1][0], 1)
        self.assertEqual(started[2][0], 2)


if __name__ == "__main__":
    unittest.main()
