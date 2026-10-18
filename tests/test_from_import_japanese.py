"""Conformance tests for postposed-alias from-import syntax."""
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


def evaluate(source: str):
    namespace = {}
    exec(compile(transpile(source), "select.jpy", "exec"), namespace)
    return namespace


class SelectionImportTests(unittest.TestCase):
    def test_simple_import_exact(self):
        self.assertEqual(transpile("math から sqrt を 読み込む\n"), "from math import sqrt\n")

    def test_alias_variants_exact(self):
        for marker in ("として", "と名付ける"):
            with self.subTest(marker=marker):
                source = f"math から sqrt を 読み込む 平方根 {marker}\n"
                self.assertEqual(transpile(source), "from math import sqrt as 平方根\n")

    def test_loaded_objects_match_python(self):
        for marker in ("として", "と名付ける"):
            with self.subTest(marker=marker):
                source = f"math から sqrt を 読み込む 平方根 {marker}\nresult = 平方根(9)\n"
                result = evaluate(source)
                self.assertEqual(result["result"], 3.0)
                self.assertEqual(result["平方根"].__name__, "sqrt")

    def test_dotted_modules_and_unicode_names(self):
        source = (
            "collections.abc から Iterable を 読み込む 繰り返せる と名付ける\n"
            "result = isinstance([], 繰り返せる)\n"
        )
        self.assertEqual(evaluate(source)["result"], True)
        self.assertIn("from collections.abc import Iterable as 繰り返せる", transpile(source))

    def test_trailing_comment_and_line_count(self):
        source = (
            "# math から sqrt を 読み込む 別名 として\n"
            "math から sqrt を 読み込む 平方根 として  # comment retained\n"
            "print(平方根(16))\n"
        )
        converted = transpile(source)
        self.assertTrue(converted.startswith("# math から sqrt を 読み込む"))
        self.assertIn("from math import sqrt as 平方根  # comment retained", converted)
        self.assertEqual(source.count("\n"), converted.count("\n"))

    def test_existing_python_import_statements_are_unchanged(self):
        source = (
            "from math import sqrt as sq\n"
            "import math\n"
            "読み込む sys として system\n"
            "print(sq(16), math.pi, system.version_info.major)\n"
        )
        transformed = transpile(source)
        self.assertIn("from math import sqrt as sq\n", transformed)
        self.assertIn("import math\n", transformed)
        self.assertIn("import sys as system\n", transformed)
        self.assertEqual(transpile(transformed), transformed)

    def test_alias_marker_is_not_global_keyword(self):
        source = (
            "として = 'one'\n"
            "と名付ける = 'two'\n"
            "読み込む = lambda x: x\n"
            "print(として, と名付ける)\n"
            "読み込む('test')\n"
            "obj.から = 1\n"
        )
        self.assertEqual(transpile(source), source)

    def test_invalid_alias_order_and_duplicate_markers(self):
        cases = (
            "math から sqrt を 読み込む 平方根 として と名付ける\n",
            "math から sqrt を 読み込む 平方根 として として\n",
            "math から sqrt を 読み込む として\n",
            "math から sqrt を 読み込む 平方根 as\n",
            "math から sqrt を 読み込む 平方根 と 名付ける\n",
            "math から sqrt と名付ける 平方根 を読み込む\n",
        )
        for case in cases:
            with self.subTest(case=case):
                with self.assertRaises(SyntaxError):
                    compile(transpile(case), "bad.jpy", "exec")

    def test_multiple_and_relative_imports_remain_python_only(self):
        source = (
            "from math import sqrt, sin\n"
            "from .subpackage import symbol\n"
        )
        self.assertEqual(transpile(source), source)
        for bad in (
            "math から sqrt, sin を 読み込む\n",
            ".math から sqrt を 読み込む\n",
            "math から * を 読み込む\n",
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(SyntaxError):
                    compile(transpile(bad), "bad.jpy", "exec")

    def test_missing_module_import_target_is_rejected(self):
        for bad in (
            "から sqrt を 読み込む\n",
            "math から を 読み込む\n",
            "math から sqrt を 読み込む 平方根\n",
            "math から sqrt を 読み込む 平方根 と名付ける として\n",
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(SyntaxError):
                    compile(transpile(bad), "bad.jpy", "exec")

    def test_same_module_can_import_different_names(self):
        source = (
            "math から sqrt を 読み込む 平方根 として\n"
            "math から cos を 読み込む 余弦 と名付ける\n"
            "result = (平方根(9), 余弦(0))\n"
        )
        self.assertEqual(evaluate(source)["result"], (3.0, 1.0))

    def test_run_and_compile_output_semantics_are_separate(self):
        source = (
            "math から sqrt を 読み込む 平方根 と名付ける\n"
            "print(平方根(9))\n"
        )
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            src = root / "main.jpy"
            src.write_text(source, encoding="utf-8")
            stdio = io.StringIO()
            with contextlib.redirect_stdout(stdio):
                run_file(src)
            self.assertEqual(stdio.getvalue(), "3.0\n")
            self.assertEqual(sorted(x.name for x in root.iterdir()), ["main.jpy"])
            output = root / "main.py"
            silence = io.StringIO()
            with contextlib.redirect_stdout(silence):
                compile_file(src, output)
            self.assertEqual(silence.getvalue(), "")
            result = subprocess.run([sys.executable, "-I", str(output)],
                                    capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout, stdio.getvalue())
            self.assertNotIn("japanese_python", output.read_text("utf-8"))


if __name__ == "__main__":
    unittest.main()
