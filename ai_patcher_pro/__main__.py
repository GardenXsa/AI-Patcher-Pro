"""Точка входа в приложение AI Patcher Pro."""

import sys
from PyQt6.QtWidgets import QApplication
from ai_patcher_pro.gui.styles import STYLESHEET
from ai_patcher_pro.gui.main_window import AIPatcherPro


def main() -> int:
    """Запуск приложения."""
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    app.setApplicationName("AI Patcher Pro")
    app.setApplicationVersion("2.0.0")

    window = AIPatcherPro()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
