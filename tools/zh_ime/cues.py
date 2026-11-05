"""中国語の同音字の手がかりを集め、Rime の結果に当てて効き目を測る（日本語の homophone-cues と同じ考え方）。

  python3 tools/zh_ime/cues.py --tatoeba cmn_sentences.tsv.bz2 --mistakes out/mistakes-luna_pinyin_simp.tsv \
      --test 5000 --out out

1. 取り違えの組: measure.py の誤り（確かめの枠）から、同じ音で取り違えた字の組（元 A、出力 B、音）を数える。
2. 手がかり集め: 手がかり選びの枠（文の id で 0.1 以上 0.8 未満）の文で、その音で読まれた A と B の前後を見る。
   手がかりは「すぐ左の 1〜2 字（L）」「すぐ右の 1〜2 字（R）」「同じまとまりの中の 2 字（W）」。
   A と一緒に min-df 回以上出て、B とは一度も出ないものを A の手がかりにする。
3. 当てる: 確かめの枠の Rime の出力で、字 B（その音）の前後に A の手がかりがあり B の手がかりが無ければ A に替える。
   組を選ぶのに使った半分の文は除き、残りの半分で、よくなったまとまり・悪くなったまとまりを数える（他・她・它は文の前後を見ないと決められないので別に数える）。
"""
import argparse
import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from measure import HAN, ONLY_HAN_PUNCT, edit_distance, read_tatoeba, stable_unit, syllables  # noqa: E402

TA = set("他她它")


def load(path, seed, lo, hi, t2s):
    out = []
    for sid, text in read_tatoeba(path):
        u = stable_unit(seed, sid)
        if not (lo <= u < hi) or not ONLY_HAN_PUNCT.match(text) or t2s.convert(text) != text:
            continue
        chunks = []
        for c in HAN.findall(text):
            py = syllables(c)
            if py is None:
                chunks = None
                break
            chunks.append((c, py))
        if chunks:
            out.append((sid, chunks))
    return out


def features(s, i):
    f = []
    if i >= 1:
        f.append("L" + s[i - 1])
    if i >= 2:
        f.append("L" + s[i - 2:i])
    if i + 1 < len(s):
        f.append("R" + s[i + 1])
    if i + 2 < len(s):
        f.append("R" + s[i + 1:i + 3])
    for j in range(len(s) - 1):
        if j != i and j + 1 != i:
            f.append("W" + s[j:j + 2])
    return f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tatoeba", required=True)
    ap.add_argument("--mistakes", required=True)
    ap.add_argument("--out", default="out")
    ap.add_argument("--seed", type=int, default=20261017)
    ap.add_argument("--test", type=int, default=5000)
    ap.add_argument("--min-pair", type=int, default=3)
    ap.add_argument("--min-df", type=int, default=3)
    ap.add_argument("--top", type=int, default=40)
    args = ap.parse_args()
    from opencc import OpenCC
    t2s = OpenCC("t2s")

    def pair_side(sid):
        return stable_unit(args.seed + 2, sid) < 0.5

    # 1. 取り違えの組（同じ長さのまとまりで、同じ音の字どうし）
    got_of = {}
    pairs = collections.Counter()
    for line in open(args.mistakes, encoding="utf-8").read().split("\n")[1:]:
        if not line:
            continue
        sid, py, ref, hyp = line.split("\t")
        got_of[(sid, ref)] = hyp
        syl = py.split(" ")
        # 組は確かめの枠の半分（組選びの側）だけから数え、残りの半分で効き目を測る
        if pair_side(sid) and len(hyp) == len(ref) == len(syl):
            for a, b, s in zip(ref, hyp, syl):
                if a != b and syllables(b) and syllables(a):
                    pairs[(a, b, s)] += 1
    pairs = {k: n for k, n in pairs.items() if n >= args.min_pair}
    by_out = collections.defaultdict(list)  # 出力の字と音 → 替える先の候補
    for a, b, s in pairs:
        by_out[(b, s)].append(a)

    # 2. 手がかり集め（手がかり選びの枠）
    chars = {c for a, b, _ in pairs for c in (a, b)}
    df = collections.defaultdict(collections.Counter)  # (字, 音) → 手がかり → 数
    for _, chunks in load(args.tatoeba, args.seed, 0.1, 0.8, t2s):
        for c, py in chunks:
            for i, ch in enumerate(c):
                if ch in chars:
                    df[(ch, py[i])].update(set(features(c, i)))
    cues = {}
    lines = []
    for a, b, s in sorted(pairs, key=lambda k: -pairs[k]):
        fa, fb = df[(a, s)], df[(b, s)]
        ca = [f for f, n in fa.most_common() if n >= args.min_df and fb[f] == 0][: args.top]
        cb = [f for f, n in fb.most_common() if n >= args.min_df and fa[f] == 0][: args.top]
        cues[(a, b, s)] = (set(ca), set(cb))
        lines.append(f"{a}\t{b}\t{s}\t{pairs[(a, b, s)]}\t{fa.total()}\t{fb.total()}\t{','.join(ca)}\t{','.join(cb)}")
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "zh-cues.tsv").write_text("元\t出力\t音\t取り違え\t元の数\t出力の数\t元の手がかり\t出力の手がかり\n"
                                         + "\n".join(lines) + "\n", encoding="utf-8")

    # 3. 確かめの枠の Rime の出力に当てる（measure.py と同じ文の選び方）
    sents = load(args.tatoeba, args.seed, 0.8, 1.01, t2s)
    sents.sort(key=lambda s: stable_unit(args.seed + 1, s[0]))
    sents = sents[: args.test]
    stats = collections.Counter()
    examples = []
    for sid, chunks in sents:
        if pair_side(sid):
            continue
        for ref, py in chunks:
            hyp = got_of.get((sid, ref), ref)
            new = list(hyp)
            if len(hyp) == len(py):
                for i, ch in enumerate(hyp):
                    best, best_n = None, 0
                    for a in by_out.get((ch, py[i]), ()):
                        ca, cb = cues[(a, ch, py[i])]
                        f = set(features(hyp, i))
                        if f & cb:
                            continue
                        n = len(f & ca)
                        if n > best_n:
                            best, best_n = a, n
                    if best:
                        new[i] = best
            new = "".join(new)
            ta = any(x in TA or y in TA for x, y in zip(ref, hyp) if x != y) or \
                any(x in TA or y in TA for x, y in zip(ref, new) if x != y)
            key = "他她它" if ta else "ほか"
            stats[key + "・まとまり"] += 1
            stats[key + "・前の誤り字"] += edit_distance(ref, hyp)
            stats[key + "・後の誤り字"] += edit_distance(ref, new)
            if new != hyp:
                kind = "よくなった" if new == ref else ("悪くなった" if hyp == ref else "変わったがまだ違う")
                stats[key + "・" + kind] += 1
                if len(examples) < 60:
                    examples.append(f"  {kind}  {ref}  Rime: {hyp}  →  {new}")
    report = [f"取り違えの組 {len(pairs)}（{args.min_pair} 回以上）、手がかりのある組 "
              f"{sum(1 for v in cues.values() if v[0])}"]
    for key in ("ほか", "他她它"):
        n = stats[key + "・まとまり"]
        report.append(f"{key}: まとまり {n}、誤り字 {stats[key + '・前の誤り字']} → {stats[key + '・後の誤り字']}、"
                      f"よくなった {stats[key + '・よくなった']}、悪くなった {stats[key + '・悪くなった']}、"
                      f"変わったがまだ違う {stats[key + '・変わったがまだ違う']}")
    report.append("例:")
    report += examples
    (out_dir / "zh-cues-result.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report[:3]))


if __name__ == "__main__":
    sys.exit(main())
