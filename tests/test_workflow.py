"""Tests for workflow assistant helpers."""

import json
import os
import tempfile
import unittest

from ai_patcher_pro.core.workflow import (
    AI_PATCHER_PROFILE,
    find_applied_patch,
    get_check_commands,
    mark_patch_applied,
    patch_fingerprint,
    project_rule_warnings,
    save_project_profile,
    workflow_status_report,
)


class TestWorkflowHelpers(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="ai_patcher_workflow_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_patch_registry_marks_and_finds_patch(self):
        raw_ops = [{"id": 0, "op": {"path": "a.py", "action": "append", "content": "x"}}]
        fp = patch_fingerprint("p", raw_ops, [])
        mark_patch_applied(self.tmpdir, fp, "p", ["a.py"], "ok")
        found = find_applied_patch(self.tmpdir, fp)
        self.assertIsNotNone(found)
        self.assertEqual(found["patch_name"], "p")
        self.assertIn("a.py", found["files"])

    def test_save_profile_and_get_check_commands(self):
        save_project_profile(self.tmpdir, AI_PATCHER_PROFILE)
        commands = get_check_commands(self.tmpdir, "quick")
        self.assertTrue(commands)
        self.assertEqual(commands[0]["run"], "after_apply")
        self.assertIn("compileall", commands[0]["cmd"])

    def test_project_rule_warnings_for_meterea_required_docs(self):
        profile = {
            "name": "Test Meterea",
            "required_files_for_runtime_changes": ["docs/AI_PATCHER_WORKLOG.md"],
            "forbidden_patterns": ["HARDCODED"],
        }
        save_project_profile(self.tmpdir, profile)
        warnings = project_rule_warnings(
            self.tmpdir,
            [
                {
                    "id": 1,
                    "op": {
                        "path": "engine/a.cpp",
                        "action": "append",
                        "content": "// HARDCODED id",
                    },
                }
            ],
        )
        self.assertTrue(any("обязательные файлы" in w for w in warnings))
        self.assertTrue(any("HARDCODED" in w for w in warnings))

    def test_workflow_status_report_contains_recommendation(self):
        report = workflow_status_report(
            self.tmpdir,
            "patch",
            [],
            [],
            [],
            False,
        )
        self.assertIn("Workflow Assistant", report)
        self.assertIn("Main recommendation", report)


if __name__ == "__main__":
    unittest.main()
