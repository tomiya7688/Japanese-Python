"""Both Japanese as-spellings and English as have the same meaning."""
from __future__ import annotations

import contextlib
import io
import itertools
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from japanese_python import transpile
from japanese_python.compiler import compile_file
from japanese_python.runner import run_file


WORDS = ("として", "と名付ける", "as")


def evaluate(source: str) -> dict:
    namespace = {}
    exec(compile(transpile(source), "aliases.jpy", "exec"), namespace)
    return namespace


class AliasSpellingTests(unittest.TestCase):
    def test_all_spellings_emit_identical_python(self):
        examples = (
            ("読み込む math {word} 数学\n", "import math as 数学\n"),
            ("試す:\n    pass\n捕まえる ValueError {word} エラー:\n    pass\n",
             "try:\n    pass\nexcept ValueError as エラー:\n    pass\n"),
            ("使う open('sample.txt') {word} ファイル:\n    pass\n",
             "with open('sample.txt') as ファイル:\n    pass\n"),
        )
        for word, (source, expected) in itertools.product(WORDS, examples):
            with self.subTest(word=word, source=source):
                converted = transpile(source.format(word=word))
                self.assertEqual(converted, expected)
                self.assertEqual(transpile(converted), converted)

    def test_import_binds_the_same_module(self):
        for word in WORDS:
            with self.subTest(word=word):
                out = evaluate(f"読み込む math {word} 数学\nresult = 数学.sqrt(9)\n")
                self.assertEqual(out['result'], 3.0)
                self.assertEqual(out['数学'].__name__, 'math')

    def test_except_binds_and_cleans_up_the_exception_name(self):
        for word in WORDS:
            with self.subTest(word=word):
                out = evaluate(
                    "original = ValueError('sample')\n試す:\n    raise original\n"
                    f"捕まえる ValueError {word} error:\n    result = error\n")
                self.assertIs(out['result'], out['original'])
                self.assertNotIn('error', out)

    def test_with_binds_enter_result_and_runs_exit(self):
        for word in WORDS:
            with self.subTest(word=word):
                source = (
                    "value = object()\nevents = []\nclass Manager:\n"
                    "    def __enter__(self):\n        events.append('enter')\n        return value\n"
                    "    def __exit__(self, *exc):\n        events.append('exit')\n"
                    "manager = Manager()\n"
                    f"使う manager {word} received:\n    result = received\n"
                )
                out = evaluate(source)
                self.assertIs(out['result'], out['value'])
                self.assertIsNot(out['result'], out['manager'])
                self.assertEqual(out['events'], ['enter', 'exit'])

    def test_with_destructuring_and_aliasless_forms(self):
        for word in WORDS:
            with self.subTest(word=word):
                out = evaluate(
                    "from contextlib import nullcontext\n"
                    f"使う nullcontext((1, 2)) {word} (a, b):\n    result = a + b\n"
                    "使う nullcontext():\n    pass\n")
                self.assertEqual(out['result'], 3)
        self.assertEqual(transpile('読み込む math\n'), 'import math\n')

    def test_strings_comments_and_fstrings_are_unchanged(self):
        source = (
            "# と名付ける として as\n"
            "from contextlib import nullcontext\n"
            "使う nullcontext(f'と名付ける {1 + 1}') と名付ける text:  # として\n"
            "    result = text\n"
        )
        expected = source.replace("使う nullcontext", "with nullcontext").replace(
            ") と名付ける text:", ") as text:")
        self.assertEqual(transpile(source), expected)
        self.assertEqual(evaluate(source)['result'], 'と名付ける 2')

    def test_marker_words_are_not_global_reserved_names(self):
        source = 'と名付ける = lambda x: x\nとして = 1\nと名付ける(として)\nobj.と名付ける(1)\n'
        self.assertEqual(transpile(source), source)
        out = evaluate(
            "from contextlib import nullcontext\nと名付ける = nullcontext(7)\n"
            "使う (と名付ける) として result:\n    pass\n")
        self.assertEqual(out['result'], 7)

    def test_original_english_statements_remain_english(self):
        source = (
            "import math as と名付ける\nfrom contextlib import nullcontext\n"
            "with nullcontext(1) as として:\n    result = として\n"
        )
        self.assertEqual(transpile(source), source)
        self.assertEqual(evaluate(source)['result'], 1)
        for word in WORDS[:2]:
            with self.subTest(word=word):
                invalid = f'import math {word} m\n'
                self.assertEqual(transpile(invalid), invalid)
                with self.assertRaises(SyntaxError):
                    compile(transpile(invalid), 'english.py', 'exec')

    def test_duplicate_or_mixed_markers_are_rejected(self):
        examples = (
            "読み込む math {first} {second} m\n",
            "試す:\n    pass\n捕まえる ValueError {first} {second} error:\n    pass\n",
            "使う manager {first} {second} value:\n    pass\n",
        )
        for first, second, source in itertools.product(WORDS, WORDS, examples):
            with self.subTest(first=first, second=second, source=source):
                with self.assertRaises(SyntaxError):
                    transpile(source.format(first=first, second=second))

    def test_missing_targets_are_rejected(self):
        for word in WORDS:
            for source in (
                f'読み込む math {word}\n',
                f'試す:\n    pass\n捕まえる ValueError {word}:\n    pass\n',
                f'使う manager {word}:\n    pass\n',
            ):
                with self.subTest(word=word, source=source):
                    with self.assertRaises(SyntaxError):
                        compile(transpile(source), 'missing.jpy', 'exec')

    def test_spacing_multiline_and_source_line_contract(self):
        source = (
            "from contextlib import nullcontext\n"
            "使う (\n    nullcontext(42)\n)\tと名付ける\tvalue:\n    result = value\n"
        )
        translated = transpile(source)
        self.assertEqual(source.count('\n'), translated.count('\n'))
        self.assertEqual(evaluate(source)['result'], 42)
        for invalid in ('読み込む math と 名付ける m\n', '読み込む math と名付けるm\n'):
            with self.subTest(source=invalid):
                with self.assertRaises(SyntaxError):
                    compile(transpile(invalid), 'spacing.jpy', 'exec')

    def test_compile_and_run_use_identical_alias_rules(self):
        for word in WORDS:
            with self.subTest(word=word), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                source = root / 'main.jpy'
                source.write_text(
                    f"読み込む io {word} streams\n試す:\n"
                    f"    使う streams.StringIO('ok') {word} stream:\n        print(stream.read())\n"
                    "    raise ValueError('bad')\n"
                    f"捕まえる ValueError {word} error:\n    print(error)\n"
                    "print(stream.closed)\n", encoding='utf-8')
                direct = io.StringIO()
                with contextlib.redirect_stdout(direct):
                    run_file(source)
                self.assertEqual(sorted(p.name for p in root.iterdir()), ['main.jpy'])
                emitted = root / 'main.py'
                silent = io.StringIO()
                with contextlib.redirect_stdout(silent):
                    compile_file(source, emitted)
                self.assertEqual(silent.getvalue(), '')
                process = subprocess.run([sys.executable, '-I', str(emitted)], check=True,
                                         capture_output=True, text=True)
                self.assertEqual(process.stdout, direct.getvalue())
                self.assertEqual(direct.getvalue(), 'ok\nbad\nTrue\n')
                self.assertNotIn('japanese_python', emitted.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
