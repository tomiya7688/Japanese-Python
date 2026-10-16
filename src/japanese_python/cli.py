"""Minimal, unambiguous two-command CLI for the JPy reference tooling."""

from __future__ import annotations

import argparse
import sys

from .compiler import compile_file
from .runner import run_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jpy", description="JPy v0.1 参考ツール（言語仕様は spec/ を参照）")
    commands = parser.add_subparsers(dest="command", required=True)

    compilation = commands.add_parser("compile", help=".jpy を通常の .py ファイルに変換するだけ")
    compilation.add_argument("source", help="入力 .jpy")
    compilation.add_argument("-o", "--output", help="出力 .py（既定: build/<name>.py）")
    compilation.add_argument("--force", action="store_true", help="既存ファイルの上書きを許可")

    execution = commands.add_parser("run", help=".py を書き出さず、CPython で .jpy を実行")
    execution.add_argument("source", help="実行する .jpy")
    execution.add_argument("script_args", nargs=argparse.REMAINDER, help="プログラムに渡す引数")

    args = parser.parse_args(argv)
    try:
        if args.command == "compile":
            target = compile_file(args.source, args.output, force=args.force)
            print(target)
            return 0
        if args.command == "run":
            passed = args.script_args
            if passed and passed[0] == "--":
                passed = passed[1:]
            run_file(args.source, passed)
            return 0
    except SyntaxError as exc:
        print(f"{exc.filename or args.source}:{exc.lineno or '?'}: {exc.msg}", file=sys.stderr)
        return 1
    except (OSError, ValueError, UnicodeError, RuntimeError) as exc:
        print(f"jpy: {exc}", file=sys.stderr)
        return 1
    raise AssertionError("unreachable")
