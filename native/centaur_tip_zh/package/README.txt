Centaur IME Chinese（試用版）

拼音（全拼、声調なし）で簡体字の中国語を打つ入力方式です。
- 打った拼音は文字の欄に、候補はカーソルの下の小さな窓に出ます（1.你好  2.妳好 …）。
- 空白で一番の候補、数字で番号の候補、- と = でページ送り、Enter で打った英字のまま、Esc で取り消し。
- 記号は全角になります（，。）。
- Shift だけを押して離す、か Shift+Space で中国語と英語を切り替えます。
- パスワード欄、メールアドレス・URL の欄、ターミナル、リモートデスクトップなどでは英字のままです。

入れ方:   管理者の PowerShell で install.ps1
外し方:   管理者の PowerShell で uninstall.ps1
使い方:   設定 → 時刻と言語 → 言語と地域 → 中国語（簡体字、中国）→ キーボードの追加 → Centaur IME Chinese

変換は Rime（librime 1.17.0、https://github.com/rime/librime、BSD-3-Clause）を使っています。
辞書は万象拼音（rime_wanxiang、CC BY 4.0、https://github.com/amzxyz/rime_wanxiang）と語法の模型
（RIME-LMDG の wanxiang-lts-zh-hans.gram、CC BY 4.0）、共通の設定は rime-prelude（LGPL-3.0）と、
簡体字に直す OpenCC の表（Apache-2.0）です。
