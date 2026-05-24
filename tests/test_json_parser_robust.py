"""Тесты устойчивого парсинга кривого JSON от LLM."""

import unittest

from ai_patcher_pro.core.json_parser import extract_all_json


class TestRobustJsonParsing(unittest.TestCase):
    def test_fenced_block_with_chatgpt_attrs_and_tildes(self):
        raw = '''Вот патч:
~~~json id="abc123"
{
  "patch_name": "attrs",
  "operations": [
    {"path": "a.py", "action": "append", "content": "x"}
  ]
}
~~~
'''
        result = extract_all_json(raw)
        self.assertEqual(result["patch_name"], "attrs")
        self.assertEqual(result["operations"][0]["path"], "a.py")

    def test_comments_and_trailing_commas(self):
        raw = '''
{
  // comment
  "operations": [
    {
      "path": "a.py", # another comment
      "action": "replace",
      "search": "old",
      "content": "new",
    },
  ],
}
'''
        result = extract_all_json(raw)
        self.assertEqual(len(result["operations"]), 1)
        self.assertEqual(result["operations"][0]["content"], "new")

    def test_python_style_dict_single_quotes(self):
        raw = """
Here:
{'patch_name': 'py dict', 'operations': [{'path': 'a.py', 'action': 'append', 'content': 'x'}], 'commands': [{'cmd': 'py -m pytest', 'run': 'after_apply'}]}
Done.
"""
        result = extract_all_json(raw)
        self.assertEqual(result["patch_name"], "py dict")
        self.assertEqual(result["operations"][0]["action"], "append")
        self.assertEqual(result["commands"][0]["cmd"], "py -m pytest")

    def test_python_literals_inside_json_like_object(self):
        raw = '''
{
  "operations": [
    {"path": "a.py", "action": "append", "content": "x", "enabled": True, "meta": None}
  ]
}
'''
        result = extract_all_json(raw)
        self.assertTrue(result["operations"][0]["enabled"])
        self.assertIsNone(result["operations"][0]["meta"])

    def test_real_newlines_inside_json_string_are_escaped(self):
        raw = '''
{
  "operations": [
    {
      "path": "a.py",
      "action": "replace",
      "search": "line1
line2",
      "content": "line1 fixed
line2 fixed"
    }
  ]
}
'''
        result = extract_all_json(raw)
        self.assertEqual(result["operations"][0]["search"], "line1\nline2")
        self.assertIn("line2 fixed", result["operations"][0]["content"])

    def test_command_only_patch_with_alias(self):
        raw = '''
{
  "cmds": [
    {"command": "py -m compileall ai_patcher_pro", "phase": "after_analysis", "desc": "syntax"},
  ],
}
'''
        result = extract_all_json(raw)
        self.assertEqual(result["operations"], [])
        self.assertEqual(len(result["commands"]), 1)
        self.assertEqual(result["commands"][0]["run"], "after_analysis")

    def test_unquoted_object_keys_are_repaired(self):
        raw = '''
{
  operations: [
    {path: "a.py", action: "append", content: "x"}
  ]
}
'''
        result = extract_all_json(raw)
        self.assertEqual(result["operations"][0]["path"], "a.py")


if __name__ == "__main__":
    unittest.main()
