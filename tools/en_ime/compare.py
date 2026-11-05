"""CentaurIME English（AI なし）を、よく使われる仕組みと同じ文で比べる。

  python tools/en_ime/compare.py --tatoeba eng_sentences.tsv.bz2 --out compare.txt

比べる相手:
  区切り: wordsegment（Google の語の数の表）、symspellpy の word_segmentation
  直し:   Hunspell（LibreOffice・Firefox などの綴りの確かめ）、pyspellchecker（Norvig 式）、symspellpy
          AOSP LatinIME（Android 標準キーボードの C++ 本体、Apache-2.0。--latinime のとき。表は AOSP のものと Tatoeba のもの）
文は measure.py の確かめの側（重み選びに使わない後半）。区切りは ' を含むまとまりを除く（相手が ' を扱えないため）。
時間は作りが違う（C と Python）ので参考だけ。
"""
import argparse
import random
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from en_model import Model, words_of  # noqa: E402
from measure import CHUNK, fix_score, read, unit  # noqa: E402


class Ours:
    name = "CentaurIME"

    def __init__(self, m):
        self.m, self.uni = m, m.uni

    def segment(self, text):
        return self.m.segment(text)

    def corrections(self, w, prev="<s>", limit=3):
        return self.m.corrections(w, prev, limit)


class WordSegment:
    name = "wordsegment"

    def __init__(self):
        import wordsegment
        wordsegment.load()
        self.f = wordsegment.segment

    def segment(self, text):
        return self.f(text)


class SymSpell:
    name = "symspellpy"

    def __init__(self, uni):
        import importlib.resources
        from symspellpy import SymSpell as S, Verbosity
        self.V, self.uni = Verbosity, uni
        self.s = S(max_dictionary_edit_distance=2, prefix_length=7)
        d = importlib.resources.files("symspellpy") / "frequency_dictionary_en_82_765.txt"
        b = importlib.resources.files("symspellpy") / "frequency_bigramdictionary_en_243_342.txt"
        self.s.load_dictionary(str(d), term_index=0, count_index=1)
        self.s.load_bigram_dictionary(str(b), term_index=0, count_index=2)

    def segment(self, text):
        return self.s.word_segmentation(text).corrected_string.split()

    def corrections(self, w, prev="<s>", limit=3):
        r = self.s.lookup(w, self.V.CLOSEST, max_edit_distance=2, include_unknown=False)
        return [x.term for x in r][:limit] or [w]


class PySpell:
    name = "pyspellchecker"

    def __init__(self, uni):
        from spellchecker import SpellChecker
        self.s, self.uni = SpellChecker(), uni

    def corrections(self, w, prev="<s>", limit=3):
        if w in self.s:
            return [w]
        c = self.s.candidates(w) or set()
        return sorted(c, key=lambda x: -self.s.word_usage_frequency(x))[:limit] or [w]


class Hunspell:
    name = "Hunspell"

    def __init__(self, uni):
        self.uni = uni
        self.p = subprocess.Popen(["hunspell", "-a", "-d", "en_US"], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, text=True, bufsize=1)
        self.p.stdout.readline()  # 名乗りの行

    def corrections(self, w, prev="<s>", limit=3):
        self.p.stdin.write("^" + w + "\n")
        self.p.stdin.flush()
        lines = []
        while True:
            l = self.p.stdout.readline().rstrip("\n")
            if l == "":
                break
            lines.append(l)
        r = lines[0] if lines else "*"
        if r[0] in "*+-":
            return [w]
        if r[0] == "&":
            sug = [x.strip().lower() for x in r.split(":", 1)[1].split(",")]
            return sug[:limit]
        return [w]


class LatinIME:
    """AOSP LatinIME（Android 標準キーボード、Apache-2.0）の C++ 本体。latinime/Harness.java を通して呼ぶ。"""

    def __init__(self, name, cmd, uni):
        self.name, self.uni = name, uni
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                                  encoding="utf-8", bufsize=1)

    def corrections(self, w, prev="<s>", limit=3):
        self.p.stdin.write(f"{'' if prev == '<s>' else prev}\t{w}\n")
        self.p.stdin.flush()
        raw = self.p.stdout.readline().rstrip("\n")
        self.shown = getattr(self, "shown", 0) + 1
        if self.shown <= 15:  # 答えの形を記録に残す（調べる用）
            print(f"  {self.name} 問い {prev!r} {w!r} → {raw!r}", file=sys.stderr)
        c = [x for x in raw.split("\t") if x]
        return [x.lower() for x in c][:limit] or [w]


def entries_from_aosp(path, out):
    """AOSP の語の表（*.combined.gz）を Harness の形に直す。"""
    import gzip
    n = 0
    with gzip.open(path, "rt", encoding="utf-8") as f, open(out, "w", encoding="utf-8") as o:
        word = None
        for line in f:
            kv = dict(x.split("=", 1) for x in line.strip().split(",") if "=" in x)
            if "word" in kv and "f" in kv:
                word = kv["word"]
                o.write(f"u\t{word}\t{kv['f']}\n")
                n += 1
            elif "bigram" in kv and "f" in kv and word:
                o.write(f"b\t{word}\t{kv['bigram']}\t{kv['f']}\n")
    return n


def entries_from_model(m, out):
    """CentaurIME と同じ Tatoeba の表を、AOSP の 0〜255 の目盛り（2 倍ごとに 8 ほど）に直す。"""
    import math
    top = max(m.uni.values())
    with open(out, "w", encoding="utf-8") as o:
        for w, c in m.uni.items():
            o.write(f"u\t{w}\t{max(1, min(255, round(222 + 8 * math.log2(c / top))))}\n")
        for (a, b), c in m.bi.items():
            if c >= 2 and a != "<s>":
                p = c / max(m.left[a], 1)
                o.write(f"b\t{a}\t{b}\t{max(1, min(255, round(222 + 8 * math.log2(p))))}\n")


def segment_cmp(sys_, test):
    ok = n = 0
    t = 0.0
    for s in test:
        for ch in CHUNK.findall(s):
            ws = words_of(ch)
            if len(ws) < 2 or any("'" in w for w in ws):
                continue
            t0 = time.perf_counter()
            got = [g.lower() for g in sys_.segment("".join(ws))]
            t += time.perf_counter() - t0
            n += 1
            ok += got == ws
    return f"区切り {sys_.name}: まとまり {ok}/{n}（{ok / max(n, 1):.1%}）、1 まとまり平均 {t / max(n, 1) * 1000:.2f} ミリ秒"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tatoeba", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=20261105)
    ap.add_argument("--test", type=int, default=3000)
    ap.add_argument("--latinime", nargs=3, metavar=("SO", "CLASSPATH", "WORDLIST"),
                    help="AOSP LatinIME の本体（.so）、Harness のクラスの置き場、AOSP の語の表（*.combined.gz）")
    args = ap.parse_args()

    train, test = [], []
    for sid, text in read(args.tatoeba):
        (test if unit(args.seed, sid) < 0.1 else train).append(text)
    rng = random.Random(args.seed)
    rng.shuffle(test)
    verify = test[args.test:2 * args.test]  # measure.py の確かめの側と同じ文
    m = Model(train)
    m.word_penalty, m.oov_char, m.typo_weight = 2.0, 2.0, 8.0
    ours = Ours(m)
    out = [f"確かめの文 {len(verify)}（CentaurIME は重み 1 語 2.0・表に無い字 2.0・直し 8.0）"]
    for s in (ours, WordSegment(), SymSpell(m.uni)):
        out.append(segment_cmp(s, verify))
        print(out[-1], flush=True)
    # 直しの打ち間違いは同じ種から作るので、どの相手も同じ間違いで比べる。
    # 「別の正しい語になる間違い」を除く基準は全員 CentaurIME の語の表にそろえる。
    fixers = [ours, Hunspell(m.uni), PySpell(m.uni), SymSpell(m.uni)]
    if args.latinime:
        # 同じ本体を、AOSP の英語の表と、CentaurIME と同じ Tatoeba の表の両方で（仕組みの差と表の差を分ける）
        so, cp, aosp = args.latinime
        entries_from_aosp(aosp, "latin-aosp.tsv")
        entries_from_model(m, "latin-tatoeba.tsv")
        for label, f in (("LatinIME（AOSP の表）", "latin-aosp.tsv"), ("LatinIME（Tatoeba の表）", "latin-tatoeba.tsv")):
            fixers.append(LatinIME(label, ["java", "-cp", cp, "Harness", so, f], m.uni))
    for s in fixers:
        r = fix_score(s, verify, args.seed, 0, s.name)
        out += r
        print(r[0], flush=True)
    Path(args.out).write_text("\n".join(out) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
