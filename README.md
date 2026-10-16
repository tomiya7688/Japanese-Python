# Japanese-Python (JPy)

> **日本語で Python の基本構文を書ける言語仕様**。変換器は仕様を実装・検証するための補助ツールです。

JPy は Python の **式、ライブラリ、型注釈、インデント、実行意味論**をそのまま利用し、`if`・`def` などの文を日本語で書けるようにします。正式な条件分岐は `もし 条件 ならば:` / `それ以外でもし 条件 ならば:` / `それ以外:` で、元の Python の `if`・`elif`・`for` も使えます。語順変更は v0.1 では `条件 なら:`、`条件 の間:`、`式 を戻す`、範囲反復の構文に限定します。Python の代替実行環境や独自の型システムは作りません。

**`繰り返し i が 0 から 5 まで:` の終了値 5 は含みません（Python の `range(0, 5)` と同じ）。**

**最優先の成果物は [規範仕様書](spec/JPy-v0.1.md) です。** 実装と例が矛盾したら、仕様書を正として扱い、必要なら仕様の変更提案を行います。

```jpy
関数 判定(点数: int) -> str:
    もし 点数 >= 80 ならば:
        "優秀" を戻す
    それ以外でもし 点数 >= 60 ならば:
        "合格" を戻す
    それ以外:
        戻す "不合格"

各 点数 を [50, 80] から:
    print(判定(点数))

繰り返し i が 0 から 5 まで:
    print(i)  # 0, 1, 2, 3, 4

i = 0
i < 3 の間:
    print(i)
    i += 1
```

## 基本方針：2 つのコマンドは別物

| | `jpy compile` | `jpy run` |
|---|---|---|
| 用途 | **通常の `.py` ファイルを生成するだけ** | **`.jpy` を直接の実行対象として CPython で起動** |
| `.py` の書き出し | **する** | **しない**（メモリ内で構文を変換） |
| アプリケーションの実行 | **しない** | **する** |
| JPy ランタイム | 生成した `.py` に不要 | 参考ツールが実行開始時に必要 |
| PyInstaller / Nuitka | **生成した `.py` が入力** | バンドルの入力にはしない |

この 2 つの意味を混同したり、後から入れ替えたりしないことを **互換性上の不変条件**とします。

`run` は CPython に未変換の日本語構文を直接解釈させるわけではありません。`.jpy` を読み込んで**メモリ内だけで通常の Python 構文に直し、同じ CPython プロセスで `compile` / `exec`** します。`.py` を一時保存して呼び出す方式や、独自 VM による実行とは異なります。

## 導入・試用

Python 3.12 以上の CPython を使用します。

```bash
python -m pip install -e .

# 1. 変換のみ。デフォルト出力は build/hello.py
jpy compile examples/hello.jpy
python build/hello.py

# 出力先を指定（既存ファイルの上書きには --force）
jpy compile examples/hello.jpy -o examples/hello.py

# 2. .py を作らず元の .jpy を CPython で実行
jpy run examples/hello.jpy
python -m japanese_python run examples/hello.jpy
```

`jpy run main.jpy -- 引数1 引数2` とすればスクリプト引数が `sys.argv` に渡ります。双方のコマンドは `.jpy` だけを入力とします。

## PyInstaller / Nuitka で配布する

JPy 向けの特殊なランタイム・プラグインは不要です。**先に `compile` し、出来上がった普通の `.py` をパッケージャーに渡してください。** `run` をバンドル用の入口として流用しません。

```bash
jpy compile examples/hello.jpy -o build/hello.py

# PyInstaller: one-file 実行ファイル
python -m PyInstaller --onefile --name hello build/hello.py

# Nuitka: standalone / onefile（環境により C コンパイラが必要）
python -m nuitka --mode=standalone build/hello.py
python -m nuitka --mode=onefile build/hello.py
```

PyInstaller と Nuitka は別途インストールする必要があります。既存ファイルがある場合は `jpy compile ... --force` で再生成してください。**上のコマンドは連携方法であり、両パッケージャーの全環境・全依存へのビルド成功を保証するものではありません。** スクリプトの依存する `.jpy` モジュールは、v0.1 では事前に `.py` に変換して配置する必要があります。詳しくは [配布ガイド](docs/packaging.md) を参照してください。

## 仕様・開発

- [JPy v0.1 言語仕様（規範）](spec/JPy-v0.1.md)
- [PyInstaller / Nuitka 配布ガイド](docs/packaging.md)
- [例](examples/hello.jpy)
- [仕様に基づくテスト](tests/)

```bash
python -m unittest discover -s tests -v
```

v0.1 は **仕様のドラフトと最小参考実装**です。`with`・`async`・内包表記などの標準 Python 構文はそのまま利用できますが、それらの日本語表記は未定義です。`.jpy` の直接 `import`、独自の型検査、自然文の自由解釈は提供しません。

## ライセンス

ライセンスは未決定です。採用するライセンスの相談・決定後に `LICENSE` を追加します。ライセンス決定前に利用・再配布条件を推測しないでください。
