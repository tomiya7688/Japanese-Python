"""Write a standalone Python source artifact from a .jpy input file."""

from __future__ import annotations

from pathlib import Path

from .transpiler import transpile


def compile_file(
    filename: str | Path, output: str | Path | None = None, *, force: bool = False
) -> Path:
    """Translate a JPy file into a plain .py file with no runtime dependency.

    The compiler never executes application code and never invokes a packager.
    """
    source_path = Path(filename).resolve(strict=True)
    if source_path.suffix != ".jpy":
        raise ValueError("入力は .jpy ファイルである必要があります")
    target = Path(output) if output is not None else Path("build") / (source_path.stem + ".py")
    if target.suffix != ".py":
        raise ValueError("出力は .py ファイルである必要があります")
    if target.resolve() == source_path:
        raise ValueError("入力ファイルを上書きできません")
    if target.exists() and not force:
        raise FileExistsError(f"すでに存在します: {target}。上書きには --force が必要です")
    source = source_path.read_text(encoding="utf-8-sig")
    translated = transpile(source, filename=str(source_path))
    # This is syntax validation, not execution. The .py file is self-contained.
    compile(translated, str(source_path), "exec", dont_inherit=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Explicit exclusive create avoids accidental overwrites in races.
    with target.open("w" if force else "x", encoding="utf-8", newline="") as handle:
        handle.write(translated)
    return target
