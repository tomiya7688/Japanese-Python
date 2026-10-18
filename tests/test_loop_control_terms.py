"""Conformance tests for canonical break / continue spellings.

The legacy names, original Python keywords and compile/run contract remain intact.
"""
from __future__ import annotations

import asyncio
import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from japanese_python import transpile
from japanese_python.compiler import compile_file
from japanese_python.runner import run_file


def execute(source: str) -> dict:
    namespace = {"__name__": "__jpy_test__"}
    exec(compile(transpile(source, filename="control.jpy"), "control.jpy", "exec"), namespace)
    return namespace


class LoopControlTermTests(unittest.TestCase):
    def test_keywords_translate_to_break_and_continue(self):
        src = "for i in range(2):\n    繰り返しを続ける\n    繰り返しをやめる\n"
        self.assertEqual(transpile(src), "for i in range(2):\n    continue\n    break\n")
        self.assertEqual(transpile(transpile(src)), transpile(src))

    def test_expected_example_output(self):
        src = (
            "繰り返し i が 0 から 10 まで:\n"
            "    もし i == 3 ならば:\n"
            "        繰り返しを続ける\n"
            "    もし i == 7 ならば:\n"
            "        繰り返しをやめる\n"
            "    print(i)\n"
        )
        out=io.StringIO()
        with contextlib.redirect_stdout(out):
            execute(src)
        self.assertEqual(out.getvalue(), "0\n1\n2\n4\n5\n6\n")

    def test_continue_in_while_skips_remainder_but_tests_again(self):
        src = (
            "i = 0\nvalues = []\n"
            "i < 5 の間:\n"
            "    i += 1\n"
            "    もし i % 2 == 0 ならば:\n"
            "        繰り返しを続ける\n"
            "    values.append(i)\n"
        )
        namespace = execute(src)
        self.assertEqual(namespace["values"], [1, 3, 5])
        self.assertEqual(namespace["i"], 5)

    def test_break_affects_only_innermost_loop(self):
        src = (
            "pairs = []\n"
            "繰り返し i が 0 から 3 まで:\n"
            "    繰り返し j が 0 から 4 まで:\n"
            "        もし j == 2 ならば:\n"
            "            繰り返しをやめる\n"
            "        pairs.append((i, j))\n"
        )
        self.assertEqual(execute(src)["pairs"],
                         [(0, 0), (0, 1), (1, 0), (1, 1), (2, 0), (2, 1)])

    def test_try_finally_inside_loop_does_not_change_loop_target(self):
        src = (
            "result = []\n"
            "for i in range(4):\n"
            "    試す:\n"
            "        もし i == 1 ならば:\n"
            "            繰り返しを続ける\n"
            "        もし i == 2 ならば:\n"
            "            繰り返しをやめる\n"
            "        result.append(i)\n"
            "    最後に:\n"
            "        result.append(('final', i))\n"
        )
        self.assertEqual(execute(src)["result"], [0, ("final", 0), ("final", 1), ("final", 2)])

    def test_break_prevents_loop_else_but_continue_does_not(self):
        src = (
            "events = []\n"
            "繰り返し i が 0 から 3 まで:\n"
            "    繰り返しを続ける\n"
            "それ以外:\n"
            "    events.append('normal')\n"
            "繰り返し j が 0 から 3 まで:\n"
            "    繰り返しをやめる\n"
            "それ以外:\n"
            "    events.append('not reached')\n"
        )
        self.assertEqual(execute(src)["events"], ["normal"])

    def test_original_and_previous_japanese_spelling_are_equivalent(self):
        for spelling, translated in (("抜ける", "break"), ("続ける", "continue"),
                                     ("繰り返しをやめる", "break"),
                                     ("繰り返しを続ける", "continue")):
            with self.subTest(spelling=spelling):
                self.assertEqual(transpile(f"while True:\n    {spelling}\n"),
                                 f"while True:\n    {translated}\n")
        old = "for i in range(2):\n    続ける\n    抜ける\n"
        new = "for i in range(2):\n    繰り返しを続ける\n    繰り返しをやめる\n"
        self.assertEqual(transpile(old), transpile(new))

    def test_loop_control_outside_a_loop_is_invalid(self):
        for spelling in ("繰り返しをやめる", "繰り返しを続ける"):
            for template in ("{}\n", "もし True ならば:\n    {}\n",
                             "試す:\n    {}\n例外処理:\n    pass\n",
                             "for i in range(1):\n    def inside():\n        {}\n"):
                with self.subTest(spelling=spelling, template=template):
                    text = template.format(spelling)
                    with self.assertRaises(SyntaxError):
                        compile(transpile(text), "illegal.jpy", "exec")

    def test_words_as_python_identifiers_outside_keyword_positions(self):
        source = (
            "繰り返しをやめる = lambda x: x\n"
            "繰り返しを続ける: int = 4\n"
            "繰り返しをやめる(1)\n"
            "obj.繰り返しを続ける(2)\n"
            "# 繰り返しをやめる\n"
            "message = '繰り返しを続ける'\n"
        )
        self.assertEqual(transpile(source), source)

    def test_async_for_accepts_same_break_and_continue(self):
        source = (
            "import asyncio\n"
            "async def get_values():\n"
            "    for i in range(5):\n"
            "        yield i\n"
            "async def loop():\n"
            "    result = []\n"
            "    async for i in get_values():\n"
            "        もし i == 1 ならば:\n"
            "            繰り返しを続ける\n"
            "        もし i == 3 ならば:\n"
            "            繰り返しをやめる\n"
            "        result.append(i)\n"
            "    返す result\n"
            "result = asyncio.run(loop())\n"
        )
        self.assertEqual(execute(source)["result"], [0, 2])

    def test_jpy_run_and_compile_use_same_control_words(self):
        source = (
            "繰り返し i が 0 から 8 まで:\n"
            "    もし i == 2 ならば:\n"
            "        繰り返しを続ける\n"
            "    もし i == 5 ならば:\n"
            "        繰り返しをやめる\n"
            "    print(i)\n"
        )
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            jpy = root / "main.jpy"
            jpy.write_text(source, encoding="utf-8")
            direct = io.StringIO()
            with contextlib.redirect_stdout(direct):
                run_file(jpy)
            self.assertEqual(direct.getvalue(), "0\n1\n3\n4\n")
            self.assertEqual(sorted(x.name for x in root.iterdir()), ["main.jpy"])
            py = root / "main.py"
            silent = io.StringIO()
            with contextlib.redirect_stdout(silent):
                compile_file(jpy, py)
            self.assertEqual(silent.getvalue(), "")
            completed = subprocess.run(
                [sys.executable, "-I", str(py)], check=True, text=True,
                capture_output=True
            )
            self.assertEqual(completed.stdout, direct.getvalue())
            self.assertNotIn("japanese_python", py.read_text("utf-8"))

if __name__ == "__main__":
    unittest.main()
