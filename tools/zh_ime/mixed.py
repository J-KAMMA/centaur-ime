"""中国語の拼音の中の英単語を残す（日本語版の「英単語を切り替えずに残す」を中国語へ移す）。AI なしの決まりと計測。

  python3 tools/zh_ime/mixed.py --tatoeba cmn_sentences.tsv.bz2 --wiki zh.parquet --eng eng_sentences.tsv.bz2 --out out

決まり: 打った英字（声調なしの全拼）を、拼音の音節と英単語に分ける一番安い分け方を探す。
  拼音の音節 1 つ = 1、英単語（英語の語の一覧）1 つ = 1、ただし拼音としても全部読める英単語（women = wo men、
  china = chi na）は +3（拼音を優先）。一覧に無く拼音としても読めない英字の並び（名前）は 1 字 0.7＋2。
英語の語の一覧: Tatoeba の英語の文に 3 回以上出る 3 字以上の語と、ブランド名（tools/data の 2 つの表）。
試験:
  英単語まじり: 中国語ウィキペディア（CC BY-SA 4.0）の、漢字の間に英単語（3 字以上）がある句（句読点で切る）。
    漢字は拼音に、英単語は小文字にして続けて打った形を作り、英単語を英語として取れた割合と、句が全部合った割合。
  ふつうの中国語: Tatoeba の確かめの枠（measure.py と同じ 0.8 以上）の句。誤って英語を取った句の割合。
"""
import argparse
import bz2
import collections
import re
import sys
from pathlib import Path

from pypinyin import Style, lazy_pinyin

sys.path.insert(0, str(Path(__file__).resolve().parent))
import measure as Z  # noqa: E402

HAN = re.compile(r"[一-鿿]")
MIXED = re.compile(r"^[一-鿿A-Za-z ]+$")
LATIN = re.compile(r"[A-Za-z]+")


def pinyin_set():
    s = set()
    for code in range(0x4E00, 0xA000):
        for r in lazy_pinyin(chr(code), style=Style.NORMAL, errors="ignore"):
            if r.isascii() and r.isalpha():
                s.add(r)
    return s


class Splitter:
    def __init__(self, syllables, english):
        self.syl = syllables
        self.eng = english
        self.max_syl = max(map(len, syllables))

    def is_pinyin(self, s):
        ok = [True] + [False] * len(s)
        for i in range(len(s)):
            if ok[i]:
                for j in range(i + 1, min(len(s), i + self.max_syl) + 1):
                    if s[i:j] in self.syl:
                        ok[j] = True
        return ok[len(s)]

    def split(self, s):
        """[(部分, 英語か)] を返す。"""
        n = len(s)
        best = [None] * (n + 1)
        best[0] = (0.0, None)
        for i in range(n):
            if best[i] is None:
                continue
            c0 = best[i][0]
            for j in range(i + 1, min(n, i + 30) + 1):
                w = s[i:j]
                opts = []
                if j - i <= self.max_syl and w in self.syl:
                    opts.append((1.0, False))
                if j - i >= 3 and w in self.eng:
                    opts.append((1.0 + (3.0 if self.is_pinyin(w) else 0.0), True))
                elif j - i >= 3 and not self.is_pinyin(w):
                    opts.append((2.0 + 0.7 * (j - i), True))
                for cost, eng in opts:
                    if best[j] is None or c0 + cost < best[j][0]:
                        best[j] = (c0 + cost, (i, eng))
        if best[n] is None:
            return [(s, True)]
        out, j = [], n
        while j > 0:
            i, eng = best[j][1]
            out.append((s[i:j], eng))
            j = i
        out.reverse()
        # となりあう拼音の音節はまとめる
        merged = []
        for w, eng in out:
            if merged and not eng and not merged[-1][1]:
                merged[-1] = (merged[-1][0] + w, False)
            else:
                merged.append((w, eng))
        return merged


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tatoeba", required=True)
    ap.add_argument("--wiki", required=True)
    ap.add_argument("--eng", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--test", type=int, default=3000)
    a = ap.parse_args()

    syl = pinyin_set()
    count = collections.Counter()
    with bz2.open(a.eng, "rt", encoding="utf-8") as f:
        for line in f:
            c = line.rstrip("\n").split("\t")
            if len(c) >= 3 and c[1] == "eng":
                count.update(w.lower() for w in LATIN.findall(c[2]))
    english = {w for w, n in count.items() if n >= 3 and len(w) >= 3}
    data = Path(__file__).resolve().parents[1] / "data"
    for name in ("brand-casing-wikidata.tsv", "brand-casing.tsv"):
        p = data / name
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                c = line.split("\t")
                if len(c) >= 2 and not line.startswith("#") and re.fullmatch(r"[a-z]{3,}", c[0]):
                    english.add(c[0])
    sp = Splitter(syl, english)
    out = [f"拼音の音節 {len(syl)}、英語の語 {len(english)}"]

    # 英単語まじりの句（ウィキ）
    import pyarrow.parquet as pq
    mixed = []
    for text in pq.read_table(a.wiki, columns=["text"]).column("text").to_pylist():
        for s in re.split(r"[，。！？；：、（）《》“”\n,.;:!?()]", text):
            s = s.strip()
            if 4 <= len(s) <= 40 and MIXED.match(s) and HAN.search(s) and re.search(r"[A-Za-z]{3,}", s) \
                    and all(len(w) >= 3 for w in LATIN.findall(s)):
                mixed.append(s)
        if len(mixed) >= a.test:
            break
    ok_word = n_word = ok_chunk = 0
    bad = []
    for s in mixed:
        typed, gold = "", []
        for m in re.finditer(r"[A-Za-z]+|[一-鿿]+", s):
            t = m.group()
            if HAN.match(t):
                typed += "".join(Z.syllables(t) or [])
            else:
                gold.append(t.lower())
                typed += t.lower()
        got = [w for w, eng in sp.split(typed) if eng]
        n_word += len(gold)
        ok_word += sum(1 for g in gold if g in got)
        ok_chunk += got == gold
        if got != gold and len(bad) < 25:
            bad.append(f"  {s}  → 英語 {got}（正しくは {gold}）")
    out.append(f"英単語まじりの句 {len(mixed)}: 英単語を英語として取れた {ok_word / max(n_word, 1):.1%}"
               f"（{ok_word}/{n_word}）、句が全部合った {ok_chunk / max(len(mixed), 1):.1%}")
    out += bad

    # ふつうの中国語の句（Tatoeba の確かめの枠）
    pure = []
    for sid, text in Z.read_tatoeba(a.tatoeba):
        if Z.stable_unit(20261017, sid) < 0.8:
            continue
        for c in Z.HAN.findall(text):
            py = Z.syllables(c)
            if py:
                pure.append((c, "".join(py)))
        if len(pure) >= a.test:
            break
    wrong = [(c, [w for w, e in sp.split(t) if e]) for c, t in pure]
    wrong = [(c, w) for c, w in wrong if w]
    out.append(f"ふつうの中国語の句 {len(pure)}: 誤って英語を取った {len(wrong) / max(len(pure), 1):.2%}（{len(wrong)}）")
    out += [f"  {c} → 英語 {w}" for c, w in wrong[:25]]
    Path(a.out).mkdir(parents=True, exist_ok=True)
    (Path(a.out) / "zh-mixed.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(l for l in out if not l.startswith("  ")))


if __name__ == "__main__":
    main()
