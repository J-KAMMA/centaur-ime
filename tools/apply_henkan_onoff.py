"""変換キーで IME を入（「あ」）、無変換キーで切（「A」）にする（MS-IME 風の割り当て表 data/keymap/ms-ime.tsv）。

  python tools/apply_henkan_onoff.py <mozc/src>

tools/apply_jaen_integration.py から呼ばれる（data/keymap/ms-ime.tsv はほかの script が触らない）。

変えるのは、何も打っていないときの 2 行だけ:
  - IME が切のときの変換キー: 再変換 → 入（DirectInput Henkan IMEOn）
  - 入で何も打っていないときの無変換キー: カタカナ入力に切り替え → 切（Precomposition Muhenkan IMEOff）
入で何も打っていないときの変換キー（再変換）と、打っている途中・変換中の変換・無変換キー（変換、
ひらがな・カタカナの切り替え）は今のまま。変換キーを押せばいつでも「あ」、無変換キーを押せば打つ前なら
「A」になり、今どちらの状態かを気にせずに済む（BekiIME の割り当てに倣う）。
"""
import sys
from pathlib import Path

src = Path(sys.argv[1])
P = "data/keymap/ms-ime.tsv"
CHANGES = [
    ("DirectInput\tHenkan\tReconvert", "DirectInput\tHenkan\tIMEOn"),
    ("Precomposition\tMuhenkan\tCompositionModeSwitchKanaType", "Precomposition\tMuhenkan\tIMEOff"),
]

p = src / P
text = p.read_bytes().decode("utf-8")
newline = "\r\n" if "\r\n" in text else "\n"
lines = text.split(newline)
for old, new in CHANGES:
    hits = [i for i, line in enumerate(lines) if line == old]
    if len(hits) != 1:
        raise SystemExit(f"{P}: expected 1 line {old!r}, found {len(hits)}")
    lines[hits[0]] = new
p.write_bytes(newline.join(lines).encode("utf-8"))
