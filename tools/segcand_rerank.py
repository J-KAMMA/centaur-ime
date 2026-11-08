"""区切りごとの候補（tools/segment_candidates.sh の出力）を、文字の n-gram 言語模型（KenLM）で選び直して測る。

  python tools/segcand_rerank.py --lm wiki.binary --seg wrong.tsv --gold wrong-gold.tsv \
      --seg ok.tsv --gold ok-gold.tsv

各区切りの候補の上位 K 個から、点数 = λ・言語模型の対数確率 − μ・log(順位+1) が最大の並びをビームで探す。
今の変換（各区切りの 1 番目）は λ=0 のとき。λ・μ は dev（入力の前半）で決め、試験（後半）で 1 回だけ測る。
間違えた文（直せたか）と正しかった文（壊さなかったか）の両方を数える。
"""
import argparse
import math
import sys
from collections import defaultdict

import kenlm


def load(seg_path, gold_path):
    gold = {}
    for line in open(gold_path, encoding="utf-8"):
        c = line.rstrip("\n").split("\t")
        if len(c) >= 2:
            gold[c[0]] = c[1]
    segs = defaultdict(dict)
    for line in open(seg_path, encoding="utf-8"):
        c = line.rstrip("\n").split("\t")
        if len(c) >= 3:
            segs[c[0]][int(c[1])] = [w for w in c[2:] if w != "辞書登録"]
    out = []
    for r, g in gold.items():
        if r in segs:
            d = segs[r]
            out.append((g, [d[i] for i in sorted(d)]))
    return out


def spaced(text):
    return " ".join(ch for ch in text if not ch.isspace())


def best(lm, lists, lam, mu, k, beam):
    states = [(0.0, "")]
    for i, cands in enumerate(lists):
        nxt = {}
        last = i == len(lists) - 1
        for score, text in states:
            for rank, w in enumerate(cands[:k]):
                t = text + w
                s = score - mu * math.log(rank + 1)
                if t not in nxt or nxt[t] < s:
                    nxt[t] = s
        # 言語模型の点は文の先頭からの全体で付け直す（短い文なので十分速い）
        scored = sorted(((s + lam * lm.score(spaced(t), bos=True, eos=last), s, t) for t, s in nxt.items()),
                        reverse=True)[:beam]
        states = [(s, t) for _, s, t in scored]
    return max(states, key=lambda st: st[0] + lam * lm.score(spaced(st[1]), bos=True, eos=True))[1]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lm", required=True)
    ap.add_argument("--seg", action="append", required=True)
    ap.add_argument("--gold", action="append", required=True)
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--beam", type=int, default=8)
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    lm = kenlm.Model(a.lm)
    sets = [load(s, g) for s, g in zip(a.seg, a.gold)]
    names = ["間違えた文", "正しかった文"][: len(sets)] + [f"組{i}" for i in range(2, len(sets))]

    def run(rows, lam, mu):
        return sum(best(lm, lists, lam, mu, a.k, a.beam) == g for g, lists in rows)

    dev = [rows[: len(rows) // 2] for rows in sets]
    test = [rows[len(rows) // 2:] for rows in sets]
    grid = [(lam, mu) for lam in (0.5, 1.0, 1.5, 2.0, 3.0) for mu in (0.5, 1.0, 2.0, 4.0, 8.0)]
    res = {}
    base_dev = [run(rows, 0.0, 1.0) for rows in dev]
    print("dev 今の変換（各区切りの 1 番目）:", " / ".join(f"{n} {c}/{len(r)}" for n, c, r in zip(names, base_dev, dev)))
    for lam, mu in grid:
        res[(lam, mu)] = [run(rows, lam, mu) for rows in dev]
        print(f"dev λ={lam} μ={mu}:", " / ".join(f"{n} {c}/{len(r)}" for n, c, r in zip(names, res[(lam, mu)], dev)),
              f"合計 {sum(res[(lam, mu)])}", flush=True)
    pick = max(grid, key=lambda p: (sum(res[p]), -p[0]))
    base_t = [run(rows, 0.0, 1.0) for rows in test]
    got_t = [run(rows, *pick) for rows in test]
    print("試験 今の変換:", " / ".join(f"{n} {c}/{len(r)}" for n, c, r in zip(names, base_t, test)))
    print(f"試験 dev で決めた λ={pick[0]} μ={pick[1]}:",
          " / ".join(f"{n} {c}/{len(r)}" for n, c, r in zip(names, got_t, test)))


if __name__ == "__main__":
    main()
