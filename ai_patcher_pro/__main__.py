"""Точка входа в приложение AI Patcher Pro."""

import ctypes
import os
import sys

from PyQt6.QtWidgets import QApplication, QMessageBox

from ai_patcher_pro.gui.styles import STYLESHEET
from ai_patcher_pro.gui.main_window import AIPatcherPro


def is_admin() -> bool:
    """
    Проверяет, запущено ли приложение с правами администратора.

    Returns:
        True если запущено с правами администратора/root.
    """
    try:
        if sys.platform == "win32":
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        else:
            return os.geteuid() == 0
    except (AttributeError, OSError):
        return False


def run_as_admin() -> int:
    """
    Перезапускает приложение с правами администратора.

    На Windows использует ShellExecuteW с глаголом "runas".
    На Linux/macOS выводит инструкцию использовать sudo.

    Returns:
        0 при успешном перезапуске, 1 при ошибке.
    """
    if sys.platform == "win32":
        script = os.path.abspath(sys.argv[0])
        params = " ".join([script] + sys.argv[1:])
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, params, None, 1
        )
        if ret <= 32:
            print(f"Не удалось перезапустить от имени администратора (код {ret})")
            return 1
        return 0
    else:
        print(
            "Запустите приложение с правами суперпользователя:\n"
            f"  sudo python3 {' '.join(sys.argv)}"
        )
        return 1


def main() -> int:
    """Запуск приложения."""
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    app.setApplicationName("AI Patcher Pro")
    app.setApplicationVersion("3.2.0")

    # Проверка прав администратора
    if not is_admin():
        if sys.platform == "win32":
            msg_box = QMessageBox()
            msg_box.setIcon(QMessageBox.Icon.Warning)
            msg_box.setWindowTitle("Требуются права администратора")
            msg_box.setText(
                "AI Patcher Pro требует запуска от имени администратора\n"
                "для корректного выполнения консольных команд."
            )
            msg_box.setInformativeText(
                "Перезапустить с правами администратора?"
            )
            msg_box.setStandardButtons(
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            msg_box.setDefaultButton(QMessageBox.StandardButton.Yes)

            if msg_box.exec() == QMessageBox.StandardButton.Yes:
                result = run_as_admin()
                sys.exit(result)
            else:
                sys.exit(1)
        else:
            msg_box = QMessageBox()
            msg_box.setIcon(QMessageBox.Icon.Warning)
            msg_box.setWindowTitle("Требуются права root")
            msg_box.setText(
                "AI Patcher Pro требует запуска с правами суперпользователя\n"
                "для корректного выполнения консольных команд."
            )
            msg_box.setInformativeText(
                f"Запустите:\n  sudo python3 {' '.join(sys.argv)}"
            )
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg_box.exec()
            sys.exit(1)

    window = AIPatcherPro()
    window.show()

    return app.exec()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback
        traceback.print_exc()
        print("\nНажмите Enter для выхода...")
        input()
