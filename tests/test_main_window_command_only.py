"""UI regression tests for command-only patches."""

import sys
import unittest

from PyQt6.QtWidgets import QApplication

from ai_patcher_pro.gui.main_window import AIPatcherPro


class TestMainWindowCommandOnlyUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_command_only_ready_changes_main_button_text(self):
        window = AIPatcherPro()
        window.raw_operations = []
        window.commands_after_apply = [
            {"cmd": "py -m compileall ai_patcher_pro tests", "run": "after_apply"}
        ]

        window._check_ready_status()

        self.assertEqual(window.btn_apply.text(), "Выполнить команды")
        self.assertTrue(window.btn_apply.isEnabled())
        self.assertEqual(window.lbl_status.text(), "Готово к выполнению команд")

    def test_reset_main_action_button_restores_patch_mode(self):
        window = AIPatcherPro()
        window.btn_apply.setText("Выполнить команды")
        window.btn_apply.setEnabled(True)

        window._reset_main_action_button()

        self.assertEqual(window.btn_apply.text(), "ПРИМЕНИТЬ ПАТЧ")
        self.assertFalse(window.btn_apply.isEnabled())


if __name__ == "__main__":
    unittest.main()
