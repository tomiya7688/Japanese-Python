# 配布ガイド: PyInstaller / Nuitka

この文書は **JPy v0.1 の変換済み `.py` を配布ツールに渡すための手順**です。言語仕様の規範は [spec/JPy-v0.1.md](../spec/JPy-v0.1.md) です。

## 不変条件

- `jpy compile X.jpy -o X.py` は **通常の Python ソースへの変換のみ**であり、アプリケーションを実行しません。
- `jpy run X.jpy` は **元の `.jpy` を実行対象として CPython で実行**し、変換済み `.py` を一切出力しません。
- PyInstaller / Nuitka は、**コンパイルモードで生成した `.py`** を入力にします。配布のために `run` を実行・置換・ラップしません。
- 結果として配布アプリは JPy に依存しません（アプリケーション自身が明示的に JPy を使う場合を除く）。

## スモークテスト手順

```bash
python -m pip install -e .
python -m pip install pyinstaller
jpy compile examples/hello.jpy -o build/hello.py
python build/hello.py
python -m PyInstaller --onefile --name jpy-hello build/hello.py
# 生成された dist/jpy-hello（Windows では .exe）を起動して出力を確認
```

Nuitka の場合:

```bash
python -m pip install nuitka
jpy compile examples/hello.jpy -o build/hello.py --force
python -m nuitka --mode=standalone build/hello.py
# standalone で成功後、必要に応じて onefile
python -m nuitka --mode=onefile build/hello.py
```

PyInstaller 公式: https://pyinstaller.org/en/stable/usage.html  
Nuitka 公式: https://nuitka.net/user-documentation/use-cases.html

## マルチモジュール・リソース

`.jpy` ファイルは v0.1 では Python の import hook では認識されません。`main.jpy` が `module.jpy` に依存する場合、`main.py` と `module.py` の **両方を**変換し、元の Python のモジュール配置・パッケージ構造を保ってください。変換済みの `.py` は JPy のない Python 環境で先に動作確認します。

相対パス、画像などのデータファイル、隠れた動的 import、OS 固有のライブラリは、それぞれ PyInstaller / Nuitka の公式ガイドに沿って設定が必要です。配布ツールがリソースパスや `__file__` を扱う方法は通常の Python 配布アプリと同じ制約を受けます。

**v0.1 で保証する範囲:** 変換済み `.py` が JPy ランタイム無しで CPython で実行・構文解析できること。特定のパッケージャーの環境依存ビルド、OS をまたいだクロスコンパイル、暗黙の `.jpy` 依存変換までは保証しません。
