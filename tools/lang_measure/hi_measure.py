"""ヒンディー語: ローマ字で打った文をデーヴァナーガリーに直す精度（AI なし）。

  python3 tools/lang_measure/hi_measure.py --dakshina dakshina_dataset_v1.0/hi --out out

材料は Google の Dakshina（CC BY-SA 4.0）。
  表づくり: hi.translit.sampled.train.tsv（元の語<TAB>ローマ字<TAB>人数）でローマ字 → 元の語の候補と重みを作り、
            native_script_wikipedia の文（試験と別）で語の 2 つの並びの表を作る。
  試験:     romanized/hi.romanized.rejoined.test.{roman,native}.txt（人がふだんの書き方でローマ字にした文）
選び方: 語ごとに、そのローマ字で書かれた元の語を候補にし、ローマ字との組の重みと 2 語の並びで選ぶ（lattice.py）。
表に無いローマ字は indic_transliteration の決まった読み方（ITRANS）で直す。
比べる基準: ①決まった読み方だけ ②組の重みだけ（並びを見ない）。
--nbest-out を付けると、AI の並べ替え（train_task.py --task rerank）に渡す上位の候補を JSON lines で書く。
重みを決める文（dev）は romanized/hi.romanized.rejoined.dev（表づくりにも試験にも使っていない）。
"""
import argparse
import json
import collections
import math
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lattice import Bigram, nbest, viterbi  # noqa: E402

DEVA = re.compile(r"^[ऀ-ॿ]+$")


def rule(roman):
    try:
        from indic_transliteration import sanscript
        return sanscript.transliterate(roman, sanscript.ITRANS, sanscript.DEVANAGARI)
    except Exception:
        return roman


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dakshina", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--lm-limit", type=int, default=300000)
    ap.add_argument("--test", type=int, default=3000)
    ap.add_argument("--nbest-out", help="上位の候補を書く JSON lines のファイル")
    ap.add_argument("--nbest", type=int, default=8)
    args = ap.parse_args()
    d = Path(args.dakshina)

    def text_open(path):
        # Dakshina の一部のファイルは gzip で縮めてある
        import gzip
        return gzip.open(path, "rt", encoding="utf-8") if path.suffix == ".gz" else open(path, encoding="utf-8")

    def lines(folder, stem):
        with text_open(next((d / folder).glob(stem + "*"))) as f:
            return f.read().split("\n")

    table = collections.defaultdict(collections.Counter)
    for line in lines("lexicons", "hi.translit.sampled.train.tsv"):
        p = line.split("\t")
        if len(p) >= 3:
            table[p[1].lower()][p[0]] += int(p[2])
    lm = Bigram()
    wiki = next((d / "native_script_wikipedia").glob("*train.text*"))
    with text_open(wiki) as f:
        for i, line in enumerate(f):
            if i >= args.lm_limit:
                break
            lm.add([w for w in line.split() if DEVA.match(w)])
    roman = lines("romanized", "hi.romanized.rejoined.test.roman.txt")
    native = lines("romanized", "hi.romanized.rejoined.test.native.txt")
    pairs = [(r.split(), n.split()) for r, n in zip(roman, native) if r.strip()]
    pairs = [(r, n) for r, n in pairs if len(r) == len(n)][: args.test]
    out = [f"組の表のローマ字 {len(table)}、並びの表の語 {len(lm.uni)}、試験の文 {len(pairs)}（語の数が合う文だけ）"]

    def lattice_of(rs):
        cands, emits, n_oov = [], [], 0
        for w in rs:
            c = table.get(w)
            if c:
                tot = sum(c.values())
                cs = sorted(c, key=lambda x: (-c[x], x))[:8]
                cands.append(cs)
                emits.append({x: math.log(c[x] / tot) for x in cs})
            else:
                n_oov += 1
                x = rule(w)
                cands.append([x])
                emits.append({x: 0.0})
        return cands, emits, n_oov

    ok = collections.Counter()
    sent = collections.Counter()
    n_words = 0
    oov = 0
    t = 0.0
    bad = []
    for r, n in pairs:
        idx = [i for i, w in enumerate(n) if DEVA.match(w)]  # 句読点や数字は数えない
        rs = [r[i].lower() for i in idx]
        want = [n[i] for i in idx]
        if not want:
            continue
        cands, emits, n_oov = lattice_of(rs)
        oov += n_oov
        t0 = time.perf_counter()
        got = viterbi(cands, lm, lambda i, x: emits[i][x])
        t += time.perf_counter() - t0
        res = {"決まった読み方だけ": [rule(w) for w in rs], "組の重みだけ": [c[0] for c in cands], "並びも見る": got}
        n_words += len(want)
        for k, g in res.items():
            ok[k] += sum(a == b for a, b in zip(want, g))
            sent[k] += g == want
        if got != want and len(bad) < 20:
            bad.append(f"  {' '.join(rs)}  →  {' '.join(got)}  （正しくは {' '.join(want)}）")
    out.append(f"語 {n_words}（表に無いローマ字 {oov / max(n_words, 1):.1%}）")
    for k in ("決まった読み方だけ", "組の重みだけ", "並びも見る"):
        out.append(f"  {k}: 語 {ok[k] / max(n_words, 1):.1%}、文 {sent[k] / max(len(pairs), 1):.1%}")
    out.append(f"並びも見るときの 1 文平均 {t / max(len(pairs), 1) * 1000:.2f} ミリ秒")
    out.append("誤りの例:")
    out += bad
    if args.nbest_out:
        dev_r = lines("romanized", "hi.romanized.rejoined.dev.roman.txt")
        dev_n = lines("romanized", "hi.romanized.rejoined.dev.native.txt")
        dev = [(r.split(), n.split()) for r, n in zip(dev_r, dev_n) if r.strip()]
        dev = [(r, n) for r, n in dev if len(r) == len(n)][: args.test]
        with open(args.nbest_out, "w", encoding="utf-8") as f:
            for split, rows in (("dev", dev), ("test", pairs)):
                for r, n in rows:
                    idx = [i for i, w in enumerate(n) if DEVA.match(w)]
                    want = [n[i] for i in idx]
                    if not want:
                        continue
                    cands, emits, _ = lattice_of([r[i].lower() for i in idx])
                    nb = nbest(cands, lm, lambda i, x: emits[i][x], args.nbest)
                    f.write(json.dumps({"split": split, "gold": want, "cands": [c for _, c in nb],
                                        "base": [s for s, _ in nb]}, ensure_ascii=False) + "\n")
        out.append(f"並べ替えの候補: dev {len(dev)} 文、試験 {len(pairs)} 文 → {args.nbest_out}")
    Path(args.out).mkdir(parents=True, exist_ok=True)
    (Path(args.out) / "hi-measure.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out[: 6]))


if __name__ == "__main__":
    main()
