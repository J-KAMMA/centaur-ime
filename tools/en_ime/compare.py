"""CentaurIME English（AI なし）を、よく使われる仕組みと同じ文で比べる。

  python tools/en_ime/compare.py --tatoeba eng_sentences.tsv.bz2 --out compare.txt

比べる相手:
  区切り: wordsegment（Google の語の数の表）、symspellpy の word_segmentation
  直し:   Hunspell（LibreOffice・Firefox などの綴りの確かめ）、pyspellchecker（Norvig 式）、symspellpy
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
    for s in (ours, Hunspell(m.uni), PySpell(m.uni), SymSpell(m.uni)):
        r = fix_score(s, verify, args.seed, 0, s.name)
        out += r
        print(r[0], flush=True)
    Path(args.out).write_text("\n".join(out) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
