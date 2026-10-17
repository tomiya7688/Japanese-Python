"""Token-based reference translator for spec/JPy-v0.1.md.

Only statement syntax is translated. No application code is executed here.
Comments, literals, expression text and physical line numbers are retained
apart from the documented BOM/newline normalization.
"""
from __future__ import annotations

import ast
import io
import keyword
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

    def is_name(self, text: str) -> bool:
        return self.token.type == tokenize.NAME and self.text == text


# An English statement remains English, including its inline suite. Literal
# and expression keywords (True, not, lambda, await, ...) are not in this set.
_PYTHON_HEADS = frozenset((
    "def", "class", "if", "elif", "else", "for", "while", "try", "except",
    "finally", "with", "async", "return", "raise", "assert", "import", "from",
    "pass", "break", "continue", "del", "global", "nonlocal", "yield",
    "match", "case",
))
_ASSIGNMENTS = frozenset((
    "=", ":=", ":", "+=", "-=", "*=", "/=", "//=", "%=", "**=", "@=",
    "&=", "|=", "^=", ">>=", "<<=",
))
# Equivalent spellings at the as-position in Japanese import/except/with.
_ALIAS_WORDS = frozenset(("として", "と名付ける", "as"))


def _syntax_error(message: str, filename: str, token: tokenize.TokenInfo,
                  lines: list[str]) -> SyntaxError:
    row, col = token.start
    line = lines[row - 1] if 0 < row <= len(lines) else ""
    return SyntaxError(message, (filename, row, col + 1, line))


def _depth_tokens(tokens: list[tokenize.TokenInfo]) -> list[_Token]:
    depth = 0
    result = []
    for token in tokens:
        if token.type == tokenize.OP and token.string in (")", "]", "}"):
            depth -= 1
        result.append(_Token(token, depth))
        if token.type == tokenize.OP and token.string in ("(", "[", "{"):
            depth += 1
    return result


def _translate_statement(tokens: list[tokenize.TokenInfo], source: str,
                         lines: list[str], starts: list[int], filename: str) -> list[_Edit]:
    grouped = _depth_tokens(tokens)
    sig = [t for t in grouped if t.depth == 0]
    if not sig:
        return []
    first, last = sig[0], sig[-1]
    head = first.text

    def offset(loc: tuple[int, int]) -> int:
        return starts[loc[0] - 1] + loc[1]

    def fail(message: str, target: _Token = first) -> None:
        raise _syntax_error(message, filename, target.token, lines)

    def edit(token: _Token, value: str) -> _Edit:
        return _Edit(offset(token.token.start), offset(token.token.end), value)

    def gap(left: _Token, right: _Token) -> str:
        return source[offset(left.token.end):offset(right.token.start)]

    def spaced(left: _Token, right: _Token) -> bool:
        between = gap(left, right)
        return bool(between) and all(c in " \t\f" for c in between)

    def cut(left: _Token, marker: _Token, replacement: str = "") -> _Edit:
        # Removing a cross-line separator would invalidate our line contract.
        if not spaced(left, marker):
            fail("構文語の前に空白が必要です。区切り自体では改行できません", marker)
        return _Edit(offset(left.token.end), offset(marker.token.end), replacement)

    def make(edits: list[_Edit]) -> list[_Edit]:
        if any(t.token.type == tokenize.OP and t.text == ";" for t in sig):
            fail("JPy の構文をセミコロンで連結することはできません")
        return edits

    def positions(items: list[_Token], name: str) -> list[int]:
        return [i for i, t in enumerate(items) if t.is_name(name)]

    def alias_positions(items: list[_Token]) -> list[int]:
        return [i for i, t in enumerate(items)
                if t.token.type == tokenize.NAME and t.text in _ALIAS_WORDS]

    def expr_text(items: list[_Token]) -> str:
        if not items:
            fail("Python の式が必要です")
        return source[offset(items[0].token.start):offset(items[-1].token.end)]

    def expression(items: list[_Token]) -> ast.expr:
        try:
            return ast.parse(expr_text(items), mode="eval").body
        except SyntaxError:
            fail("有効な Python の式を指定してください", items[0] if items else first)
        raise AssertionError("unreachable")

    if (first.token.type == tokenize.NAME and head in _PYTHON_HEADS) or head == "@":
        return []
    # Japanese names in assignment, annotation or attribute expressions remain
    # names. A no-space call/index such as 戻す(x) is also ordinary Python.
    if len(sig) > 1 and sig[1].text in _ASSIGNMENTS and not (len(sig) == 2 and sig[1].text == ":"):
        return []
    colon = last.token.type == tokenize.OP and last.text == ":"
    header = sig[:-1] if colon else []
    separated_head = len(sig) > 1 and spaced(first, sig[1])

    if colon and separated_head and head in ("もし", "それ以外でもし"):
        if len(header) < 3 or not header[-1].is_name("ならば"):
            fail(f"{head} は '{head} 条件 ならば:' の形で書いてください")
        return make([edit(first, "if" if head == "もし" else "elif"),
                     cut(header[-2], header[-1])])

    heads = {"関数": "def", "クラス": "class", "それ以外": "else",
             "試す": "try", "最後に": "finally"}
    if colon and head in heads and (separated_head or len(header) == 1):
        if head in ("それ以外", "試す", "最後に") and len(header) != 1:
            fail(f"{head} は単独のブロックヘッダとして使用してください")
        if head in ("関数", "クラス") and len(header) < 2:
            fail(f"{head} の後には名前が必要です")
        return make([edit(first, heads[head])])

    if colon and separated_head and head in ("繰り返し", "各"):
        if head == "繰り返し" and header[-1].text in ("まで", "ずつ"):
            ga, kara, made = (positions(header, word) for word in ("が", "から", "まで"))
            stepped = header[-1].is_name("ずつ")
            if (len(header) < 7 or ga != [2] or len(kara) != 1 or len(made) != 1
                    or header[1].token.type != tokenize.NAME or keyword.iskeyword(header[1].text)):
                fail("範囲は '繰り返し 名前 が 開始 から 終了 まで [増分 ずつ]:' としてください")
            k, m = kara[0], made[0]
            if (k < 4 or m < k + 2 or (not stepped and m != len(header) - 1)
                    or (stepped and (m > len(header) - 3 or positions(header, "ずつ") != [len(header) - 1]))):
                fail("範囲の開始・終了・増分を正しく区切ってください")
            operands = [header[3:k], header[k + 1:m]]
            separators = [header[2], header[k]]
            if stepped:
                operands.append(header[m + 1:-1])
                separators.append(header[m])
            edits = [edit(first, "for")]
            for n, (operand, separator) in enumerate(zip(operands, separators)):
                node = expression(operand)
                if not spaced(header[1] if n == 0 else operands[n - 1][-1], separator):
                    fail("範囲の構文語の前に空白が必要です", separator)
                if not spaced(separator, operand[0]):
                    fail("範囲の構文語の後に空白が必要です", separator)
                # A tuple is one argument, never extra range() arguments.
                prefix = "(" if isinstance(node, ast.Tuple) else ""
                suffix = ")" if prefix else ""
                a = offset(separator.token.start) if n == 0 else offset(operands[n - 1][-1].token.end)
                edits.append(_Edit(a, offset(operand[0].token.start),
                                   ("in range(" if n == 0 else ", ") + prefix))
                if suffix:
                    end = offset(operand[-1].token.end)
                    edits.append(_Edit(end, end, suffix))
            edits.append(cut(operands[-1][-1], header[-1], ")"))
            return make(edits)
        if len(header) < 5 or not header[-1].is_name("から"):
            fail("反復は '繰り返し 対象 を 式 から:'、条件反復は '条件 の間:' を使用してください")
        separators = positions(header, "を")
        if len(separators) != 1 or not 2 <= separators[0] < len(header) - 2:
            fail("対象と反復可能な式は最上位の 'を' で一度だけ区切ってください")
        k = separators[0]
        if not spaced(header[k - 1], header[k]) or not spaced(header[k], header[k + 1]):
            fail("'を' の前後に空白が必要です", header[k])
        return make([edit(first, "for"), edit(header[k], "in"), cut(header[-2], header[-1])])

    if colon and head == "捕まえる" and (separated_head or len(header) == 1):
        if len(header) > 1 and header[1].text == "*":
            fail("例外グループには Python の except* を使用してください")
        aliases = alias_positions(header)
        if len(aliases) > 1:
            fail("例外の別名指定（として / と名付ける / as）は一度だけ指定してください")
        edits = [edit(first, "except")]
        if aliases:
            k = aliases[0]
            if k < 2 or k != len(header) - 2 or not spaced(header[k - 1], header[k]) or not spaced(header[k], header[k + 1]):
                fail("捕まえる の別名指定は '例外 として 名前' にしてください")
            edits.append(edit(header[k], "as"))
        return make(edits)

    if colon and head == "使う" and separated_head:
        aliases = alias_positions(header)
        if len(aliases) > 1:
            fail("使う は 1 つのコンテキストマネージャーを指定します")
        k = aliases[0] if aliases else len(header)
        node = expression(header[1:k])
        if isinstance(node, ast.Tuple):
            fail("複数のコンテキストマネージャーには Python の with を使用してください")
        edits = [edit(first, "with")]
        if aliases:
            if k == len(header) - 1 or not spaced(header[k - 1], header[k]) or not spaced(header[k], header[k + 1]):
                fail("使う の別名指定は '式 として 対象' にしてください")
            edits.append(edit(header[k], "as"))
            # An unparenthesized comma can introduce a second with-item rather
            # than a destructuring target; the Japanese form is single-item.
            try:
                parsed = ast.parse(f"with {expr_text(header[1:k])} as {expr_text(header[k + 1:])}:\n    pass\n")
            except SyntaxError:
                fail("使う の代入先が不正です")
            if len(parsed.body[0].items) != 1:
                fail("分解代入の対象は括弧で囲んでください")
        return make(edits)

    if colon and len(header) >= 2 and header[-1].token.type == tokenize.NAME:
        marker = header[-1]
        if marker.text in ("なら", "の間") and spaced(header[-2], marker):
            return make([_Edit(offset(first.token.start), offset(first.token.start),
                               "if " if marker.text == "なら" else "while "),
                         cut(header[-2], marker)])

    if head == "読み込む" and separated_head:
        if any(t.text == "," for t in sig):
            fail("読み込む は v0.1 では一度に 1 モジュールのみ指定できます")
        aliases = alias_positions(sig)
        if len(aliases) > 1:
            fail("読み込む の別名指定（として / と名付ける / as）は一度だけ指定してください")
        edits = [edit(first, "import")]
        if aliases:
            k = aliases[0]
            if k < 2 or k != len(sig) - 2 or not spaced(sig[k - 1], sig[k]) or not spaced(sig[k], sig[k + 1]):
                fail("読み込む の別名指定は 'モジュール として 名前' にしてください")
            edits.append(edit(sig[k], "as"))
        return make(edits)

    if len(sig) >= 2 and last.is_name("を戻す") and spaced(sig[-2], last):
        if head == "戻す" and separated_head:
            fail("戻す と 'を戻す' を同じ文で混在できません")
        return make([_Edit(offset(first.token.start), offset(first.token.start), "return "),
                     cut(sig[-2], last)])

    simple = {"戻す": "return", "抜ける": "break", "続ける": "continue",
              "何もしない": "pass", "投げる": "raise", "確認する": "assert"}
    if head in simple:
        if head in ("抜ける", "続ける", "何もしない") and len(sig) != 1:
            return []
        if len(sig) > 1 and not separated_head:
            return []
        return make([edit(first, simple[head])])
    return []


def transpile(source: str, *, filename: str = "<jpy>") -> str:
    """Translate without execution; callers validate the whole Python module.

    Syntax/semantic context restrictions are validated by compile_file/run_file.
    This low-level function may return Python rejected in that final validation.
    """
    if not isinstance(source, str):
        raise TypeError("source must be str")
    source = source.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    lines = io.StringIO(source).readlines()
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line))
    encoding, _ = tokenize.detect_encoding(io.BytesIO(source.encode("utf-8")).readline)
    if encoding.lower().replace("_", "-") not in ("utf-8", "utf-8-sig"):
        raise SyntaxError(f"JPy v0.1 は UTF-8 のみ対応しています: {encoding}",
                          (filename, 1, 1, lines[0] if lines else ""))
    statements, current = [], []
    fdepth, fstart = 0, None
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            # A complete f-string is opaque even on CPython versions that expose
            # its expression tokens separately. Never translate literal parts.
            if token.type == getattr(tokenize, "FSTRING_START", -1):
                if not fdepth:
                    fstart = token
                fdepth += 1
                continue
            if fdepth:
                if token.type == getattr(tokenize, "FSTRING_END", -1):
                    fdepth -= 1
                    if not fdepth:
                        a = starts[fstart.start[0] - 1] + fstart.start[1]
                        b = starts[token.end[0] - 1] + token.end[1]
                        current.append(tokenize.TokenInfo(tokenize.STRING, source[a:b],
                                                          fstart.start, token.end, fstart.line))
                continue
            if token.type in (tokenize.INDENT, tokenize.DEDENT, tokenize.NL, tokenize.COMMENT):
                continue
            if token.type in (tokenize.NEWLINE, tokenize.ENDMARKER):
                if current:
                    statements.append(current)
                    current = []
            else:
                current.append(token)
    except tokenize.TokenError as exc:
        row, col = exc.args[1]
        raise SyntaxError(str(exc.args[0]), (filename, row, col + 1,
                          lines[row - 1] if row <= len(lines) else "")) from exc
    except IndentationError as exc:
        exc.filename = filename
        raise
    edits = []
    for statement in statements:
        edits.extend(_translate_statement(statement, source, lines,starts, filename))
    previous = len(source)
    for start, end, replacement in sorted(edits, reverse=True):
        if end > previous:
            raise AssertionError("Overlapping JPy token edits")
        source = source[:start] + replacement + source[end:]
        previous = start
    return source
