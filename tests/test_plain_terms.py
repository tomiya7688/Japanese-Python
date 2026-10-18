"""Plain-Japanese canonical spellings must preserve native Python meaning."""
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


def evaluate(source: str, *, filename: str = "plain.jpy") -> dict:
    namespace = {}
    exec(compile(transpile(source, filename=filename), filename, "exec"), namespace)
    return namespace


class PlainJapaneseTermsTests(unittest.TestCase):
    def test_canonical_exception_translation(self):
        source = (
            "試す:\n"
            "    例外を起こす ValueError('bad')\n"
            "例外処理 ValueError として error:\n"
            "    result = str(error)\n"
            "最後に:\n"
            "    finished = True\n"
        )
        expected = (
            "try:\n"
            "    raise ValueError('bad')\n"
            "except ValueError as error:\n"
            "    result = str(error)\n"
            "finally:\n"
            "    finished = True\n"
        )
        self.assertEqual(transpile(source), expected)
        scope = evaluate(source)
        self.assertEqual(scope["result"], "bad")
        self.assertTrue(scope["finished"])
        self.assertNotIn("error", scope)

    def test_plain_exception_with_alias_spellings(self):
        for word in ("として", "と名付ける", "as"):
            with self.subTest(word=word):
                source = (
                    "試す:\n"
                    "    例外を起こす LookupError('problem')\n"
                    f"例外処理 LookupError {word} cause:\n"
                    "    found = str(cause)\n"
                )
                self.assertEqual(evaluate(source)["found"], "problem")
                self.assertIn("except LookupError as cause:", transpile(source))

    def test_exception_handling_bare_except_and_else(self):
        caught = evaluate(
            "試す:\n"
            "    例外を起こす RuntimeError('x')\n"
            "例外処理:\n"
            "    outcome = 'caught'\n"
        )
        self.assertEqual(caught["outcome"], "caught")
        success = evaluate(
            "試す:\n"
            "    outcome = 'try'\n"
            "例外処理 ValueError:\n"
            "    outcome = 'except'\n"
            "それ以外:\n"
            "    outcome = 'else'\n"
            "最後に:\n"
            "    completed = True\n"
        )
        self.assertEqual(success["outcome"], "else")
        self.assertTrue(success["completed"])

    def test_exception_chain_and_reraise(self):
        code = (
            "試す:\n"
            "    試す:\n"
            "        例外を起こす ValueError('inner')\n"
            "    例外処理 ValueError と名付ける original:\n"
            "        例外を起こす RuntimeError('outer') from original\n"
            "例外処理 RuntimeError として problem:\n"
            "    result = (str(problem), str(problem.__cause__))\n"
        )
        self.assertEqual(evaluate(code)["result"], ("outer", "inner"))
        with self.assertRaisesRegex(ValueError, "again"):
            evaluate("試す:\n    例外を起こす ValueError('again')\n例外処理 ValueError:\n    例外を起こす\n")
        with self.assertRaises(RuntimeError):
            evaluate(
                "試す:\n"
                "    例外を起こす ValueError('inner')\n"
                "例外処理 ValueError:\n"
                "    例外を起こす RuntimeError('outer') from None\n"
            )

    def test_previous_exception_words_remain_compatible(self):
        old = "試す:\n    投げる ValueError('x')\n捕まえる ValueError as error:\n    result = str(error)\n最後に:\n    done = True\n"
        new = "試す:\n    例外を起こす ValueError('x')\n例外処理 ValueError as error:\n    result = str(error)\n最後に:\n    done = True\n"
        self.assertEqual(transpile(old), transpile(new))
        self.assertEqual(evaluate(old)["result"], evaluate(new)["result"])

    def test_nonexistent_jargon_is_not_automatically_interpreted(self):
        for source in (
            "試行:\n    pass\n",
            "例外を送出 ValueError('x')\n",
            "試す:\n    pass\n最終処理:\n    pass\n",
        ):
            with self.subTest(source=source):
                with self.assertRaises(SyntaxError):
                    compile(transpile(source), "not-a-keyword.jpy", "exec")

    def test_new_return_spelling_and_backward_compatibility(self):
        for head, postfix in (("返す", "を返す"), ("戻す", "を戻す")):
            with self.subTest(head=head, postfix=postfix):
                source = (
                    f"関数 first(a, b):\n    {head} a + b\n"
                    f"関数 second(a, b):\n    a + b {postfix}\n"
                    f"関数 empty():\n    {head}\n"
                    "result = (first(2, 3), second(2, 3), empty())\n"
                )
                self.assertEqual(evaluate(source)["result"], (5, 5, None))
        self.assertEqual(transpile("関数 f():\n    返す (1, 2)\n"), "def f():\n    return (1, 2)\n")

    def test_new_return_postfix_tuple_and_evaluation_once(self):
        source = (
            "calls = []\n"
            "関数 value():\n"
            "    calls.append(1)\n"
            "    返す 7\n"
            "関数 pair():\n"
            "    value(), 9 を返す\n"
            "result = pair()\n"
        )
        scope = evaluate(source)
        self.assertEqual(scope["result"], (7, 9))
        self.assertEqual(scope["calls"], [1])

    def test_return_hybrid_forms_rejected(self):
        for first, second in (("返す", "を返す"), ("返す", "を戻す"), ("戻す", "を返す")):
            with self.subTest(first=first, second=second):
                with self.assertRaises(SyntaxError):
                    transpile(f"関数 f():\n    {first} 1 {second}\n")

    def test_new_names_as_identifiers_and_literals(self):
        source = (
            "返す = lambda x: x + 1\n"
            "例外を起こす = lambda x: x\n"
            "例外処理 = 'name'\n"
            "返す(3)\n"
            "例外を起こす(4)\n"
            "obj.例外を起こす(5)\n"
            "x = '例外を起こす 返す 例外処理'\n"
            "# 例外を起こす ValueError\n"
        )
        self.assertEqual(transpile(source), source)
        self.assertEqual(transpile("関数 f():\n    返す (3)\n"), "def f():\n    return (3)\n")

    def test_english_python_is_unmodified(self):
        source = (
            "def f(x):\n"
            "    try:\n"
            "        if x:\n"
            "            raise ValueError('bad')\n"
            "    except ValueError as e:\n"
            "        return str(e)\n"
            "    finally:\n"
            "        pass\n"
            "    return None\n"
        )
        self.assertEqual(transpile(source), source)

    def test_source_line_count_and_error_location(self):
        source = (
            "# 例外を起こす is not a command here\n"
            "試す:\n"
            "    例外を起こす ValueError('x')\n"
            "例外処理 ValueError と名付ける issue:\n"
            "    result = str(issue)\n"
        )
        compiled = transpile(source, filename="src.jpy")
        self.assertEqual(source.count("\n"), compiled.count("\n"))
        self.assertEqual(evaluate(source)["result"], "x")
        with self.assertRaises(SyntaxError) as caught:
            transpile(
                "試す:\n"
                "    pass\n"
                "例外処理 ValueError として と名付ける e:\n"
                "    pass\n", filename="wrong.jpy"
            )
        self.assertEqual(caught.exception.lineno, 3)
        self.assertEqual(caught.exception.filename, "wrong.jpy")

    def test_compile_and_run_match_without_leaking_generated_python(self):
        source = (
            "関数 f():\n"
            "    試す:\n"
            "        例外を起こす ValueError('bad')\n"
            "    例外処理 ValueError と名付ける error:\n"
            "        print(str(error))\n"
            "        返す 'ok'\n"
            "print(f())\n"
        )
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            jpy = root / "main.jpy"
            jpy.write_text(source, encoding="utf-8")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                run_file(jpy)
            self.assertEqual(stdout.getvalue(), "bad\nok\n")
            self.assertEqual(sorted(path.name for path in root.iterdir()), ["main.jpy"])
            py = root / "main.py"
            compile_file(jpy, py)
            completed = subprocess.run(
                [sys.executable, "-I", str(py)], capture_output=True,
                text=True, check=True
            )
            self.assertEqual(completed.stdout, stdout.getvalue())
            self.assertNotIn("japanese_python", py.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
