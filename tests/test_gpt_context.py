"""Тесты GPT context pack."""

import os
import tempfile
import unittest


from ai_patcher_pro.core.gpt_context import (
    CONTEXT_FILES,
    build_local_diff_text,
    ensure_context_gitignore,
    save_gpt_context_bundle,
)


class TestGPTContextPack(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="ai_patcher_gpt_ctx_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_ensure_context_gitignore_adds_files_once(self):
        gitignore_path = os.path.join(self.tmpdir, ".gitignore")
        with open(gitignore_path, "w", encoding="utf-8") as f:
            f.write("__pycache__/\n")

        ensure_context_gitignore(self.tmpdir)
        ensure_context_gitignore(self.tmpdir)

        with open(gitignore_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("__pycache__/", content)
        for name in CONTEXT_FILES:
            self.assertEqual(content.count(name), 1)

    def test_local_diff_handles_non_git_folder(self):
        text = build_local_diff_text(self.tmpdir)
        self.assertIn("# local_diff.txt", text)
        self.assertIn("Git status недоступен", text)

    def test_save_bundle_creates_expected_files_and_preserves_task(self):
        task_path = os.path.join(self.tmpdir, "GPT_TASK.md")
        with open(task_path, "w", encoding="utf-8") as f:
            f.write("do not overwrite")

        written = save_gpt_context_bundle(
            self.tmpdir,
            scan_context="FULL SCAN CONTENT\n",
        )

        for name in CONTEXT_FILES:
            self.assertIn(name, written)
            self.assertTrue(os.path.exists(os.path.join(self.tmpdir, name)))

        with open(os.path.join(self.tmpdir, "Project_scan.txt"), "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "FULL SCAN CONTENT\n")

        with open(task_path, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "do not overwrite")

        self.assertTrue(os.path.exists(os.path.join(self.tmpdir, ".gitignore")))


if __name__ == "__main__":
    unittest.main()
