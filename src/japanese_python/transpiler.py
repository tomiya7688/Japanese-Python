"""A minimal reference transpiler for JPy v0.1.

The language specification is in spec/JPy-v0.1.md. This implementation is
intentionally syntax-only: it does not provide a JPy runtime or modify Python
expressions. All edits are performed on token boundaries, preserving physical
line numbers, comments, and string contents.
"""

from __future__ import annotations

import io
import tokenize
from dataclasses import dataclass
from typing import NamedTuple


class _Edit(NamedTuple):
    start: int
    end: int
    replacement: str


@dataclass(frozen=True)
class _Token:
    token: tokenize.TokenInfo
    depth: int

    @property
    def text(self) -> str:
        return self.token.string


def _syntax_error(message: str, filename: str, token: tokenize.TokenInfo, lines: list[str]) -> SyntaxError:
    line_number, column = token.start
    line = lines[line_number - 1] if line_number <= len(lines) else ""
    return SyntaxError(message, (filename, line_number, column + 1, line))


def _depth_tokens(tokens: list[tokenize.TokenInfo]) -> list[_Token]:
    """Mark parentheses depth immediately before each token, not indentation."""
    depth = 0
    result: list[_Token] = []
    for token in tokens:
        if token.type in (tokenize.NL, tokenize.COMMENT, tokenize.INDENT, tokenize.DEDENT):
            continue
        if token.type in (tokenize.NEWLINE, tokenize.ENDMARKER):
            continue
        if token.string in (")", "]", "}"):
            depth -= 1
        result.append(_Token(token=token, depth=depth))
        if token.string in ("(", "[", "{"):
            depth += 1
    return result


def _offset(line_starts: list[int], loc: tuple[int, int]) -> int:
    line, col = loc
    return line_starts[line - 1] + col


def _translate_statement(
    tokens: list[tokenize.TokenInfo],
    lines: list[str],
    starts: list[int],
    filename: str,
) -> list[_Edit]:
    grouped = _depth_tokens(tokens)
    if not grouped:
        return []
    first = grouped[0]
    last = grouped[-1]
    sig = [t for t in grouped if t.depth == 0]
    if not sig:
        return []

    def replace(token: _Token, replacement: str) -> _Edit:
        return _Edit(_offset(starts, token.token.start), _offset(starts, token.token.end), replacement)

    def remove_after(previous: _Token, marker: _Token) -> _Edit:
        return _Edit(_offset(starts, previous.token.end), _offset(starts, marker.token.end), "")

    def fail(message: str, target: _Token = first) -> None:
        raise _syntax_error(message, filename, target.token, lines)

    def make(edits: list[_Edit]) -> list[_Edit]:
        if any(item.text == ";" for item in sig):
            fail("JPy の構文をセミコロンで連結することはできません")
        return edits

    colon = last.text == ":" and last.depth == 0
    head = first.text

    # Tokens constituting the header excluding the final ':' (if present).
    header = sig[:-1] if colon else []

    # Canonical Japanese if/elif have matching explicit "... ならば:" syntax.
    # Original Python `if`, `elif`, and `for` syntax is never rewritten.
    if colon and head in ("もし", "それ以外でもし"):
        if len(header) < 3 or header[-1].text != "ならば":
            fail(f"{head} は '{head} 条件 ならば:' の形で書いてください")
        return make([
            replace(first, "if" if head == "もし" else "elif"),
            remove_after(header[-2], header[-1]),
        ])

    # Keyword-led compound statements, recognized only as block headers.
    head_map = {
        "関数": "def",
        "クラス": "class",
        "それ以外": "else",
        "試す": "try",
        "最後に": "finally",
    }
    if colon and head in head_map:
        if head in ("それ以外", "試す", "最後に") and len(header) != 1:
            fail(f"{head} は単独のブロックヘッダとして使用してください")
        if head in ("関数", "クラス") and len(header) < 2:
            fail(f"{head} の後には名前が必要です")
        return make([replace(first, head_map[head])])

    # Numeric for range: 繰り返し i が 0 から 5 まで:
    # End is EXCLUSIVE, matching CPython's range(0, 5) exactly.
    if colon and head == "繰り返し" and header[-1].text == "まで":
        if len(header) < 7:
            fail("繰り返し は '繰り返し i が 開始 から 終了 まで:' の形で書いてください")
        ga_positions = [i for i, item in enumerate(header) if item.text == "が"]
        kara_positions = [i for i, item in enumerate(header) if item.text == "から"]
        if (ga_positions != [2] or len(kara_positions) != 1
                or kara_positions[0] < 4 or kara_positions[0] >= len(header) - 2
                or header[1].token.type != tokenize.NAME):
            fail("範囲繰り返しは '繰り返し 名前 が 開始 から 終了 まで:' としてください")
        from_index = kara_positions[0]
        first_start_expr = header[3]
        last_start_expr = header[from_index - 1]
        first_end_expr = header[from_index + 1]
        last_end_expr = header[-2]

        # Normalize the separator whitespace without changing physical line count.
        # A newline outside a parenthesized expression is rejected for v0.1.
        a = _offset(starts, first.token.start)
        b = _offset(starts, first_start_expr.token.start)
        c = _offset(starts, last_start_expr.token.end)
        d = _offset(starts, first_end_expr.token.start)
        e = _offset(starts, last_end_expr.token.end)
        f = _offset(starts, header[-1].token.end)
        original = "".join(lines)
        if any("\n" in original[x:y] or "\r" in original[x:y]
               for x, y in ((a, b), (c, d), (e, f))):
            fail("範囲構文の区切りでは改行できません（式内の括弧による改行は可能）")
        return make([
            _Edit(a, b, f"for {header[1].text} in range("),
            _Edit(c, d, ", "),
            _Edit(e, f, ")"),
        ])

    # Generic Python for-loop: keep the original 各 form, and accept
    # 繰り返し with the same target/iterable grammar until further spec decisions.
    if colon and head in ("各", "繰り返し") and header[-1].text == "から":
        if len(header) < 5:
            fail(f"{head} は '{head} 対象 を 式 から:' の形で書いてください")
        separators = [i for i, item in enumerate(header) if item.text == "を"]
        if len(separators) != 1 or separators[0] < 2 or separators[0] >= len(header) - 2:
            fail(f"{head} の対象と反復可能な式は最上位の 'を' で一度だけ区切ってください")
        target_sep = header[separators[0]]
        end_marker = header[-1]
        prev = header[-2]
        return make([
            replace(first, "for"),
            replace(target_sep, "in"),
            remove_after(prev, end_marker),
        ])

    if colon and head in ("各", "繰り返し"):
        fail(f"{head} の構文が不正です。範囲は '繰り返し i が 0 から 5 まで:'、条件反復は '条件 の間:' を使用してください")

    # Postposed while: 条件 の間: -> while 条件:
    if colon and len(header) >= 2 and header[-1].text == "の間":
        if head in ("もし", "それ以外でもし"):
            fail("条件分岐と 'の間' を組み合わせることはできません")
        return make([
            _Edit(_offset(starts, first.token.start), _offset(starts, first.token.start), "while "),
            remove_after(header[-2], header[-1]),
        ])

    if colon and head == "捕まえる":
        sep = [i for i, item in enumerate(header) if item.text == "として"]
        if len(sep) > 1:
            fail("例外の別名は 'として' で一度だけ指定してください")
        edits = [replace(first, "except")]
        if sep:
            k = sep[0]
            if k < 2 or k != len(header) - 2:
                fail("捕まえる の別名指定は '例外 として 名前' にしてください")
            edits.append(replace(header[k], "as"))
        return make(edits)

    # The second Japanese word order: 'expression なら:'.
    # Do not silently support `もし condition なら:` or other hybrids.
    if colon and len(header) >= 2 and header[-1].text == "なら":
        end_marker = header[-1]
        previous = header[-2]
        return make([
            _Edit(_offset(starts, first.token.start), _offset(starts, first.token.start), "if "),
            remove_after(previous, end_marker),
        ])

    # Import is a simple statement without a trailing colon.
    if head == "読み込む" and len(sig) >= 2 and sig[1].text not in ("=", ":=", "+=", "-=", "*=", "/=", ":", ".", "("):
        if any(item.text == "," and item.depth == 0 for item in grouped):
            fail("読み込む は v0.1 では一度に 1 モジュールのみ指定できます")
        sep = [i for i, item in enumerate(sig) if item.text == "として"]
        if len(sep) > 1:
            fail("読み込む の別名は 'として' で一度だけ指定してください")
        edits = [replace(first, "import")]
        if sep:
            k = sep[0]
            if k < 2 or k != len(sig) - 2:
                fail("読み込む の別名指定は 'モジュール として 名前' にしてください")
            edits.append(replace(sig[k], "as"))
        return make(edits)

    # The third Japanese word order: 'expression を戻す'.
    if len(sig) >= 2 and sig[-1].text == "を戻す":
        if head == "戻す":
            fail("戻す と 'を戻す' を同じ文で混在できません")
        previous = sig[-2]
        marker = sig[-1]
        return make([
            _Edit(_offset(starts, first.token.start), _offset(starts, first.token.start), "return "),
            remove_after(previous, marker),
        ])

    simple_map = {"戻す": "return", "抜ける": "break", "続ける": "continue", "何もしない": "pass"}
    if head in simple_map:
        if head != "戻す" and len(sig) != 1:
            # "抜ける = 1" remains a valid Python assignment to an identifier.
            return []
        if head == "戻す" and len(sig) > 1 and sig[1].text in ("=", ":=", "+=", "-=", "*=", "/=", ":"):
            # JPy's words are otherwise legal Unicode Python identifiers.
            return []
        return make([replace(first, simple_map[head])])

    return []


def transpile(source: str, *, filename: str = "<jpy>") -> str:
    """Translate a JPy v0.1 source string into plain Python.

    The result has exactly the same number of physical lines as ``source``;
    Python's AST, execution semantics, and imports are unchanged. Callers may
    validate/compile the returned Python source as needed.
    """
    if not isinstance(source, str):
        raise TypeError("source must be str")

    # Python honours source encoding declarations when reading .py files.
    # JPy source and generated Python are *both* UTF-8: reject incompatible
    # cookies rather than emit a file that CPython would decode incorrectly.
    source = source.removeprefix("\ufeff")
    declared_encoding, _ = tokenize.detect_encoding(io.BytesIO(source.encode("utf-8")).readline)
    if declared_encoding.lower().replace("_", "-") not in ("utf-8", "utf-8-sig"):
        raise SyntaxError(f"JPy v0.1 は UTF-8 のみ対応しています: {declared_encoding}", (filename, 1, 1, source.splitlines(keepends=True)[0]))

    lines = source.splitlines(keepends=True)
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line))

    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        statements: list[list[tokenize.TokenInfo]] = []
        current: list[tokenize.TokenInfo] = []
        for token in tokens:
            if token.type == tokenize.ENDMARKER:
                if current:
                    statements.append(current)
                break
            if token.type in (tokenize.INDENT, tokenize.DEDENT, tokenize.NL, tokenize.COMMENT):
                continue
            if token.type == tokenize.NEWLINE:
                if current:
                    statements.append(current)
                    current = []
                continue
            current.append(token)
    except (tokenize.TokenError, IndentationError) as exc:
        raise SyntaxError(f"JPy トークン解析エラー: {exc}") from exc

    edits: list[_Edit] = []
    for statement in statements:
        edits.extend(_translate_statement(statement, lines, starts, filename))

    previous = len(source)
    for start, end, value in sorted(edits, reverse=True):
        if end > previous:
            raise AssertionError("Overlapping JPy token edits")
        source = source[:start] + value + source[end:]
        previous = start
    return source
