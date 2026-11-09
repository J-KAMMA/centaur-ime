"""辞書の中の「その漢字の普段の読みではない読み」を洗い出す（はした → 端 のような語）。

使い方: python tools/find_rare_readings.py <mozc/src/data/dictionary_oss> <Unihan_Readings.txt> <出力.tsv>

1 字の漢字の語（表記が漢字 1 字、または漢字 1 字＋送りがな）で、読みが Unihan の
kJapaneseKun / kJapaneseOn のどれにも合わないものを出す。人名・地名の品詞は除く。
出力は 費用の安い順（安いほど変換に出やすく、区切りを邪魔しやすい）。
列: 読み, 表記, 費用, 品詞, その字の Unihan の読み
"""
import re
import sys
from pathlib import Path

dict_dir, unihan, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])


def kata_to_hira(s):
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in s)


ROMA = {}
for kana, roma in [
    ("きゃ", "kya"), ("きゅ", "kyu"), ("きょ", "kyo"), ("しゃ", "sha"), ("しゅ", "shu"), ("しょ", "sho"),
    ("ちゃ", "cha"), ("ちゅ", "chu"), ("ちょ", "cho"), ("にゃ", "nya"), ("にゅ", "nyu"), ("にょ", "nyo"),
    ("ひゃ", "hya"), ("ひゅ", "hyu"), ("ひょ", "hyo"), ("みゃ", "mya"), ("みゅ", "myu"), ("みょ", "myo"),
    ("りゃ", "rya"), ("りゅ", "ryu"), ("りょ", "ryo"), ("ぎゃ", "gya"), ("ぎゅ", "gyu"), ("ぎょ", "gyo"),
    ("じゃ", "ja"), ("じゅ", "ju"), ("じょ", "jo"), ("びゃ", "bya"), ("びゅ", "byu"), ("びょ", "byo"),
    ("ぴゃ", "pya"), ("ぴゅ", "pyu"), ("ぴょ", "pyo"),
    ("か", "ka"), ("き", "ki"), ("く", "ku"), ("け", "ke"), ("こ", "ko"), ("さ", "sa"), ("し", "shi"),
    ("す", "su"), ("せ", "se"), ("そ", "so"), ("た", "ta"), ("ち", "chi"), ("つ", "tsu"), ("て", "te"),
    ("と", "to"), ("な", "na"), ("に", "ni"), ("ぬ", "nu"), ("ね", "ne"), ("の", "no"), ("は", "ha"),
    ("ひ", "hi"), ("ふ", "fu"), ("へ", "he"), ("ほ", "ho"), ("ま", "ma"), ("み", "mi"), ("む", "mu"),
    ("め", "me"), ("も", "mo"), ("や", "ya"), ("ゆ", "yu"), ("よ", "yo"), ("ら", "ra"), ("り", "ri"),
    ("る", "ru"), ("れ", "re"), ("ろ", "ro"), ("わ", "wa"), ("を", "wo"), ("ん", "n"), ("が", "ga"),
    ("ぎ", "gi"), ("ぐ", "gu"), ("げ", "ge"), ("ご", "go"), ("ざ", "za"), ("じ", "ji"), ("ず", "zu"),
    ("ぜ", "ze"), ("ぞ", "zo"), ("だ", "da"), ("ぢ", "ji"), ("づ", "zu"), ("で", "de"), ("ど", "do"),
    ("ば", "ba"), ("び", "bi"), ("ぶ", "bu"), ("べ", "be"), ("ぼ", "bo"), ("ぱ", "pa"), ("ぴ", "pi"),
    ("ぷ", "pu"), ("ぺ", "pe"), ("ぽ", "po"), ("あ", "a"), ("い", "i"), ("う", "u"), ("え", "e"), ("お", "o"),
]:
    ROMA.setdefault(roma, kana)


def roma_to_hira(s):
    s = s.lower()
    out, i = "", 0
    while i < len(s):
        if i + 1 < len(s) and s[i] == s[i + 1] and s[i] not in "aeioun":
            out += "っ"
            i += 1
            continue
        for n in (3, 2, 1):
            if s[i:i + n] in ROMA:
                out += ROMA[s[i:i + n]]
                i += n
                break
        else:
            i += 1
    return out


readings = {}
for line in unihan.read_text(encoding="utf-8").splitlines():
    if line.startswith("#") or not line:
        continue
    code, field, value = line.split("\t")
    if field not in ("kJapaneseKun", "kJapaneseOn"):
        continue
    ch = chr(int(code[2:], 16))
    rs = readings.setdefault(ch, set())
    for r in value.split():
        r = r.split("-")[0]
        h = roma_to_hira(r) if r.isascii() else kata_to_hira(r)
        rs.add(h)
        # 連濁・促音化（ひと → びと、がく → がっ）も普段の読みとして数える
        if h:
            voiced = {"か": "が", "き": "ぎ", "く": "ぐ", "け": "げ", "こ": "ご", "さ": "ざ", "し": "じ", "す": "ず",
                      "せ": "ぜ", "そ": "ぞ", "た": "だ", "ち": "ぢ", "つ": "づ", "て": "で", "と": "ど", "は": "ば",
                      "ひ": "び", "ふ": "ぶ", "へ": "べ", "ほ": "ぼ"}
            if h[0] in voiced:
                rs.add(voiced[h[0]] + h[1:])
            pm = {"は": "ぱ", "ひ": "ぴ", "ふ": "ぷ", "へ": "ぺ", "ほ": "ぽ"}
            if h[0] in pm:
                rs.add(pm[h[0]] + h[1:])
            if len(h) >= 2 and h[-1] in "くきつち":
                rs.add(h[:-1] + "っ")

pos = {}
id_def = dict_dir / "id.def"
if id_def.exists():
    for line in id_def.read_text(encoding="utf-8").splitlines():
        i, name = line.split(" ", 1)
        pos[i] = name

KANJI = re.compile(r"^([一-龥々])([ぁ-ゖ]*)$")
rows = []
for path in sorted(dict_dir.glob("dictionary*.txt")):
    for line in path.read_text(encoding="utf-8").splitlines():
        f = line.split("\t")
        if len(f) < 5:
            continue
        reading, lid, _, cost, surface = f[:5]
        m = KANJI.match(surface)
        if not m:
            continue
        p = pos.get(lid, lid)
        if "人名" in p or "地域" in p or "組織" in p or "固有名詞" in p:
            continue
        ch, okuri = m.groups()
        if okuri and not reading.endswith(okuri):
            continue
        stem = reading[: len(reading) - len(okuri)] if okuri else reading
        known = readings.get(ch)
        if not known:
            continue
        if stem in known:
            continue
        # 送りがなの一部を読みに含む書き方（行う: おこな）や、読みの頭だけ（端: は）は普段の読みとする
        if any(k.startswith(stem) or stem.startswith(k) and len(stem) - len(k) <= 1 and okuri for k in known):
            continue
        rows.append((int(cost), reading, surface, p, " ".join(sorted(known))))

rows.sort()
with out.open("w", encoding="utf-8") as w:
    w.write("# 読み\t表記\t費用\t品詞\tUnihan の読み\n")
    for cost, reading, surface, p, known in rows:
        w.write(f"{reading}\t{surface}\t{cost}\t{p}\t{known}\n")
print(f"{len(rows)} 語を書いた: {out}")
