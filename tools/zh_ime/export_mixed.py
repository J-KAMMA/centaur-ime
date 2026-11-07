"""Centaur IME 中国語の「拼音の中の英単語を残す」表（zh-mixed.tsv）と、C++ と同じ答えになるかの確かめの材料を書く。

  python tools/zh_ime/export_mixed.py --tatoeba cmn_sentences.tsv.bz2 --eng eng_sentences.tsv.bz2 \
      --out zh-mixed.tsv --check zh-mixed-check.tsv

表の行: 「S<TAB>拼音の音節」（pypinyin で読んだ漢字の読み全部）と「E<TAB>英語の語」（mixed.py と同じ: Tatoeba の英語の文に
20 回以上出る 4 字以上の語と、ブランド名の表の 3 字以上の英小文字の語）。
--check: 「打った英字<TAB>分け方（英語の部分は E:語、拼音は P:音節の並び、| で区切る）」を、Tatoeba の中国語の句と、
その音節の間に英語の語を入れた形から書く（native/centaur_core/zh_mixed_cli で同じ答えになるかを見る）。
"""
import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import measure as Z  # noqa: E402
from mixed import LATIN, Splitter, pinyin_set  # noqa: E402

import bz2  # noqa: E402
import collections  # noqa: E402
import re  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tatoeba", required=True)
    ap.add_argument("--eng", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--check")
    ap.add_argument("--n", type=int, default=3000)
    a = ap.parse_args()

    syl = pinyin_set()
    count = collections.Counter()
    with bz2.open(a.eng, "rt", encoding="utf-8") as f:
        for line in f:
            c = line.rstrip("\n").split("\t")
            if len(c) >= 3 and c[1] == "eng":
                count.update(w.lower() for w in LATIN.findall(c[2]))
    english = {w for w, n in count.items() if n >= 20 and len(w) >= 4}
    data = Path(__file__).resolve().parents[1] / "data"
    for name in ("brand-casing-wikidata.tsv", "brand-casing.tsv"):
        for line in (data / name).read_text(encoding="utf-8").splitlines():
            c = line.split("\t")
            if len(c) >= 2 and not line.startswith("#") and re.fullmatch(r"[a-z]{3,}", c[0]):
                english.add(c[0])
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        f.write("".join(f"S\t{s}\n" for s in sorted(syl)))
        f.write("".join(f"E\t{w}\n" for w in sorted(english)))
    print(f"拼音の音節 {len(syl)}、英語の語 {len(english)}")

    if a.check:
        sp = Splitter(syl, english)
        rng = random.Random(20261107)
        words = sorted(english)
        inputs = []
        for _, text in Z.read_tatoeba(a.tatoeba):
            for c in Z.HAN.findall(text):
                py = Z.syllables(c)
                if not py:
                    continue
                inputs.append("".join(py))
                k = rng.randrange(len(py) + 1)
                inputs.append("".join(py[:k]) + rng.choice(words) + "".join(py[k:]))
            if len(inputs) >= a.n:
                break
        with open(a.check, "w", encoding="utf-8", newline="\n") as f:
            for s in inputs:
                parts = "|".join(("E:" if e else "P:") + w for w, e in sp.split(s))
                f.write(f"{s}\t{parts}\n")
        print(f"確かめの材料 {len(inputs)}")


if __name__ == "__main__":
    main()
