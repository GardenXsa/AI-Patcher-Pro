"""
QSS стили приложения — тёмная тема VS Code.

Вынесена из основного кода для удобства настройки и замены.
"""

STYLESHEET = """
QMainWindow, QDialog {
    background-color: #1e1e1e;
}
QWidget {
    color: #d4d4d4;
    font-family: "Segoe UI", "Helvetica Neue", sans-serif;
}
QTextEdit {
    background-color: #151515;
    border: 1px solid #3c3c3c;
    color: #d4d4d4;
    border-radius: 6px;
    padding: 8px;
    font-size: 13px;
    font-family: "Consolas", "Courier New", monospace;
}
QTextEdit:disabled, QTextEdit[readOnly="true"] {
    background-color: #121212;
    color: #aaaaaa;
}
QPushButton {
    background-color: #007acc;
    color: white;
    border: none;
    padding: 6px 14px;
    border-radius: 6px;
    font-weight: bold;
    font-size: 12px;
}
QPushButton:hover { background-color: #005f9e; }
QPushButton:disabled { background-color: #333333; color: #666666; }

QPushButton#btn_danger { background-color: #c0392b; }
QPushButton#btn_danger:hover { background-color: #e74c3c; }

QPushButton#btn_success { background-color: #27ae60; }
QPushButton#btn_success:hover { background-color: #2ecc71; }
QPushButton#btn_success:disabled { background-color: #1e4d2e; color: #888888; }

QPushButton#btn_warning { background-color: #d35400; }
QPushButton#btn_warning:hover { background-color: #e67e22; }

QPushButton#btn_purple { background-color: #8e44ad; }
QPushButton#btn_purple:hover { background-color: #9b59b6; }

QPushButton#btn_copy { background-color: #34495e; }
QPushButton#btn_copy:hover { background-color: #2c3e50; }

QPushButton#btn_edit { background-color: #2980b9; }
QPushButton#btn_edit:hover { background-color: #2471a3; }

QPushButton#btn_workspace {
    background-color: #252526;
    border: 1px solid #3c3c3c;
    text-align: left;
    padding-left: 10px;
}
QPushButton#btn_workspace:hover {
    background-color: #2d2d30;
    border: 1px solid #007acc;
}

QProgressBar {
    border: none;
    border-radius: 3px;
    text-align: center;
    background-color: #333333;
    color: transparent;
}
QProgressBar::chunk { background-color: #007acc; border-radius: 3px; }

QScrollArea { border: none; background-color: transparent; }
QWidget#scroll_content { background-color: transparent; }

QComboBox {
    background-color: #252526;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    padding: 4px 8px;
    color: #d4d4d4;
}
QComboBox::drop-down { border: none; }

QWidget#sidebar { background-color: #252526; }

QFrame#card {
    background-color: #252526;
    border: 1px solid #3c3c3c;
    border-radius: 10px;
}
QFrame#card_success { border: 1px solid #27ae60; }
QFrame#card_error { border: 1px solid #c0392b; }
QFrame#card_info { border: 1px solid #3498db; }

QLabel#accent_title { color: #007acc; font-size: 16px; font-weight: bold; letter-spacing: 1px; }
QLabel#status_warning { color: #f39c12; font-weight: bold; font-size: 12px; }
QLabel#status_success { color: #27ae60; font-weight: bold; font-size: 12px; }
QLabel#status_error { color: #c0392b; font-weight: bold; font-size: 12px; }

/* СКРОЛЛБАРЫ */
QScrollBar:vertical { background-color: #1e1e1e; width: 14px; margin: 0px; }
QScrollBar::handle:vertical { background-color: #424242; min-height: 30px; border-radius: 7px; margin: 2px; }
QScrollBar::handle:vertical:hover { background-color: #4f4f4f; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background-color: transparent; }

QScrollBar:horizontal { background-color: #1e1e1e; height: 14px; margin: 0px; }
QScrollBar::handle:horizontal { background-color: #424242; min-width: 30px; border-radius: 7px; margin: 2px; }
QScrollBar::handle:horizontal:hover { background-color: #4f4f4f; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background-color: transparent; }
"""
