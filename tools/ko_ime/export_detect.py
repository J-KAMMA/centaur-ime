"""Centaur IME 韓国語の見分けの表（ko-detect.tsv）と、C++ と同じ答えになるかの確かめの材料を書く。

  python3 tools/ko_ime/export_detect.py --tatoeba kor_sentences.tsv.bz2 --wiki ko.parquet --eng eng_sentences.tsv.bz2 \
      --out ko-detect.tsv --check check.tsv

表の行: 「K<TAB>韓国語の語」（Tatoeba の韓国語の文と韓国語ウィキペディアに 2 回以上出る語）と
「E<TAB>英語の語」（Tatoeba の英語の文に 3 回以上出る語）。決まりは measure.py の looks_korean・brand_of と同じで、
measure.py の表づくりの文（試験の文を除く）ではなく、配る表なので全部の文を使う。
--check: 「キー<TAB>韓国語の語の答え<TAB>ブランド名の答え」を、韓国語の語のキー・英語の語・ブランド名から書く
（native/centaur_core/ko_detect_cli で同じ答えになるかを見る）。
材料: Tatoeba（CC BY 2.0 FR）、韓国語ウィキペディア（CC BY-SA 4.0）。
"""
import argparse
import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hangul import compose, is_syllable, to_keys  # noqa: E402
from measure import KO_LINE, read_tatoeba, read_wiki  # noqa: E402

STRIP = ",.?!'\"()"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tatoeba", required=True)
    ap.add_argument("--wiki")
    ap.add_argument("--eng", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--check")
    ap.add_argument("--wiki-limit", type=int, default=120000)
    a = ap.parse_args()

    ko = collections.Counter()
    for _, s in read_tatoeba(a.tatoeba, "kor"):
        if KO_LINE.match(s):
            ko.update(e.strip(STRIP) for e in s.split())
    if a.wiki:
        for _, s in read_wiki(a.wiki, a.wiki_limit):
            ko.update(e.strip(STRIP) for e in s.split())
    en = collections.Counter()
    for _, s in read_tatoeba(a.eng, "eng"):
        en.update(re.findall(r"[a-z]+", s.lower()))
    korean = sorted(w for w, n in ko.items() if n >= 2 and w and all(map(is_syllable, w)))
    english = sorted(w for w, n in en.items() if n >= 3)
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        f.write("".join(f"K\t{w}\n" for w in korean))
        f.write("".join(f"E\t{w}\n" for w in english))
    print(f"韓国語の語 {len(korean)}、英語の語 {len(english)}")

    if a.check:
        kset, eset = set(korean), set(english)
        data = Path(__file__).resolve().parents[1] / "data"
        brands = {}
        for name in ("brand-casing-wikidata.tsv", "brand-casing.tsv"):
            for line in (data / name).read_text(encoding="utf-8").splitlines():
                p = line.split("\t")
                if len(p) >= 2 and not line.startswith("#") and p[1] != "-" and re.fullmatch(r"[a-z]{3,}", p[0]):
                    brands[p[0]] = p[1]

        def is_ko(keys):
            k = compose(keys)
            return bool(k) and all(map(is_syllable, k)) and k in kset

        def korean_of(keys):
            return compose(keys) if keys and keys.lower() not in eset and is_ko(keys) else ""

        def brand_of(keys):
            b = brands.get(keys.lower(), "")
            return "" if not b or is_ko(keys) else b

        keys = [to_keys(w) for w in korean[::20]] + english[::5] + sorted(brands)[::3]
        keys += [k.lower() for k in keys[:2000]]  # Shift を打ち忘れた形
        with open(a.check, "w", encoding="utf-8", newline="\n") as f:
            for k in keys:
                if k and "\t" not in k:
                    f.write(f"{k}\t{korean_of(k)}\t{brand_of(k)}\n")
        print(f"確かめの材料 {len(keys)}")


if __name__ == "__main__":
    main()
