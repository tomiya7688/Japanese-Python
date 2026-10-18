"""Conformance tests for Japanese structural pattern matching."""
from __future__ import annotations

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


def evaluate(source: str) -> dict:
    namespace = {}
    exec(compile(transpile(source, filename="match.jpy"), "match.jpy", "exec"), namespace)
    return namespace


class JapanesePatternMatchingTests(unittest.TestCase):
    def test_match_case_exact_python(self):
        source = (
            "値 に応じて:\n"
            "    0 の場合:\n"
            "        print('zero')\n"
            "    1 | 2 の場合:\n"
            "        print('one or two')\n"
            "    _ の場合:\n"
            "        print('other')\n"
        )
        expected = (
            "match 値:\n"
            "    case 0:\n"
            "        print('zero')\n"
            "    case 1 | 2:\n"
            "        print('one or two')\n"
            "    case _:\n"
            "        print('other')\n"
        )
        self.assertEqual(transpile(source), expected)
        self.assertEqual(transpile(expected), expected)

    def test_wildcard_literal_and_or(self):
        source = (
            "値 = 2\n"
            "値 に応じて:\n"
            "    0 の場合:\n"
            "        result = 'zero'\n"
            "    1 | 2 の場合:\n"
            "        result = 'low'\n"
            "    _ の場合:\n"
            "        result = 'other'\n"
        )
        self.assertEqual(evaluate(source)["result"], "low")

    def test_mapping_capture_and_guard_in_japanese(self):
        source = (
            "値 = {'名前': '葵', '年齢': 20}\n"
            "値 に応じて:\n"
            "    {'名前': 名前, '年齢': 年齢} の場合 もし 年齢 >= 18 ならば:\n"
            "        result = (名前, 年齢)\n"
            "    _ の場合:\n"
            "        result = 'no match'\n"
        )
        py = transpile(source)
        self.assertIn("case {'名前': 名前, '年齢': 年齢} if 年齢 >= 18:", py)
        self.assertEqual(evaluate(source)["result"], ("葵", 20))

    def test_sequence_star_pattern(self):
        source = (
            "値 = [10, 20, 30]\n"
            "値 に応じて:\n"
            "    [先頭, *残り] の場合:\n"
            "        result = (先頭, 残り)\n"
        )
        self.assertEqual(evaluate(source)["result"], (10, [20, 30]))

    def test_class_pattern_uses_python_semantics(self):
        source = (
            "from dataclasses import dataclass\n"
            "@dataclass\n"
            "class Point:\n"
            "    x: int\n"
            "    y: int\n"
            "point = Point(3, 8)\n"
            "point に応じて:\n"
            "    Point(x, y) の場合:\n"
            "        result = (x, y)\n"
        )
        self.assertEqual(evaluate(source)["result"], (3, 8))

    def test_python_if_guard_and_as_pattern_are_supported(self):
        source = (
            "値 = (5, 2)\n"
            "値 に応じて:\n"
            "    [x, y] as whole の場合 if x > y:\n"
            "        result = (x, y, whole)\n"
            "    _ の場合:\n"
            "        result = None\n"
        )
        self.assertEqual(evaluate(source)["result"], (5, 2, (5, 2)))
        self.assertIn("case [x, y] as whole if x > y:", transpile(source))

    def test_subject_evaluated_once_and_guard_order(self):
        source = (
            "events = []\n"
            "def f():\n"
            "    events.append('subject')\n"
            "    return [1, 2]\n"
            "f() に応じて:\n"
            "    [a, b] の場合 もし (events.append('guard') or a == 4) ならば:\n"
            "        events.append('first')\n"
            "    [a, b] の場合:\n"
            "        events.append('second')\n"
        )
        self.assertEqual(evaluate(source)["events"], ["subject", "guard", "second"])

    def test_mixed_original_english_match_and_japanese_case(self):
        source = (
            "match 3:\n"
            "    3 の場合:\n"
            "        first = True\n"
            "    case _:\n"
            "        first = False\n"
            "4 に応じて:\n"
            "    case 4:\n"
            "        second = True\n"
            "    _ の場合:\n"
            "        second = False\n"
        )
        obj = evaluate(source)
        self.assertTrue(obj["first"])
        self.assertTrue(obj["second"])
        self.assertIn("match 3:", transpile(source))
        self.assertIn("    case 4:", transpile(source))

    def test_nested_matches(self):
        source = (
            "値 = [[1, 2]]\n"
            "値 に応じて:\n"
            "    [inner] の場合:\n"
            "        inner に応じて:\n"
            "            [a, b] の場合:\n"
            "                result = a + b\n"
        )
        self.assertEqual(evaluate(source)["result"], 3)

    def test_multiline_patterns_subjects_and_source_lines(self):
        source = (
            "(\n"
            "    [1, 2]\n"
            ") に応じて:\n"
            "    [\n"
            "       x, y\n"
            "    ] の場合 もし x < y ならば:\n"
            "        result = x + y\n"
        )
        converted = transpile(source)
        self.assertEqual(source.count("\n"), converted.count("\n"))
        self.assertEqual(evaluate(source)["result"], 3)

    def test_comments_and_fstrings_unchanged(self):
        source = (
            "# 値 に応じて: and x の場合:\n"
            "text = f'に応じて の場合 {2 + 1}'\n"
            "text に応じて: # trailing comment\n"
            "    'に応じて の場合 3' の場合:\n"
            "        result = 'ok'\n"
            "    _ の場合:\n"
            "        result = 'other'\n"
        )
        converted = transpile(source)
        self.assertIn("f'に応じて の場合 {2 + 1}'", converted)
        self.assertIn("match text: # trailing comment", converted)
        self.assertEqual(evaluate(source)["result"], "ok")

    def test_original_python_match_case_is_untouched(self):
        source = (
            "match value:\n"
            "    case [x, y] if x > 0:\n"
            "        print(x, y)\n"
            "    case _:\n"
            "        pass\n"
        )
        self.assertEqual(transpile(source), source)

    def test_identifiers_not_mistaken_in_regular_python(self):
        source = (
            "の場合 = 3\n"
            "に応じて = 4\n"
            "obj.の場合 = 1\n"
            "print(の場合, に応じて)\n"
            "match の場合:\n"
            "    case に応じて:\n"
            "        pass\n"
        )
        self.assertEqual(transpile(source), source)

    def test_invalid_case_outside_match(self):
        for source in (
            "0 の場合:\n    pass\n",
            "[x, y] の場合 if x > 0:\n    pass\n",
        ):
            with self.subTest(source=source):
                with self.assertRaises(SyntaxError):
                    compile(transpile(source), "invalid.jpy", "exec")

    def test_invalid_markers_and_missing_guard(self):
        cases = (
            "value に 応じて:\n    0 の場合:\n        pass\n",
            "value に応じて:\n    0 の 場合:\n        pass\n",
            "value に応じて:\n    0 の場合 もし True:\n        pass\n",
            "value に応じて:\n    0 の場合 if:\n        pass\n",
            "value に応じて:\n    0 の場合 もし ならば:\n        pass\n",
            "value に応じて:\n    0 の場合 extra:\n        pass\n",
            "value に応じて:\n    0 の場合 の場合:\n        pass\n",
        )
        for source in cases:
            with self.subTest(source=source):
                with self.assertRaises(SyntaxError):
                    compile(transpile(source), "invalid.jpy", "exec")

    def test_jpy_error_reports_source_line(self):
        source = (
            "value に応じて:\n"
            "    0 の場合:\n"
            "        pass\n"
            "    1 の場合 もし True:\n"
            "        pass\n"
        )
        with self.assertRaises(SyntaxError) as error:
            transpile(source, filename="origin.jpy")
        self.assertEqual(error.exception.filename, "origin.jpy")
        self.assertEqual(error.exception.lineno, 4)

    def test_compile_run_contract_and_standalone_python(self):
        source = (
            "value = {'numbers': [1, 2]}\n"
            "value に応じて:\n"
            "    {'numbers': [a, b]} の場合 もし a < b ならば:\n"
            "        print(a + b)\n"
            "    _ の場合:\n"
            "        print('other')\n"
        )
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            jpy = root / "case.jpy"
            jpy.write_text(source, encoding="utf-8")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                run_file(jpy)
            self.assertEqual(stdout.getvalue(), "3\n")
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["case.jpy"])
            py = root / "case.py"
            silence = io.StringIO()
            with contextlib.redirect_stdout(silence):
                compile_file(jpy, py)
            self.assertEqual(silence.getvalue(), "")
            result = subprocess.run([sys.executable, "-I", str(py)], check=True,
                                    capture_output=True, text=True)
            self.assertEqual(result.stdout, stdout.getvalue())
            self.assertNotIn("japanese_python", py.read_text(encoding="utf-8"))

if __name__ == "__main__":
    unittest.main()
