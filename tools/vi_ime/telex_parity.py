"""Telex の組み立ての確かめ。

  python3 tools/vi_ime/telex_parity.py <telex_cli> [vie_sentences.tsv.bz2]
1. C++（native/centaur_core/telex.cc）が Python（telex.py）と同じ答えを出すか: でたらめなキーの並び 30,000 個と境目。
2. 元に戻るか: ベトナム語の語を Telex のキーにして組み立て直し、元の語になる割合（Tatoeba の文があれば）。
   戻らない語は、声調の置き場の書き方の違い（hòa と hoà など）を別に数える。
一致しなければ終了の番号 1。
"""
import bz2
import collections
import random
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from telex import SPLIT, compose, to_telex  # noqa: E402

rng = random.Random(20261106)
keys = "aeiouyAEOdDwWsfrxjzqgnhtcmlpvkb  1,"
qs = ["".join(rng.choice(keys) for _ in range(rng.randint(1, 14))) for _ in range(30000)]
qs += ["tieengs vieetj", "Vieetj Nam", "nguwowif", "quar", "gif", "giuwax", "hoaf", "thuyr", "ddi hocj", "aaa", "ss",
       "chuyeenj", "khongz", "tranw", "VIEETJ", "", "w", "uow", "huowng"]
py = [compose(q) for q in qs]
p = subprocess.run([sys.argv[1]], input="".join(q + "\n" for q in qs), capture_output=True, text=True,
                   encoding="utf-8", check=True)
cc = p.stdout.split("\n")[: len(qs)]
diff = [(q, a, b) for q, a, b in zip(qs, py, cc) if a != b]
print(f"問い {len(qs)}、Python と C++ の違い {len(diff)}")
for d in diff[:15]:
    print("  違い", d)
print("例:", " / ".join(f"{q}→{a}" for q, a in zip(qs[-19:-4], py[-19:-4])))

if len(sys.argv) > 2:
    words = collections.Counter()
    with bz2.open(sys.argv[2], "rt", encoding="utf-8") as f:
        for line in f:
            c = line.rstrip("\n").split("\t")
            if len(c) >= 3 and c[1] == "vie":
                words.update(re.findall(r"[^\W\d_]+", unicodedata.normalize("NFC", c[2]).lower()))
    viet = {w: n for w, n in words.items() if all(ch.isascii() or ch in SPLIT or ch in "đ" for ch in w)}
    ok = style = 0
    bad = []
    for w, n in viet.items():
        got = compose(to_telex(w))
        if got == w:
            ok += n
            continue
        # 声調の置き場だけが違う（字から声調を外すと同じ）
        if unicodedata.normalize("NFD", got).replace("̀", "").replace("́", "").replace("̃", "") \
                .replace("̉", "").replace("̣", "") == unicodedata.normalize("NFD", w).replace("̀", "") \
                .replace("́", "").replace("̃", "").replace("̉", "").replace("̣", ""):
            style += n
        else:
            bad.append((n, w, to_telex(w), got))
    total = sum(viet.values())
    print(f"元に戻った語（出る回数で数える）{ok / total:.2%}、声調の置き場の書き方だけ違う {style / total:.2%}、"
          f"そのほか {(total - ok - style) / total:.2%}（語の種類 {len(viet)}）")
    for n, w, k, g in sorted(bad, reverse=True)[:15]:
        print(f"  {w}（{n} 回）キー {k} → {g}")
sys.exit(1 if diff else 0)
