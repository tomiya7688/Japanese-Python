"""Execute .jpy source in CPython, without writing a translated .py file."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

from .transpiler import transpile


def run_file(filename: str | Path, argv: Sequence[str] = ()) -> None:
    """Read a JPy source file, compile *in memory*, and execute via CPython.

    This deliberately does NOT call ``compile_file`` and does NOT create a .py
    file. The .jpy path is kept for ``__file__`` and traceback filenames.
    """
    if sys.implementation.name != "cpython":
        raise RuntimeError("jpy run は CPython 上での実行だけをサポートします")

    source_path = Path(filename).resolve(strict=True)
    if source_path.suffix != ".jpy":
        raise ValueError("入力は .jpy ファイルである必要があります")
    source = source_path.read_text(encoding="utf-8-sig")
    translated = transpile(source, filename=str(source_path))
    code = compile(translated, str(source_path), "exec", dont_inherit=True)

    namespace = {
        "__name__": "__main__",
        "__file__": str(source_path),
        "__package__": None,
        "__spec__": None,
        "__cached__": None,
    }
    previous_argv = sys.argv
    previous_path = sys.path[:]
    try:
        sys.argv = [str(source_path), *argv]
        sys.path.insert(0, str(source_path.parent))
        exec(code, namespace)
    finally:
        sys.argv = previous_argv
        sys.path[:] = previous_path
