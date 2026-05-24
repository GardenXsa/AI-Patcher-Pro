"""Smoke tests for ScannerTab workspace integration."""

import sys
import tempfile
import unittest

from PyQt6.QtWidgets import QApplication

from ai_patcher_pro.gui.scanner_tab import ScannerTab


class TestScannerTabWorkspace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_set_workspace_updates_scan_path_and_enables_scan(self):
        tab = ScannerTab()
        workspace = tempfile.mkdtemp(prefix="scanner_tab_workspace_")

        tab.set_workspace(workspace)

        self.assertEqual(tab._scan_path, workspace)
        self.assertTrue(tab.btn_scan.isEnabled())
        self.assertIn(workspace, tab.lbl_path.text())

    def test_set_workspace_empty_disables_scan(self):
        tab = ScannerTab()
        tab.set_workspace("")

        self.assertEqual(tab._scan_path, "")
        self.assertFalse(tab.btn_scan.isEnabled())


if __name__ == "__main__":
    unittest.main()
