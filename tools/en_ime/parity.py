"""C++ の芯（native/centaur_core）が、試作の Python（en_model.py）と同じ結果を出すかを確かめ、時間を比べる。

  python3 tools/en_ime/parity.py --tatoeba eng_sentences.tsv.bz2 --cli ./centaur_core_cli --out out/parity.txt

measure.py と同じ表（試験の 1 割を除いた文）を作って C++ 向けに書き出し、同じ問い（区切り・直し・補完）を両方に投げる。
問いには、ふつうの文のほかに境目を混ぜる: 空、1 字、表に無い長い語、大文字、' を含む語、とても長い並び。
一つでも違えば終了の番号 1 で止める。
"""
import argparse
import random
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from en_model import Model, words_of  # noqa: E402
from measure import CHUNK, read, typo, unit  # noqa: E402

WP, OOV, TW = 3.0, 2.0, 8.0  # measure.py で選んだ重み


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tatoeba", required=True)
    ap.add_argument("--cli", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=20261105)
    ap.add_argument("--n", type=int, default=1500)
    args = ap.parse_args()

    train, test = [], []
    for sid, text in read(args.tatoeba):
        (test if unit(args.seed, sid) < 0.1 else train).append(text)
    rng = random.Random(args.seed)
    rng.shuffle(test)
    test = test[: args.n]
    m = Model(train)
    m.word_penalty, m.oov_char, m.typo_weight = WP, OOV, TW
    table = Path(args.out).with_name("table.tsv")
    with open(table, "w", encoding="utf-8", newline="\n") as f:
        for w, c in m.uni.items():
            f.write(f"U\t{w}\t{c}\n")
        for (a, b), c in m.bi.items():
            f.write(f"B\t{a}\t{b}\t{c}\n")

    qs = []
    for s in test:
        for ch in CHUNK.findall(s):
            ws = words_of(ch)
            if len(ws) >= 2:
                qs.append(("S", "".join(ws)))
        prev = "<s>"
        for w in words_of(s):
            qs.append(("C", prev, typo(w, rng) if len(w) >= 3 and rng.random() < 0.3 else w))
            if len(w) >= 2:
                qs.append(("P", prev, w[: rng.randrange(1, len(w))]))
            prev = w
    # 境目
    edge = ["a", "i", "zzzzzzzzzzzzzzzzzzzzzzzzz", "tanegashima", "don't", "THE", "Teh", "qq", "x" * 60,
            "abcdefghijklmnopqrstuvwxyz" * 2]
    for e in edge:
        qs += [("S", e.lower()), ("C", "<s>", e), ("C", "the", e), ("P", "<s>", e), ("P", "i", e[:1])]
    qs.append(("C", "unknownprevword", "hte"))

    t0 = time.perf_counter()
    py = []
    times = {"S": 0.0, "C": 0.0, "P": 0.0}
    for q in qs:
        s0 = time.perf_counter()
        if q[0] == "S":
            py.append(" ".join(m.segment(q[1])) if q[1] else "")
        elif q[0] == "C":
            py.append("\t".join(m.corrections(q[2], q[1])))
        else:
            py.append(m.complete(q[2], q[1]) or "")
        times[q[0]] += time.perf_counter() - s0
    py_total = time.perf_counter() - t0

    lines = ["\t".join(q) for q in qs]
    p = subprocess.run([args.cli, str(table), str(WP), str(OOV), str(TW)], input="\n".join(lines) + "\n",
                       capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        sys.exit(p.stderr[-2000:])
    cc = p.stdout.split("\n")[: len(qs)]
    diff = [(q, a, b) for q, a, b in zip(qs, py, cc) if a != b]
    n = {k: sum(1 for q in qs if q[0] == k) for k in times}
    out = [f"問い {len(qs)}（区切り {n['S']}、直し {n['C']}、補完 {n['P']}）、違い {len(diff)}",
           f"Python: 区切り {times['S'] / max(n['S'], 1) * 1e6:.0f} µs、直し {times['C'] / max(n['C'], 1) * 1e6:.0f} µs、"
           f"補完 {times['P'] / max(n['P'], 1) * 1e6:.0f} µs（合計 {py_total:.1f} 秒）",
           "C++: " + p.stderr.strip().replace("\n", "、")]
    out += [f"  違い {q} Python={a!r} C++={b!r}" for q, a, b in diff[:40]]
    Path(args.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out[:3]))
    if diff:
        print("\n".join(out[3:13]))
        sys.exit(1)


if __name__ == "__main__":
    main()
