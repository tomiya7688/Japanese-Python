"""Acceptance tests for the frozen v0.1 grammar decisions.

Existing test_transpiler.py and test_tools.py are retained unchanged.
"""
from __future__ import annotations

import ast
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


def evaluate(source: str, *, optimize: int = 0) -> dict:
    namespace = {}
    exec(compile(transpile(source), "case.jpy", "exec", optimize=optimize), namespace)
    return namespace


class GrammarDecisionTests(unittest.TestCase):
    def test_canonical_generic_for_and_legacy_alias(self):
        for head in ("繰り返し", "各"):
            with self.subTest(head=head):
                source = f"result = []\n{head} (k, v) を {{'a': 1, 'b': 2}}.items() から:\n    result.append((k, v))\n"
                self.assertEqual(evaluate(source)["result"], [('a', 1), ('b', 2)])

    def test_iterable_evaluated_once(self):
        source = "calls = []\ndef values():\n    calls.append(1)\n    return [3, 4]\n繰り返し x を values() から:\n    pass\n"
        self.assertEqual(evaluate(source)["calls"], [1])

    def test_range_step_exact_translation(self):
        source = "繰り返し i が 0 から 6 まで 2 ずつ:\n    print(i)\n"
        self.assertEqual(transpile(source), "for i in range(0, 6, 2):\n    print(i)\n")

    def test_positive_negative_and_empty_ranges(self):
        for start, stop, step in ((0, 5, 1), (0, 6, 2), (5, -1, -2), (5, 0, 1), (1, 1, 1)):
            with self.subTest(start=start, stop=stop, step=step):
                source = f"result = []\n繰り返し i が {start} から {stop} まで {step} ずつ:\n    result.append(i)\n"
                self.assertEqual(evaluate(source)["result"], list(range(start, stop, step)))

    def test_zero_step_and_noninteger_follow_python(self):
        for source, error in (("繰り返し i が 0 から 5 まで 0 ずつ:\n    pass\n", ValueError),
                              ("繰り返し i が 0.5 から 5 まで:\n    pass\n", TypeError)):
            with self.subTest(source=source):
                with self.assertRaises(error):
                    evaluate(source)

    def test_range_arguments_evaluate_once_in_order(self):
        source = "calls = []\ndef arg(x):\n    calls.append(x)\n    return x\n繰り返し i が arg(0) から arg(5) まで arg(2) ずつ:\n    pass\n"
        self.assertEqual(evaluate(source)["calls"], [0, 5, 2])

    def test_range_name_lookup_is_not_replaced_by_hidden_builtin(self):
        source = "def range(*args):\n    return ['custom']\nresult = []\n繰り返し i が 0 から 5 まで:\n    result.append(i)\n"
        self.assertEqual(evaluate(source)["result"], ['custom'])

    def test_range_tuple_remains_one_argument(self):
        source = "def range(*args):\n    return args\nresult = []\n繰り返し i が 0, 1 から 5 まで:\n    result.append(i)\n"
        self.assertEqual(evaluate(source)["result"], [(0, 1), 5])

    def test_range_rejects_argument_injection(self):
        for argument in ("*items", "stop=5", "0 まで"):
            with self.subTest(argument=argument):
                with self.assertRaises(SyntaxError):
                    transpile(f"繰り返し i が {argument} から 10 まで:\n    pass\n")

    def test_with_alias_and_cleanup(self):
        source = "from io import StringIO\n使う StringIO('data') として stream:\n    result = stream.read()\nclosed = stream.closed\n"
        out = evaluate(source)
        self.assertEqual(out["result"], 'data')
        self.assertTrue(out["closed"])

    def test_with_without_alias_and_destructuring(self):
        source = "from contextlib import nullcontext\n使う nullcontext():\n    pass\n使う nullcontext((1, 2)) として (a, b):\n    result = a + b\n"
        self.assertEqual(evaluate(source)["result"], 3)

    def test_multiple_context_managers_use_python(self):
        source = "from contextlib import nullcontext\nwith nullcontext(1) as a, nullcontext(2) as b:\n    result = a + b\n"
        self.assertEqual(transpile(source), source)
        self.assertEqual(evaluate(source)["result"], 3)
        for line in ("使う (a, b):", "使う a として x, b:"):
            with self.subTest(line=line):
                with self.assertRaises(SyntaxError):
                    transpile(line + "\n    pass\n")

    def test_raise_rethrow_chain_and_finally(self):
        source = "試す:\n    試す:\n        投げる ValueError('bad')\n    捕まえる ValueError as cause:\n        投げる RuntimeError('wrapped') from cause\n捕まえる RuntimeError として error:\n    result = (str(error), str(error.__cause__))\n最後に:\n    finished = True\n"
        out = evaluate(source)
        self.assertEqual(out["result"], ('wrapped', 'bad'))
        self.assertTrue(out["finished"])
        with self.assertRaises(ValueError):
            evaluate("試す:\n    投げる ValueError('again')\n捕まえる ValueError:\n    投げる\n")

    def test_assert_message_and_optimization(self):
        source = "確認する False, 'contract'\n"
        with self.assertRaisesRegex(AssertionError, "contract"):
            evaluate(source)
        evaluate(source, optimize=1)

    def test_english_as_in_japanese_statements(self):
        source = "読み込む contextlib as c\n使う c.nullcontext(42) as value:\n    result = value\n"
        self.assertEqual(evaluate(source)["result"], 42)

    def test_loop_else_and_break(self):
        for body, expected in (("pass", True), ("抜ける", False)):
            with self.subTest(body=body):
                source = f"result = False\n繰り返し i が 0 から 1 まで:\n    {body}\nそれ以外:\n    result = True\n"
                self.assertEqual(evaluate(source)["result"], expected)
        self.assertTrue(evaluate("result = False\nFalse の間:\n    pass\nそれ以外:\n    result = True\n")["result"])

    def test_return_tuple_and_none(self):
        source = "関数 pair():\n    1, 2 を戻す\n関数 empty():\n    戻す\nresult = (pair(), empty())\n"
        self.assertEqual(evaluate(source)["result"], ((1, 2), None))

    def test_identifier_calls_and_attributes_are_preserved(self):
        source = "戻す = lambda x: x + 1\n戻す(3)\nobj.戻す(3)\n戻す[0]\n使う = 4\n確認する: int = 3\n読み込む //= 2\n"
        self.assertEqual(transpile(source), source)
        self.assertEqual(transpile("関数 f():\n    戻す (3)\n"), "def f():\n    return (3)\n")

    def test_original_python_headers_with_marker_names(self):
        source = "if の間:\n    pass\nelif なら:\n    pass\nwhile の間:\n    break\nfor x in の間:\n    pass\nmatch value:\n    case なら:\n        pass\n"
        self.assertEqual(transpile(source), source)
        ast.parse(source)

    def test_postposed_attribute_condition(self):
        source = "obj.active の間:\n    pass\n"
        self.assertEqual(transpile(source), "while obj.active:\n    pass\n")

    def test_strings_fstrings_and_comments_are_opaque(self):
        source = '# 使う 投げる 繰り返し\n関数 f(x):\n    f"の間{f\'まで{x}\'}ならば" を戻す\nresult = f(3)\n'
        out = transpile(source)
        self.assertIn('f"の間{f\'まで{x}\'}ならば"', out)
        self.assertEqual(evaluate(source)["result"], 'の間まで3ならば')
        self.assertTrue(out.startswith('# 使う 投げる 繰り返し\n'))

    def test_multiline_whitespace_and_idempotence(self):
        source = "繰り返し i が (\n    0\n) から 5 まで (\n    2\n) ずつ: # step\n    pass\n"
        out = transpile(source)
        self.assertEqual(source.count('\n'), out.count('\n'))
        self.assertEqual(transpile(out), out)
        compile(out, 'lines.jpy', 'exec')
        self.assertEqual(transpile('\ufeff関数 f():\r\n    戻す 1\r\n'), 'def f():\n    return 1\n')

    def test_original_async_generator_import_and_scope(self):
        source = "from math import sqrt as root\nasync def f(x):\n    return await x\ndef g():\n    yield from range(2)\nf = lambda x: [i for i in range(x) if i % 2]\nx = 1\ndef outer():\n    x = 2\n    def inner():\n        nonlocal x\n        x += 1\n    return inner\ndel x\n"
        self.assertEqual(transpile(source), source)
        compile(source, 'python.py', 'exec')

    def test_context_errors_are_rejected_by_final_validation(self):
        for source in ("戻す 1\n", "抜ける\n", "使う cm として:\n    pass\n", "確認する\n", "使う cm: pass\n"):
            with self.subTest(source=source):
                with self.assertRaises(SyntaxError):
                    compile(transpile(source), 'bad.jpy', 'exec')

    def test_parser_error_points_to_source(self):
        with self.assertRaises(SyntaxError) as caught:
            transpile("# header\n繰り返し i が 0 から 4 まで まで:\n    pass\n", filename='origin.jpy')
        self.assertEqual(caught.exception.filename, 'origin.jpy')
        self.assertEqual(caught.exception.lineno, 2)

    def test_new_grammar_has_same_compile_run_behavior(self):
        source = "from contextlib import nullcontext\n使う nullcontext() として _:\n    繰り返し i が 0 から 5 まで 2 ずつ:\n        確認する i % 2 == 0\n        print(i)\n"
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            jpy = root / 'main.jpy'
            jpy.write_text(source, encoding='utf-8')
            direct = io.StringIO()
            with contextlib.redirect_stdout(direct):
                run_file(jpy)
            self.assertEqual(list(root.glob('*.py')), [])
            emitted = root / 'main.py'
            silent = io.StringIO()
            with contextlib.redirect_stdout(silent):
                compile_file(jpy, emitted)
            self.assertEqual(silent.getvalue(), '')
            process = subprocess.run([sys.executable, '-I', str(emitted)], check=True, capture_output=True, text=True)
            self.assertEqual(process.stdout, direct.getvalue())
            self.assertEqual(direct.getvalue(), '0\n2\n4\n')
            self.assertNotIn('japanese_python', emitted.read_text())


if __name__ == '__main__':
    unittest.main()
