"""Smoke tests for responsive main window layout."""

import sys
import unittest

from PyQt6.QtWidgets import QApplication, QStackedWidget, QScrollArea

from ai_patcher_pro.gui.main_window import AIPatcherPro


class TestMainWindowResponsiveLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_main_window_uses_stacked_content_area(self):
        window = AIPatcherPro()
        self.assertTrue(hasattr(window, "content_stack"))
        self.assertIsInstance(window.content_stack, QStackedWidget)
        self.assertEqual(window.content_stack.count(), 2)

    def test_switching_tabs_does_not_change_stack_count(self):
        window = AIPatcherPro()
        count_before = window.content_stack.count()
        window._switch_tab("scanner")
        self.assertEqual(window.content_stack.currentWidget(), window.scanner_tab)
        window._switch_tab("patch")
        self.assertEqual(window.content_stack.currentWidget(), window.patch_view)
        self.assertEqual(window.content_stack.count(), count_before)

    def test_sidebar_is_scrollable(self):
        window = AIPatcherPro()
        scroll_areas = window.findChildren(QScrollArea, "sidebar_scroll")
        self.assertEqual(len(scroll_areas), 1)
        self.assertTrue(scroll_areas[0].widgetResizable())


if __name__ == "__main__":
    unittest.main()



class TestMainWindowSimplifiedSidebar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_advanced_tools_are_collapsed_by_default(self):
        window = AIPatcherPro()
        self.assertTrue(hasattr(window, "advanced_tools_frame"))
        self.assertFalse(window.advanced_tools_frame.isVisible())

    def test_advanced_tools_toggle(self):
        window = AIPatcherPro()
        # У невидимого top-level окна Qt возвращает False для child.isVisible(),
        # даже если child.setVisible(True). Поэтому проверяем hidden-state.
        self.assertTrue(window.advanced_tools_frame.isHidden())
        window._toggle_advanced_tools()
        self.assertFalse(window.advanced_tools_frame.isHidden())
        self.assertIn("▲", window.btn_more_tools.text())
        window._toggle_advanced_tools()
        self.assertTrue(window.advanced_tools_frame.isHidden())
        self.assertIn("▼", window.btn_more_tools.text())
