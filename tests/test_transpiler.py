"""Conformance tests for spec/JPy-v0.1.md (source is normative)."""

from __future__ import annotations

import ast
import unittest

from japanese_python import transpile


class TranspilerConformanceTests(unittest.TestCase):
    def test_spec_example_exact_python(self):
        source = (
            "関数 判定(点数: int) -> str:\n"
            "    もし 点数 >= 80:\n"
            "        戻す \"優\"\n"
            "    それ以外でもし 点数 >= 60:\n"
            "        \"合格\" を戻す\n"
            "    それ以外:\n"
            "        戻す \"不合格\"\n"
            "\n"
            "各 点数 を [55, 65, 82] から:\n"
            "    print(判定(点数))\n"
        )
        expected = (
            "def 判定(点数: int) -> str:\n"
            "    if 点数 >= 80:\n"
            "        return \"優\"\n"
            "    elif 点数 >= 60:\n"
            "        return \"合格\"\n"
            "    else:\n"
            "        return \"不合格\"\n"
            "\n"
            "for 点数 in [55, 65, 82]:\n"
            "    print(判定(点数))\n"
        )
        translated = transpile(source)
        self.assertEqual(translated, expected)
        namespace = {"__name__": "tests"}
        import contextlib
        import io
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            exec(compile(translated, "<conformance>", "exec"), namespace)
        self.assertEqual(buffer.getvalue(), "不合格\n合格\n優\n")

    def test_preposed_and_postposed_equivalence(self):
        source = (
            "関数 first(x):\n"
            "    もし x:\n"
            "        戻す 42\n"
            "    それ以外:\n"
            "        戻す 0\n"
            "関数 second(x):\n"
            "    x なら:\n"
            "        42 を戻す\n"
            "    それ以外:\n"
            "        0 を戻す\n"
        )
        namespace = {}
        exec(transpile(source), namespace)
        for value in (0, 1, [], [1]):
            self.assertEqual(namespace["first"](value), namespace["second"](value))

    def test_import_try_catch_alias_finally(self):
        source = (
            "読み込む math として m\n"
            "関数 compute(x):\n"
            "    試す:\n"
            "        もし x < 0:\n"
            "            raise ValueError('negative')\n"
            "        戻す m.sqrt(x)\n"
            "    捕まえる ValueError として error:\n"
            "        戻す str(error)\n"
            "    最後に:\n"
            "        何もしない\n"
        )
        translated = transpile(source)
        namespace = {}
        exec(translated, namespace)
        self.assertEqual(namespace["compute"](9), 3.0)
        self.assertEqual(namespace["compute"](-1), "negative")

    def test_class_for_and_loop_controls(self):
        source = (
            "クラス Counter:\n"
            "    関数 count(self):\n"
            "        x = 0\n"
            "        繰り返し x < 5:\n"
            "            x += 1\n"
            "            もし x == 2:\n"
            "                続ける\n"
            "            x == 3 なら:\n"
            "                抜ける\n"
            "        x を戻す\n"
            "結果 = Counter().count()\n"
        )
        namespace = {}
        exec(transpile(source), namespace)
        self.assertEqual(namespace["結果"], 3)

    def test_destructuring_and_multiline(self):
        source = (
            "各 (x, y) を [(1, 2), (3, 4)] から:\n"
            "    print(x + y)\n"
            "各 a を (\n"
            "    1,\n"
            "    2,\n"
            ") から:\n"
            "    print(a)\n"
        )
        converted = transpile(source)
        ast.parse(converted)
        self.assertIn("for (x, y) in [(1, 2), (3, 4)]:", converted)
        self.assertEqual(converted.count("\n"), source.count("\n"))

    def test_preserves_comments_and_strings_and_fstrings(self):
        source = (
            "# 関数 関数名: を戻す\n"
            "s = 'もし x なら: 読み込む foo を戻す'\n"
            's2 = f"なら: {1 + 2} から: {s}"\n'
            "関数 f():\n"
            "    '文字列中の 戻す はそのまま' を戻す # もし\n"
        )
        converted = transpile(source)
        self.assertIn("s = 'もし x なら: 読み込む foo を戻す'", converted)
        self.assertIn('f"なら: {1 + 2} から: {s}"', converted)
        self.assertTrue(converted.startswith("# 関数 関数名: を戻す\n"))
        self.assertIn("return '文字列中の 戻す はそのまま' # もし", converted)
        ast.parse(converted)

    def test_python_syntax_unmodified(self):
        source = (
            "def f(x):\n"
            "    result = [i ** 2 for i in range(x)]\n"
            "    return result\n"
            "match 3:\n"
            "    case 3:\n"
            "        print('ok')\n"
        )
        self.assertEqual(transpile(source), source)

    def test_identifier_collision(self):
        source = (
            "戻す = 7\n"
            "抜ける = 2\n"
            "読み込む = 3\n"
            "print(戻す + 抜ける + 読み込む)\n"
        )
        self.assertEqual(transpile(source), source)
        self.assertEqual(transpile("戻す\n"), "return\n")

    def test_invalid_hybrid_rejected(self):
        with self.assertRaisesRegex(SyntaxError, "組み合わせられません"):
            transpile("もし x なら:\n    戻す x\n", filename="sample.jpy")

    def test_invalid_for_separators_rejected(self):
        with self.assertRaisesRegex(SyntaxError, "区切ってください"):
            transpile("各 a を b を c から:\n    何もしない\n")

    def test_inline_japanese_suite_not_supported(self):
        with self.assertRaises(SyntaxError):
            compile(transpile("もし x: print(x)\n"), "a.jpy", "exec")

    def test_semicolon_not_supported(self):
        with self.assertRaisesRegex(SyntaxError, "セミコロン"):
            transpile("関数 f():\n    戻す 1; x = 2\n")

    def test_one_module_import_only(self):
        with self.assertRaisesRegex(SyntaxError, "1 モジュール"):
            transpile("読み込む os, sys\n")
        self.assertEqual(transpile("読み込む os\n読み込む sys\n"), "import os\nimport sys\n")

    def test_utf8_source_and_encoding_cookie(self):
        self.assertEqual(transpile("# coding: utf-8\n関数 f():\n    戻す '日本語'\n"),
                         "# coding: utf-8\ndef f():\n    return '日本語'\n")
        with self.assertRaisesRegex(SyntaxError, "UTF-8"):
            transpile("# coding: latin-1\n戻す 2\n")
        self.assertEqual(transpile("\ufeff戻す 2\n"), "return 2\n")

    def test_source_line_number_retained(self):
        source = "関数 f():\n    何もしない\n    戻す (\n        42\n    )\n"
        compiled = transpile(source)
        self.assertEqual(len(source.splitlines()), len(compiled.splitlines()))
        self.assertIn("return (\n", compiled)
        self.assertIsInstance(compile(compiled, "file.jpy", "exec"), type(compile("x=1", "x", "exec")))


if __name__ == "__main__":
    unittest.main()
