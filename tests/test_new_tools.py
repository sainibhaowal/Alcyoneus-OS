# Copyright 2026 Alcyoneus Authors

import unittest
import tempfile
from pathlib import Path

from alcyoneus.prebuilt.tools import (
    file_search,
    FileSearchTool,
    code_interpreter,
    CodeInterpreterTool,
    computer_use,
    ComputerTool,
)


class TestNewTools(unittest.TestCase):

    def test_file_search_tool(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "sample.py"
            test_file.write_text("def hello_world():\n    print('Alcyoneus OS RAG Search')\n", encoding="utf-8")

            import json
            res = json.loads(file_search(query="Alcyoneus OS", search_path=tmpdir))
            self.assertEqual(res["total_matches"], 1)
            self.assertIn("Alcyoneus OS RAG Search", res["results"][0]["snippet"])

    def test_code_interpreter_tool(self):
        code = "a = 10\nb = 20\nprint(f'SUM={a+b}')\n"
        res = code_interpreter(code=code)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["stdout"], "SUM=30")

    def test_computer_use_tool_interface(self):
        tool_obj = ComputerTool()
        # Verify fallback error handling when pyautogui GUI display is not active
        res = tool_obj(action="mouse_move", coordinate=(100, 100))
        self.assertIn("status", res)


if __name__ == "__main__":
    unittest.main()
