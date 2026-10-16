"""Keep compile/run semantics separate, even when packaging is added later."""

from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from japanese_python.compiler import compile_file
from japanese_python.runner import run_file


class ToolContractTests(unittest.TestCase):
    def test_compile_only_writes_plain_python_without_executing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "program.jpy"
            marker = root / "executed.txt"
            source.write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('called')\n", encoding="utf-8")
            output = root / "dist" / "program.py"
            result = compile_file(source, output)
            self.assertEqual(result, output)
            self.assertFalse(marker.exists(), "compile must not execute user code")
            self.assertNotIn("japanese_python", output.read_text(encoding="utf-8"))
            subprocess.run([sys.executable, "-I", str(output)], check=True)
            self.assertTrue(marker.exists(), ".py must be independently executable without JPy")

    def test_run_never_generates_python_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "program.jpy"
            source.write_text("関数 f():\n    42 を戻す\nprint(f())\n", encoding="utf-8")
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                run_file(source)
            self.assertEqual(stream.getvalue(), "42\n")
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["program.jpy"])

    def test_run_argv_file_and_local_import(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "main.jpy"
            (root / "helper.py").write_text("NAME = 'helper'\n", encoding="utf-8")
            source.write_text(
                "import sys\nimport helper\n"
                "assert __name__ == '__main__'\n"
                "assert __file__.endswith('main.jpy')\n"
                "assert __package__ is None\n"
                "print(sys.argv[1:], helper.NAME)\n",
                encoding="utf-8",
            )
            stream = io.StringIO()
            old_argv = sys.argv
            old_path = sys.path[:]
            with contextlib.redirect_stdout(stream):
                run_file(source, ["hello", "world"])
            self.assertIn("['hello', 'world'] helper", stream.getvalue())
            self.assertIs(old_argv, sys.argv)
            self.assertEqual(old_path, sys.path)
            # Avoid leaking the imported test helper into unrelated tests.
            sys.modules.pop("helper", None)

    def test_no_overwrite_without_force(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "main.jpy"
            target = root / "main.py"
            source.write_text("x = 3\n", encoding="utf-8")
            target.write_text("sentinel", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                compile_file(source, target)
            self.assertEqual(target.read_text(encoding="utf-8"), "sentinel")
            compile_file(source, target, force=True)
            self.assertEqual(target.read_text(encoding="utf-8"), "x = 3\n")

    def test_invalid_input_does_not_write_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "bad.jpy"
            target = root / "bad.py"
            source.write_text("もし :\n    何もしない\n", encoding="utf-8")
            with self.assertRaises(SyntaxError):
                compile_file(source, target)
            self.assertFalse(target.exists())

    def test_error_traceback_references_jpy_source(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "error.jpy"
            source.write_text("関数 broken():\n    1 / 0 を戻す\nbroken()\n", encoding="utf-8")
            import traceback
            try:
                run_file(source)
            except ZeroDivisionError as exc:
                formatted = "".join(traceback.format_exception(exc))
            else:
                self.fail("Expected ZeroDivisionError")
            # Code location belongs to the original .jpy, never temp .py.
            self.assertIn("error.jpy", formatted)


if __name__ == "__main__":
    unittest.main()
