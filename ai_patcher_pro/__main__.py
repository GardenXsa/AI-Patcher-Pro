"""Точка входа в приложение AI Patcher Pro.

Исправления для собранного EXE:
- корректный перезапуск от администратора в PyInstaller/frozen режиме;
- больше не закрываем приложение молча, если elevation не удался;
- можно продолжить без администратора в ограниченном режиме;
- любые startup-crash ошибки пишутся в ai_patcher_pro_crash.log и показываются окном.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import traceback
from datetime import datetime
from typing import Tuple

from PyQt6.QtWidgets import QApplication, QMessageBox

from ai_patcher_pro.gui.styles import STYLESHEET
from ai_patcher_pro.gui.main_window import AIPatcherPro


APP_NAME = "AI Patcher Pro"
APP_VERSION = "3.2.0"


def is_frozen_app() -> bool:
    """True если приложение запущено как PyInstaller/frozen executable."""
    return bool(getattr(sys, "frozen", False))


def is_admin() -> bool:
    """
    Проверяет, запущено ли приложение с правами администратора.

    Returns:
        True если запущено с правами администратора/root.
    """
    try:
        if sys.platform == "win32":
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        return os.geteuid() == 0
    except (AttributeError, OSError):
        return False


def _build_relaunch_command() -> Tuple[str, str]:
    """
    Возвращает executable и parameters для ShellExecuteW(runas).

    Важно для PyInstaller:
    - frozen EXE надо запускать как file=sys.executable;
    - параметры должны содержать только sys.argv[1:], а не путь к EXE ещё раз.

    Для запуска из исходников:
    - file=sys.executable;
    - parameters="путь_к___main__.py/модулю + args".
    """
    if is_frozen_app():
        executable = sys.executable
        params = subprocess.list2cmdline(sys.argv[1:])
        return executable, params

    script = os.path.abspath(sys.argv[0])
    executable = sys.executable
    params = subprocess.list2cmdline([script, *sys.argv[1:]])
    return executable, params


def run_as_admin() -> Tuple[bool, str]:
    """
    Перезапускает приложение с правами администратора.

    На Windows использует ShellExecuteW с глаголом "runas".
    На Linux/macOS автоматический GUI-relaunch не выполняется.

    Returns:
        (success, message)
    """
    if sys.platform == "win32":
        executable, params = _build_relaunch_command()
        cwd = os.getcwd()

        try:
            ret = ctypes.windll.shell32.ShellExecuteW(
                None,
                "runas",
                executable,
                params,
                cwd,
                1,
            )
        except Exception as e:
            return False, f"Ошибка ShellExecuteW/runas: {e}"

        if ret <= 32:
            return (
                False,
                "Не удалось перезапустить от имени администратора.\n"
                f"ShellExecuteW вернул код {ret}.\n\n"
                f"Executable: {executable}\n"
                f"Params: {params}\n"
                f"Working directory: {cwd}",
            )

        return True, "Перезапуск от имени администратора запущен."

    return (
        False,
        "Автоматический перезапуск с sudo не поддерживается.\n"
        f"Запустите вручную:\n  sudo {sys.executable} {' '.join(sys.argv)}",
    )


def ask_admin_or_continue() -> bool:
    """
    Спрашивает пользователя, перезапускаться ли с правами администратора.

    Returns:
        True если нужно продолжить текущий процесс.
        False если текущий процесс должен завершиться.
    """
    if is_admin():
        return True

    if sys.platform == "win32":
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setWindowTitle("Права администратора")
        msg_box.setText(
            "AI Patcher Pro запущен без прав администратора."
        )
        msg_box.setInformativeText(
            "Права администратора нужны только для команд, которым требуется повышенный доступ.\n\n"
            "Да — перезапустить от имени администратора.\n"
            "Нет — продолжить без администратора.\n"
            "Отмена — закрыть приложение."
        )
        msg_box.setStandardButtons(
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel
        )
        msg_box.setDefaultButton(QMessageBox.StandardButton.Yes)

        choice = msg_box.exec()
        if choice == QMessageBox.StandardButton.Yes:
            success, message = run_as_admin()
            if success:
                return False

            QMessageBox.critical(
                None,
                "Не удалось повысить права",
                message + "\n\nПриложение продолжит работу без администратора.",
            )
            return True

        if choice == QMessageBox.StandardButton.No:
            QMessageBox.information(
                None,
                "Ограниченный режим",
                "Приложение продолжит работу без администратора.\n"
                "Если команда потребует повышенных прав, она завершится ошибкой, "
                "но само приложение не закроется.",
            )
            return True

        return False

    msg_box = QMessageBox()
    msg_box.setIcon(QMessageBox.Icon.Warning)
    msg_box.setWindowTitle("Права root")
    msg_box.setText("AI Patcher Pro запущен без прав root.")
    msg_box.setInformativeText(
        "Можно продолжить в ограниченном режиме или закрыть приложение и запустить через sudo."
    )
    msg_box.setStandardButtons(
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
    )
    msg_box.button(QMessageBox.StandardButton.Yes).setText("Продолжить")
    msg_box.button(QMessageBox.StandardButton.Cancel).setText("Закрыть")
    return msg_box.exec() == QMessageBox.StandardButton.Yes


def _crash_log_path() -> str:
    """Возвращает путь к crash log рядом с exe/рабочей папкой, с fallback в TEMP."""
    candidates = []

    if is_frozen_app():
        candidates.append(os.path.dirname(os.path.abspath(sys.executable)))

    candidates.append(os.getcwd())
    candidates.append(os.environ.get("TEMP", ""))

    for directory in candidates:
        if not directory:
            continue
        try:
            os.makedirs(directory, exist_ok=True)
            test_path = os.path.join(directory, "ai_patcher_pro_crash.log")
            with open(test_path, "a", encoding="utf-8"):
                pass
            return test_path
        except OSError:
            continue

    return "ai_patcher_pro_crash.log"


def write_crash_log(exc_text: str) -> str:
    """Пишет traceback в crash log и возвращает путь."""
    path = _crash_log_path()
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write("\n" + "=" * 80 + "\n")
        f.write(f"{APP_NAME} crash at {datetime.now().isoformat(timespec='seconds')}\n")
        f.write(f"sys.executable: {sys.executable}\n")
        f.write(f"sys.argv: {sys.argv}\n")
        f.write(f"cwd: {os.getcwd()}\n")
        f.write(f"frozen: {is_frozen_app()}\n")
        f.write("\n")
        f.write(exc_text)
        f.write("\n")
    return path


def show_crash_dialog(exc_text: str, log_path: str) -> None:
    """Показывает понятную ошибку запуска вместо молчаливого закрытия EXE."""
    app = QApplication.instance()
    created_app = False
    if app is None:
        app = QApplication(sys.argv)
        created_app = True

    msg = QMessageBox()
    msg.setIcon(QMessageBox.Icon.Critical)
    msg.setWindowTitle("AI Patcher Pro — ошибка запуска")
    msg.setText("Приложение упало при запуске.")
    msg.setInformativeText(
        "Подробный traceback сохранён в файл:\n"
        f"{log_path}\n\n"
        "Скопируйте этот файл или его содержимое GPT вместо скриншота."
    )
    msg.setDetailedText(exc_text)
    msg.setStandardButtons(QMessageBox.StandardButton.Ok)
    msg.exec()

    if created_app:
        app.quit()


def main() -> int:
    """Запуск приложения."""
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)

    if not ask_admin_or_continue():
        return 0

    window = AIPatcherPro()
    window.show()

    return app.exec()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        exc_text = traceback.format_exc()
        print(exc_text)
        try:
            log_path = write_crash_log(exc_text)
        except Exception:
            log_path = "Не удалось записать crash log"
        try:
            show_crash_dialog(exc_text, log_path)
        except Exception:
            pass
        sys.exit(1)
