"""同音語の組（tools/data/homophone-cues.tsv の組）の手がかりの候補を、Tatoeba の文から数えて出す。

  python tools/mine_homophone_cues.py --tatoeba jpn_sentences.tsv.bz2 --pairs pairs.tsv --out cue-candidates.tsv

pairs.tsv は 1 行 1 組で「語幹<TAB>語幹」。語幹は手がかりの表と同じく漢字の続きで、その漢字の続きがちょうど
語幹と同じところだけを数える（花 なら 花瓶・造花 の 花 は数えない）。
手がかりは、語幹とその後ろのかなの続き（同じ文節）を除いた残りの 2〜4 字。片方の文にだけ min-df 回以上出て、
もう片方の文には一度も出ないものを、出た文の数の多い順に出す。採るかどうかは人が見て決める。

数えるのは文の番号の SHA-256（seed 20261017）が [--lo, --hi) の文だけ。0.1 未満は試験の枠、
0.8 以上は手がかりを入れたあとの確かめに取っておく（tools/tatoeba_pool_typing.py --part check）。
材料は Tatoeba の日本語の文（CC BY 2.0 FR、一部は CC0。表示: Tatoeba の投稿者）。
"""
import argparse
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import colloquial_text as ct  # noqa: E402

KANJI = re.compile(r"[一-龯々〆ヵヶ]+")
HIRA_TAIL = re.compile(r"[ぁ-ゖー]*")
PUNCT = re.compile(r"[、。！？「」『』（）・\s]")


def spans(text, stem):
    """漢字の続きがちょうど stem のところの (始め, 文節の終わり)。"""
    out = []
    for m in KANJI.finditer(text):
        if m.group() == stem:
            out.append((m.start(), HIRA_TAIL.match(text, m.end()).end()))
    return out


def grams(text, cut):
    """cut の範囲を除いた 2〜4 字（句読点をまたがない）。"""
    keep = [c if not any(a <= i < b for a, b in cut) else "\0" for i, c in enumerate(text)]
    s = "".join(keep)
    seen = set()
    for n in (2, 3, 4):
        for i in range(len(s) - n + 1):
            g = s[i:i + n]
            if "\0" not in g and not PUNCT.search(g):
                seen.add(g)
    return seen


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tatoeba", required=True)
    ap.add_argument("--pairs", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=20261017)
    ap.add_argument("--lo", type=float, default=0.1)
    ap.add_argument("--hi", type=float, default=0.8)
    ap.add_argument("--min-df", type=int, default=3)
    ap.add_argument("--top", type=int, default=25)
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    pairs = [l.split("\t")[:2] for l in Path(args.pairs).read_text(encoding="utf-8").splitlines()
             if l.strip() and not l.startswith("#")]
    stems = {s for p in pairs for s in p}
    df = {s: Counter() for s in stems}
    n = Counter()
    for sid, text in ct.read_tatoeba(args.tatoeba):
        if not (args.lo <= ct.stable_unit(args.seed, sid) < args.hi):
            continue
        found = {s: spans(text, s) for s in stems}
        for s, cut in found.items():
            if cut:
                n[s] += 1
                df[s].update(grams(text, cut))

    lines = ["# 語幹A\t文の数\t候補（出た文の数）\t語幹B\t文の数\t候補（出た文の数）"]
    for a, b in pairs:
        row = []
        for x, y in ((a, b), (b, a)):
            cand = [(g, c) for g, c in df[x].items() if c >= args.min_df and df[y][g] == 0]
            cand.sort(key=lambda gc: (-gc[1], len(gc[0]), gc[0]))
            # 短い候補を含む長い候補が同じ数なら短い方だけ残す（同じ手がかりの重なり）
            picked = []
            for g, c in cand:
                if any(p in g and pc == c for p, pc in picked):
                    continue
                picked.append((g, c))
            row += [x, str(n[x]), ",".join(f"{g}({c})" for g, c in picked[:args.top])]
        lines.append("\t".join(row))
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"{len(pairs)} 組", {s: n[s] for s in sorted(stems)})


if __name__ == "__main__":
    main()
