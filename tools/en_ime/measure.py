"""CentaurIME English の計測（AI なし）: スペースなしの区切り、打ち間違いの直し、単語の補完。

  python tools/en_ime/measure.py --tatoeba eng_sentences.tsv.bz2 --out en-measure.txt

材料は Tatoeba の英語の文（CC BY 2.0 FR、一部は CC0。表示: Tatoeba の投稿者）。文の番号の SHA-256
（seed 20261105）で 1 割を試験、残りを表づくりに使う。

  区切り:  文の中の句読点で切った各まとまりからスペースを抜き、分け直して元と一致した割合（まとまり単位・文単位）
  直し:    3 文字以上の語に 1 か所の打ち間違い（隣のキー・抜け・余分・入れ替え）を入れ、一番の候補が元の語に戻った割合。
           間違いを入れていない語を別の語に替えてしまった割合（誤った直し）も数える
  補完:    一番の候補が正しくなった時点で Tab（1 打）で確定するとして、打つ数がどれだけ減ったか
"""
import argparse
import bz2
import hashlib
import random
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from en_model import Model, words_of  # noqa: E402

ROWS = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]
NEAR = {}
for r, row in enumerate(ROWS):
    for c, ch in enumerate(row):
        near = set()
        for dr in (-1, 0, 1):
            rr = r + dr
            if 0 <= rr < len(ROWS):
                for dc in (-1, 0, 1):
                    cc = c + dc
                    if 0 <= cc < len(ROWS[rr]) and (dr, dc) != (0, 0):
                        near.add(ROWS[rr][cc])
        NEAR[ch] = sorted(near)
CHUNK = re.compile(r"[A-Za-z' ]+")


def unit(seed, key):
    return int.from_bytes(hashlib.sha256(f"{seed}\t{key}".encode()).digest()[:8], "big") / 2**64


def read(path):
    opener = bz2.open if path.endswith(".bz2") else open
    with opener(path, "rt", encoding="utf-8") as f:
        for line in f:
            c = line.rstrip("\n").split("\t")
            if len(c) >= 3 and c[1] == "eng":
                yield c[0], c[2].strip()


def typo(w, rng):
    i = rng.randrange(len(w))
    kind = rng.choice("sdit")
    if kind == "s" and w[i] in NEAR:
        return w[:i] + rng.choice(NEAR[w[i]]) + w[i + 1:]
    if kind == "d":
        return w[:i] + w[i + 1:]
    if kind == "i" and w[i] in NEAR:
        return w[:i] + rng.choice(NEAR[w[i]]) + w[i:]
    if kind == "t" and i + 1 < len(w) and w[i] != w[i + 1]:
        return w[:i] + w[i + 1] + w[i] + w[i + 2:]
    return w[:i] + w[i + 1:]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tatoeba", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=20261105)
    ap.add_argument("--test", type=int, default=3000, help="試験に使う文の数")
    ap.add_argument("--examples", type=int, default=30, help="間違えた例を出す数")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    train, test = [], []
    for sid, text in read(args.tatoeba):
        (test if unit(args.seed, sid) < 0.1 else train).append(text)
    rng = random.Random(args.seed)
    rng.shuffle(test)
    # 前半で重みを選び、後半（重み選びに使わない文）で確かめる
    test, verify = test[:args.test], test[args.test:2 * args.test]
    t0 = time.time()
    m = Model(train)
    build = time.time() - t0
    out = [f"表づくりの文 {len(train)}、語 {m.vocab}、重み選びの文 {len(test)}、確かめの文 {len(verify)}、表づくり {build:.1f} 秒"]

    # 区切り（重みの組を変えて比べ、一番よい組を確かめの文で測る）
    best = None
    for wp, oc in [(1.0, 2.0), (2.0, 2.0), (3.0, 2.0), (2.0, 2.5), (2.0, 3.0), (3.0, 3.0)]:
        m.word_penalty, m.oov_char = wp, oc
        r = segment_score(m, test, 0, f"重み 1 語 {wp}・表に無い字 {oc}")
        out += r
        ok = int(r[0].split("文 ")[1].split("/")[0])
        if best is None or ok > best[0]:
            best = (ok, wp, oc)
    m.word_penalty, m.oov_char = best[1], best[2]
    out += segment_score(m, verify, args.examples, f"確かめ・重み 1 語 {best[1]}・表に無い字 {best[2]}")

    # 直し（正しい語を替えてしまうのが 0.5% 以下の中で、一番の候補が一番よく当たる重みを選ぶ）
    best = None
    for tw in (6.0, 8.0, 10.0, 12.0):
        m.typo_weight = tw
        r = fix_score(m, test, args.seed, 0, f"重み {tw}")
        out += r
        top1 = float(r[0].split("（")[2].split("%")[0])
        false = float(r[0].split("（")[3].split("%")[0])
        if false <= 0.5 and (best is None or top1 > best[0]):
            best = (top1, tw)
    m.typo_weight = best[1] if best else 12.0
    out += fix_score(m, verify, args.seed, args.examples, f"確かめ・重み {m.typo_weight}")

    # 補完
    keys = typed = 0
    for s in test:
        ws = words_of(s)
        prev = "<s>"
        for w in ws:
            keys += len(w)
            cost = len(w)
            for k in range(1, len(w)):
                if m.complete(w[:k], prev) == w:
                    cost = k + 1  # k 文字打って Tab
                    break
            typed += min(cost, len(w))
            prev = w
    out.append(f"補完: 文字 {keys} 打のところ {typed} 打（{1 - typed / max(keys, 1):.1%} 減）")

    Path(args.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out[:1] + [l for l in out if not l.startswith("  ")][1:]))


def segment_score(m, test, examples, label):
    out = []
    ok_chunk = n_chunk = ok_sent = 0
    seg_time = 0.0
    bad = []
    for s in test:
        all_ok = True
        for ch in CHUNK.findall(s):
            ws = words_of(ch)
            if len(ws) < 2:
                continue
            joined = "".join(ws)
            t = time.perf_counter()
            got = m.segment(joined)
            seg_time += time.perf_counter() - t
            n_chunk += 1
            if got == ws:
                ok_chunk += 1
            else:
                all_ok = False
                if len(bad) < examples:
                    bad.append(f"  {' '.join(ws)}  →  {' '.join(got)}")
        ok_sent += all_ok
    out.append(f"区切り（{label}）: まとまり {ok_chunk}/{n_chunk}（{ok_chunk / max(n_chunk, 1):.1%}）、"
               f"文 {ok_sent}/{len(test)}（{ok_sent / len(test):.1%}）、1 まとまり平均 {seg_time / max(n_chunk, 1) * 1000:.2f} ミリ秒")
    return out + bad


def fix_score(m, test, seed, examples, label):
    out = []
    rng = random.Random(seed + 1)  # どの重みでも同じ打ち間違いで比べる
    fixed = n_typo = top3 = false_fix = n_clean = 0
    fix_time = 0.0
    bad = []
    for s in test:
        ws = words_of(s)
        prev = "<s>"
        for w in ws:
            if len(w) >= 3 and rng.random() < 0.3:
                wrong = typo(w, rng)
                if wrong == w or wrong in m.uni:
                    # 別の正しい語になる間違いは、文脈なしでは直せないので数えない
                    prev = w
                    continue
                t = time.perf_counter()
                c = m.corrections(wrong, prev)
                fix_time += time.perf_counter() - t
                n_typo += 1
                fixed += bool(c) and c[0] == w
                top3 += w in c
                if (not c or c[0] != w) and len(bad) < examples:
                    bad.append(f"  {wrong}（元 {w}）→ {', '.join(c)}")
            else:
                c = m.corrections(w, prev, limit=1)
                n_clean += 1
                false_fix += bool(c) and c[0] != w
            prev = w
    out.append(f"直し（{label}）: 一番の候補で直った {fixed}/{n_typo}（{fixed / max(n_typo, 1):.1%}）、3 番以内 {top3 / max(n_typo, 1):.1%}、"
               f"正しい語を替えてしまった {false_fix}/{n_clean}（{false_fix / max(n_clean, 1):.2%}）、1 語平均 {fix_time / max(n_typo, 1) * 1000:.2f} ミリ秒")
    return out + bad


if __name__ == "__main__":
    main()
