"""同音語の手がかりを、集めた取り違え（tools/mine_mistakes.py の mistakes.tsv）から自動で作る（自動の繰り返し）。

  python tools/auto_cues.py --mistakes mistakes.tsv --tatoeba jpn_sentences.tsv.bz2 \
      --cues tools/data/homophone-cues.tsv --out new-cues.tsv --report report.txt

1. 漢字どうしの取り違え（元の文の部分 → 変換の部分。どちらも漢字だけ）を数え、--min-pair 回以上のものを組にする。
2. 組の語幹ごとに、Tatoeba の材料の枠（文の番号の SHA-256 が [--lo, --hi)。確かめの枠 0.8 以上は使わない）で、
   その語幹の文にだけ --min-df 回以上出て、相手の語幹の文には一度も出ない名詞（Sudachi で区切った普通名詞・固有名詞。
   語幹の文節は除く）を手がかりの候補にする。材料の枠の文全体より --min-lift 倍以上出やすいものだけ。多い順に --top 個。
   （字の 2〜4 字の切れ端は「彼か」「にな」のような意味のない手がかりが多く混じったので、名詞にした）
3. 手がかりの表に組がすでにあれば、元の文の語幹の手がかりに足りない候補を足す。無ければ新しい組にする
   （元の文の語幹に手がかりが 1 つも無い組は作らない）。新しい組は表の終わりの「# 自動」の後に置く。
採るかどうかは、確かめの枠で変換して tools/verify_cues.py で決める（直した数より壊した数が多い組は外す）。
材料は Tatoeba の日本語の文（CC BY 2.0 FR、一部は CC0）。
"""
import argparse
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import colloquial_text as ct  # noqa: E402
from mine_homophone_cues import KANJI, grams, spans  # noqa: E402

# 手がかりは、漢字・カタカナ・数字を 1 字以上含むものだけ（「だろ」「にな」のような、かなだけの切れ端は意味を持たない）
CONTENT = re.compile(r"[一-鿿々ァ-ヶー0-9０-９]")
AUTO_MARK = "# 自動（tools/auto_cues.py が作った組。確かめの枠で tools/verify_cues.py が残したもの）"


_TOKENIZER = None


def nouns(text, cut):
    """text の名詞（普通名詞・固有名詞・カタカナの語）の表層の集合。cut の範囲にかかる語は除く。"""
    global _TOKENIZER
    if _TOKENIZER is None:
        from sudachipy import Dictionary
        _TOKENIZER = Dictionary().create()
    out = set()
    for m in _TOKENIZER.tokenize(text):
        pos = m.part_of_speech()
        if pos[0] != "名詞" or pos[1] not in ("普通名詞", "固有名詞"):
            continue
        if any(m.begin() < b and a < m.end() for a, b in cut):
            continue
        out.add(m.surface())
    return out


def read_groups(lines):
    """[(行の番号, [語幹...], {語幹: [手がかり...]})]"""
    out = []
    for i, line in enumerate(lines):
        if not line or line.startswith("#"):
            continue
        cols = line.split("\t")
        stems = cols[0::2]
        out.append((i, stems, {s: [c for c in cols[k * 2 + 1].split(",") if c] for k, s in enumerate(stems)}))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mistakes", nargs="+", required=True)
    ap.add_argument("--tatoeba", required=True)
    ap.add_argument("--cues", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--seed", type=int, default=20261017)
    ap.add_argument("--lo", type=float, default=0.1)
    ap.add_argument("--hi", type=float, default=0.8)
    ap.add_argument("--min-pair", type=int, default=2)
    ap.add_argument("--min-df", type=int, default=3)
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--add", type=int, default=5, help="組がすでにあるとき足す手がかりの数")
    ap.add_argument("--min-sent", type=int, default=15, help="新しい組にする語幹の、材料の枠の文の最少の数")
    ap.add_argument("--min-lift", type=float, default=5.0,
                    help="手がかりが、その語幹の文に、材料の枠の文全体の何倍以上出やすいか（どの文にも出る語を外す）")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    pairs = Counter()
    for path in args.mistakes:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            c = line.split("\t")
            if len(c) >= 6 and c[3] == "kanji" and KANJI.fullmatch(c[4]) and KANJI.fullmatch(c[5]) and c[4] != c[5]:
                pairs[(c[4], c[5])] += 1
    pairs = {p: n for p, n in pairs.items() if n >= args.min_pair}

    lines = Path(args.cues).read_text(encoding="utf-8").split("\n")
    groups = read_groups(lines)
    stems = {s for p in pairs for s in p}
    df = {s: Counter() for s in stems}
    n_sent = Counter()
    for sid, text in ct.read_tatoeba(args.tatoeba):
        if not (args.lo <= ct.stable_unit(args.seed, sid) < args.hi):
            continue
        for s in stems:
            cut = spans(text, s)
            if cut:
                n_sent[s] += 1
                df[s].update(nouns(text, cut))

    # どの文にも出る語を外すため、候補になりうる名詞が材料の枠の文全体に出た数も数える
    maybe = {g for s in stems for g, c in df[s].items() if c >= args.min_df and CONTENT.search(g)}
    bg = Counter()
    n_all = 0
    for sid, text in ct.read_tatoeba(args.tatoeba):
        if not (args.lo <= ct.stable_unit(args.seed, sid) < args.hi):
            continue
        n_all += 1
        if any(g in text for g in maybe):
            bg.update(maybe & nouns(text, []))

    def candidates(x, y):
        cand = [(g, c) for g, c in df[x].items()
                if c >= args.min_df and df[y][g] == 0 and CONTENT.search(g) and not any(ch in g for ch in y)
                and (c / max(n_sent[x], 1)) >= args.min_lift * (bg[g] / max(n_all, 1))]
        cand.sort(key=lambda gc: (-gc[1], len(gc[0]), gc[0]))
        picked = []
        for g, c in cand:
            if any(p in g and pc == c for p, pc in picked):
                continue  # 短い候補を含む長い候補が同じ数なら短い方だけ
            picked.append((g, c))
        return [g for g, _ in picked]

    report = [f"取り違えの組（{args.min_pair} 回以上）: {len(pairs)}"]
    new_lines = []
    added = 0
    for (gold, out), n in sorted(pairs.items(), key=lambda kv: (-kv[1], kv[0])):
        cues_gold = candidates(gold, out)
        cues_out = candidates(out, gold)
        same = [g for g in groups if gold in g[1] and out in g[1]]
        if same:
            i, gstems, gcues = same[0]
            new = [c for c in cues_gold if c not in gcues[gold]][: args.add]
            if not new:
                report.append(f"  {gold}/{out}（{n}）: 組あり、足す手がかりなし")
                continue
            gcues[gold] += new
            lines[i] = "\t".join(f"{s}\t{','.join(gcues[s])}" for s in gstems)
            added += len(new)
            report.append(f"  {gold}/{out}（{n}）: 組あり、{gold} に足す {','.join(new)}")
            continue
        if any(gold in g[1] or out in g[1] for g in groups):
            report.append(f"  {gold}/{out}（{n}）: どちらかが別の組にある（自動では足さない）")
            continue
        if n_sent[out] == 0:
            report.append(f"  {gold}/{out}（{n}）: {out} は材料の文に出ない（辞書の側の誤り。手がかりでは直さない）")
            continue
        if n_sent[gold] < args.min_sent:
            report.append(f"  {gold}/{out}（{n}）: {gold} の文が少ない（{n_sent[gold]}）")
            continue
        if not cues_gold[: args.top]:
            report.append(f"  {gold}/{out}（{n}）: {gold} の手がかりが無い（文 {n_sent[gold]}）")
            continue
        cg = cues_gold[: args.top]
        co = cues_out[: args.top] or ["―"]  # 相手の手がかりが無いときは、出てこない字を置く
        new_lines.append(f"{gold}\t{','.join(cg)}\t{out}\t{','.join(co)}")
        groups.append((-1, [gold, out], {gold: cg, out: co}))
        report.append(f"  {gold}/{out}（{n}）: 新しい組 {gold}={','.join(cg)} / {out}={','.join(co)}")

    while lines and lines[-1] == "":
        lines.pop()
    if new_lines:
        if AUTO_MARK not in lines:
            lines.append(AUTO_MARK)
        lines += new_lines
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    report.insert(1, f"新しい組 {len(new_lines)}、今の組に足した手がかり {added}")
    Path(args.report).write_text("\n".join(report) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(report[:2]))


if __name__ == "__main__":
    main()
