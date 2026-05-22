"""
Исполнитель консольных команд с потоковым выводом.

Выполняет команды из патча в фоновом потоке с захватом вывода,
таймаутом и обнаружением опасных паттернов.

Сигналы реального времени:
- command_started: команда начала выполняться
- command_output: потоковый stdout/stderr в реальном времени
- command_done: команда завершилась
- finished_all: все команды выполнены
"""

import subprocess
import threading
from typing import Dict, List

from PyQt6.QtCore import QThread, pyqtSignal

from ai_patcher_pro.core.command_utils import normalize_command, check_dangerous_command


class CommandExecutorThread(QThread):
    """
    Фоновый поток для последовательного выполнения консольных команд.

    Поддерживает потоковый вывод stdout/stderr в реальном времени,
    чтобы пользователь видел прогресс выполнения.

    Сигналы:
        command_started: Команда начала выполняться (index, cmd, description).
        command_output: Порция вывода команды (index, stream_type, data).
            stream_type: "stdout" или "stderr"
        command_done: Отправляется после завершения каждой команды.
        finished_all: Отправляется после завершения всех команд.
    """

    command_started = pyqtSignal(int, str, str)   # index, cmd, description
    command_output = pyqtSignal(int, str, str)     # index, stream_type, data
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
        for i, cmd_info in enumerate(self.commands):
            result = self._execute_single(i, cmd_info)
            self.command_done.emit(result)
        self.finished_all.emit()

    def _execute_single(self, index: int, cmd_info: Dict) -> Dict:
        """
        Выполняет одну команду через subprocess с потоковым выводом.

        Args:
            index: Порядковый номер команды.
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

        # Сигнал: команда начала выполняться
        self.command_started.emit(index, cmd, description)

        try:
            process = subprocess.Popen(
                cmd,
                shell=True,
                cwd=self.workspace,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # Построчная буферизация
            )

            # Собираем вывод в реальном времени
            stdout_parts: List[str] = []
            stderr_parts: List[str] = []

            # Поток для чтения stderr
            def _read_stderr():
                try:
                    for line in iter(process.stderr.readline, ""):
                        if line:
                            stderr_parts.append(line)
                            self.command_output.emit(index, "stderr", line)
                except (ValueError, OSError):
                    pass

            stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
            stderr_thread.start()

            # Читаем stdout в основном потоке QThread
            try:
                for line in iter(process.stdout.readline, ""):
                    if line:
                        stdout_parts.append(line)
                        self.command_output.emit(index, "stdout", line)
            except (ValueError, OSError):
                pass

            # Ждём завершения с таймаутом
            try:
                process.wait(timeout=self.COMMAND_TIMEOUT)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

                # Даём stderr-потоку время досчитать
                stderr_thread.join(timeout=2)

                return {
                    "cmd": cmd,
                    "description": description,
                    "status": "error",
                    "stdout": "".join(stdout_parts),
                    "stderr": (
                        f"Таймаут выполнения команды ({self.COMMAND_TIMEOUT} сек). "
                        f"Процесс завершён принудительно.\n"
                        + "".join(stderr_parts)
                    ),
                    "returncode": -1,
                    "warnings": warnings,
                }

            # Ждём завершения stderr-потока
            stderr_thread.join(timeout=5)

            # Если процесс завершился, но stderr ещё что-то читает — дочитываем
            remaining_stderr = process.stderr.read()
            if remaining_stderr:
                stderr_parts.append(remaining_stderr)
                self.command_output.emit(index, "stderr", remaining_stderr)

            returncode = process.returncode if process.returncode is not None else 0

            return {
                "cmd": cmd,
                "description": description,
                "status": "success" if returncode == 0 else "error",
                "stdout": "".join(stdout_parts),
                "stderr": "".join(stderr_parts),
                "returncode": returncode,
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
