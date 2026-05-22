"""
Исполнитель консольных команд.

Выполняет команды из патча в фоновом потоке с захватом вывода,
таймаутом и обнаружением опасных паттернов.
"""

import subprocess
from typing import Dict, List

from PyQt6.QtCore import QThread, pyqtSignal

from ai_patcher_pro.core.command_utils import normalize_command, check_dangerous_command


class CommandExecutorThread(QThread):
    """
    Фоновый поток для последовательного выполнения консольных команд.

    Сигналы:
        command_done: Отправляется после завершения каждой команды.
        finished_all: Отправляется после завершения всех команд.
    """

    command_done = pyqtSignal(dict)
    finished_all = pyqtSignal()

    # Таймаут выполнения одной команды (секунды)
    COMMAND_TIMEOUT = 300

    def __init__(self, commands: List[Dict], workspace: str):
        """
        Args:
            commands: Список нормализованных команд (после normalize_command).
            workspace: Рабочая директория для выполнения команд.
        """
        super().__init__()
        self.commands = commands
        self.workspace = workspace

    def run(self) -> None:
        """Выполняет все команды последовательно."""
        for cmd_info in self.commands:
            result = self._execute_single(cmd_info)
            self.command_done.emit(result)
        self.finished_all.emit()

    def _execute_single(self, cmd_info: Dict) -> Dict:
        """
        Выполняет одну команду через subprocess.

        Args:
            cmd_info: Словарь команды с ключами cmd, run, description, warnings.

        Returns:
            Результат выполнения с полями:
            cmd, description, status, stdout, stderr, returncode, warnings.
        """
        cmd = cmd_info.get("cmd", "")
        description = cmd_info.get("description", "")
        warnings = cmd_info.get("warnings", [])

        if not cmd:
            return {
                "cmd": cmd,
                "description": description,
                "status": "error",
                "stdout": "",
                "stderr": "Пустая команда.",
                "returncode": -1,
                "warnings": warnings,
            }

        try:
            process = subprocess.Popen(
                cmd,
                shell=True,
                cwd=self.workspace,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                stdout, stderr = process.communicate(timeout=self.COMMAND_TIMEOUT)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                return {
                    "cmd": cmd,
                    "description": description,
                    "status": "error",
                    "stdout": stdout or "",
                    "stderr": f"Таймаут выполнения команды ({self.COMMAND_TIMEOUT} сек). Процесс завершён принудительно.",
                    "returncode": -1,
                    "warnings": warnings,
                }

            return {
                "cmd": cmd,
                "description": description,
                "status": "success" if process.returncode == 0 else "error",
                "stdout": stdout or "",
                "stderr": stderr or "",
                "returncode": process.returncode or 0,
                "warnings": warnings,
            }

        except FileNotFoundError:
            return {
                "cmd": cmd,
                "description": description,
                "status": "error",
                "stdout": "",
                "stderr": f"Команда не найдена: {cmd.split()[0] if cmd.split() else cmd}",
                "returncode": -1,
                "warnings": warnings,
            }
        except PermissionError:
            return {
                "cmd": cmd,
                "description": description,
                "status": "error",
                "stdout": "",
                "stderr": "Недостаточно прав для выполнения команды. Запустите приложение от имени администратора.",
                "returncode": -1,
                "warnings": warnings,
            }
        except OSError as e:
            return {
                "cmd": cmd,
                "description": description,
                "status": "error",
                "stdout": "",
                "stderr": f"Ошибка ОС: {e}",
                "returncode": -1,
                "warnings": warnings,
            }
        except Exception as e:
            return {
                "cmd": cmd,
                "description": description,
                "status": "error",
                "stdout": "",
                "stderr": f"Непредвиденная ошибка: {e}",
                "returncode": -1,
                "warnings": warnings,
            }
