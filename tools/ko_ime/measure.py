"""Centaur IME 韓国語（AI なし）の計測: 分かち書き（띄어쓰기）の直しと、英語モードのまま打った語の見分け。

  python3 tools/ko_ime/measure.py --tatoeba kor_sentences.tsv.bz2 --wiki ko.parquet --eng eng_sentences.tsv.bz2 --out out

材料: Tatoeba の韓国語の文（CC BY 2.0 FR）と、韓国語ウィキペディア（CC BY-SA 4.0）の 1 区切り。
文の番号（ウィキは記事の番号）の SHA-256 で 1 割を試験、残りを表づくりに使う。

分かち書き: 字と字の間ごとに「ここに空白があるか」を、左右の 1〜3 字の並びで数えた割合で決める（長い並びほど優先し、
  数の少ない並びは短い並びへ下がる）。空白を全部抜いた文を直し、空白の当たり（適合率・再現率）、語（어절）が
  丸ごと合った割合、文が丸ごと合った割合を出す。比べる相手は kiwipiepy の space（入っていれば）。
英語モードの見分け: 試験の韓国語の語を 2 ボル式のキーの並びにしたもの（例 dkssud）を「直すべき」、
  Tatoeba の英語の語を「直してはいけない」として、見分けの当たりを数える。
"""
import argparse
import bz2
import collections
import hashlib
import math
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hangul import compose, is_syllable, to_keys  # noqa: E402

CTX = [(3, 3), (2, 3), (3, 2), (2, 2), (1, 2), (2, 1), (1, 1), (1, 0), (0, 1)]
KO_LINE = re.compile(r"^[가-힣0-9 ,.?!'\"·~()-]+$")


def unit(seed, key):
    return int.from_bytes(hashlib.sha256(f"{seed}\t{key}".encode()).digest()[:8], "big") / 2**64


def read_tatoeba(path, lang):
    with bz2.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            c = line.rstrip("\n").split("\t")
            if len(c) >= 3 and c[1] == lang:
                yield c[0], c[2].strip()


def read_wiki(path, limit):
    import pyarrow.parquet as pq
    t = pq.read_table(path, columns=["id", "text"])
    n = 0
    for aid, text in zip(t.column("id").to_pylist(), t.column("text").to_pylist()):
        for para in text.split("\n"):
            for s in re.split(r"(?<=[.?!])\s+", para.strip()):
                if 8 <= len(s) <= 120 and KO_LINE.match(s) and sum(map(is_syllable, s)) > len(s) * 0.6:
                    yield aid, s
                    n += 1
                    if n >= limit:
                        return


class Spacer:
    def __init__(self, sents):
        self.sp = collections.Counter()
        self.all = collections.Counter()
        for s in sents:
            chars, spaces = self.split(s)
            for i in range(1, len(chars)):
                for a, b in CTX:
                    if a > i or b > len(chars) - i:
                        continue
                    k = f"{a}{b}" + "".join(chars[i - a:i]) + "|" + "".join(chars[i:i + b])
                    self.all[k] += 1
                    self.sp[k] += spaces[i]

    @staticmethod
    def split(s):
        chars, spaces = [], []
        gap = 0
        for ch in s:
            if ch == " ":
                gap = 1
                continue
            chars.append(ch)
            spaces.append(gap)
            gap = 0
        return chars, spaces

    def space(self, text, min_count=3):
        chars = [c for c in text if c != " "]
        out = [chars[0]] if chars else []
        for i in range(1, len(chars)):
            p = 0.0
            for a, b in CTX:
                if a > i or b > len(chars) - i:
                    continue
                k = f"{a}{b}" + "".join(chars[i - a:i]) + "|" + "".join(chars[i:i + b])
                n = self.all.get(k, 0)
                if n >= min_count:
                    p = self.sp[k] / n
                    break
            if p >= 0.5:
                out.append(" ")
            out.append(chars[i])
        return "".join(out)


def score_spacing(fn, test, label, examples):
    tp = fp = fn_ = 0
    eoj_ok = eoj_n = sent_ok = 0
    t = 0.0
    bad = []
    for s in test:
        t0 = time.perf_counter()
        got = fn(s.replace(" ", ""))
        t += time.perf_counter() - t0
        got = re.sub(r"\s+", " ", got).strip()
        want_c, want_s = Spacer.split(s)
        got_c, got_s = Spacer.split(got)
        if got_c != want_c:  # 相手が字を替えたときは文ごと外れとして数える
            fn_ += sum(want_s)
            eoj_n += len(s.split())
            continue
        for w, g in zip(want_s[1:], got_s[1:]):
            tp += w and g
            fp += g and not w
            fn_ += w and not g
        we, ge = set(), set()
        pos = 0
        for e in s.split():
            we.add((pos, pos + len(e)))
            pos += len(e)
        pos = 0
        for e in got.split():
            ge.add((pos, pos + len(e)))
            pos += len(e)
        eoj_ok += len(we & ge)
        eoj_n += len(we)
        sent_ok += got == s
        if got != s and len(bad) < examples:
            bad.append(f"  {s}  →  {got}")
    prec = tp / max(tp + fp, 1)
    rec = tp / max(tp + fn_, 1)
    return [f"分かち書き（{label}）: 空白の適合率 {prec:.1%}・再現率 {rec:.1%}、語が合った {eoj_ok / max(eoj_n, 1):.1%}、"
            f"文が合った {sent_ok / max(len(test), 1):.1%}、1 文平均 {t / max(len(test), 1) * 1000:.2f} ミリ秒"] + bad


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tatoeba", required=True)
    ap.add_argument("--wiki")
    ap.add_argument("--eng")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=20261106)
    ap.add_argument("--test", type=int, default=2000)
    ap.add_argument("--wiki-limit", type=int, default=120000)
    ap.add_argument("--examples", type=int, default=25)
    args = ap.parse_args()

    train, tat_test, wiki_test = [], [], []
    for sid, s in read_tatoeba(args.tatoeba, "kor"):
        if not KO_LINE.match(s) or " " not in s:
            continue
        (tat_test if unit(args.seed, "t" + sid) < 0.1 else train).append(s)
    n_tat = len(train)
    if args.wiki:
        for aid, s in read_wiki(args.wiki, args.wiki_limit):
            (wiki_test if unit(args.seed, "w" + aid) < 0.1 else train).append(s)
    tat_test, wiki_test = tat_test[: args.test], wiki_test[: args.test]
    out = [f"表づくりの文 {len(train)}（Tatoeba {n_tat}、ウィキ {len(train) - n_tat}）、"
           f"試験 Tatoeba {len(tat_test)}・ウィキ {len(wiki_test)}"]
    t0 = time.time()
    sp = Spacer(train)
    out.append(f"表づくり {time.time() - t0:.1f} 秒、並びの数 {len(sp.all)}")

    kiwi = None
    try:
        from kiwipiepy import Kiwi
        kiwi = Kiwi()
    except Exception as e:  # 比べる相手が無くても自分の分は測る
        out.append(f"kiwipiepy なし: {e}")
    for name, test in (("Tatoeba", tat_test), ("ウィキ", wiki_test)):
        if not test:
            continue
        out += score_spacing(sp.space, test, f"Centaur IME・{name}", args.examples)
        if kiwi:
            out += score_spacing(lambda x: kiwi.space(x, reset_whitespace=True), test, f"kiwipiepy・{name}",
                                 args.examples)

    # 英語モードのまま打った語の見分け
    ko_vocab = collections.Counter(e.strip(",.?!'\"()") for s in train for e in s.split())
    ko_words = [e.strip(",.?!'\"()") for s in tat_test for e in s.split()]
    ko_words = [w for w in ko_words if w and all(map(is_syllable, w))]
    en_vocab, en_words = collections.Counter(), []
    if args.eng:
        for sid, s in read_tatoeba(args.eng, "eng"):
            ws = re.findall(r"[a-z]+", s.lower())
            (en_words.extend(ws) if unit(args.seed, "e" + sid) < 0.02 else en_vocab.update(ws))

    def looks_korean(keys):
        """英語の表に無い（か、ごくまれな）語で、組み立てると字母が残らず、韓国語の表にある語なら直す候補にする。"""
        low = keys.lower()
        if en_vocab[low] >= 3:
            return False
        ko = compose(keys)
        return all(map(is_syllable, ko)) and ko_vocab[ko] >= 2

    hit = sum(looks_korean(to_keys(w)) for w in ko_words)
    hit_lower = sum(looks_korean(to_keys(w).lower()) for w in ko_words)
    false = sum(looks_korean(w) for w in en_words)
    out.append(f"英語モードの見分け: 韓国語の語 {len(ko_words)} のうち見つけた {hit / max(len(ko_words), 1):.1%}"
               f"（Shift を打ち忘れた形では {hit_lower / max(len(ko_words), 1):.1%}）、"
               f"英語の語 {len(en_words)} のうち誤って直そうとした {false / max(len(en_words), 1):.2%}")
    miss = [f"  見逃し {w}（{to_keys(w)}）" for w in ko_words if not looks_korean(to_keys(w))][: args.examples]
    wrong = sorted({f"  誤り {w} → {compose(w)}" for w in en_words if looks_korean(w)})[: args.examples]
    out += miss + wrong

    Path(args.out).mkdir(parents=True, exist_ok=True)
    (Path(args.out) / "ko-measure.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(l for l in out if not l.startswith("  ")))


if __name__ == "__main__":
    main()
