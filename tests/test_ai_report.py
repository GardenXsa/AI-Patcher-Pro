"""Tests for AI-friendly patch reports."""

import unittest

from ai_patcher_pro.core.ai_report import build_ai_patch_report


class TestAIReport(unittest.TestCase):
    def test_report_includes_success_and_error_details(self):
        report = build_ai_patch_report(
            patch_name="Test patch",
            workspace="C:/tmp/project",
            current_phase="analysis",
            patch_written=False,
            raw_operations=[{"id": 0, "op": {"path": "a.py"}}],
            processed_operations=[
                {
                    "id": 0,
                    "status": "error",
                    "error": "Текст не найден",
                    "search_method": "Не найдено",
                    "op": {
                        "path": "a.py",
                        "action": "replace",
                        "search": "old",
                        "content": "new",
                    },
                    "diff": [],
                    "suggestions": [(0.87, "candidate")],
                }
            ],
            command_results=[
                {
                    "cmd": "py -m pytest",
                    "description": "tests",
                    "status": "error",
                    "returncode": 1,
                    "stdout": "collected 1 item",
                    "stderr": "FAILED",
                    "warnings": [],
                }
            ],
        )

        self.assertIn("Test patch", report)
        self.assertIn("Operation errors: 1", report)
        self.assertIn("Command errors: 1", report)
        self.assertIn("Текст не найден", report)
        self.assertIn("py -m pytest", report)
        self.assertIn("FAILED", report)
        self.assertIn("candidate", report)

    def test_report_for_successful_patch_has_next_step_request(self):
        report = build_ai_patch_report(
            patch_name="OK patch",
            workspace="/tmp/project",
            current_phase="done",
            patch_written=True,
            processed_operations=[
                {
                    "id": 0,
                    "status": "applied",
                    "error": "",
                    "search_method": "Точное совпадение",
                    "op": {"path": "main.py", "action": "append"},
                    "diff": ["+print('ok')"],
                    "suggestions": [],
                }
            ],
            command_results=[
                {"cmd": "py -m pytest", "status": "success", "returncode": 0}
            ],
        )

        self.assertIn("Patch written to disk: yes", report)
        self.assertIn("Applied: 1", report)
        self.assertIn("Commands OK: 1", report)
        self.assertIn("Патч применён", report)


if __name__ == "__main__":
    unittest.main()
