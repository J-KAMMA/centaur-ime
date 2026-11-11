"""Tatoeba の「試験の枠」の文を、ふだんの文の打ち込み（取り違え集め）に使う形にする。

  python tools/tatoeba_pool_typing.py --tatoeba jpn_sentences.tsv.bz2 --table <romanji-hiragana.tsv> --out out.tsv

試験の枠は tools/colloquial_text.py と同じ取り分け（文の番号の SHA-256、seed 20261017 の 10%）で、練習の材料には
使っていない文。話し言葉のしるしやていねいな言い方では絞らず、形の合う文（6〜40 字、漢字・かな・、。だけ）を全部使う。
tests/conversion の既存の試験と重なる文は除く。出力は「ローマ字<TAB>元の文」（tools/mine_mistakes.py の sentences.tsv）。
--part rest なら試験の枠の外（残り 9 割）の文を使う（枠の文で選んだ手がかりを、別の文で確かめるため）。
--contains <語の一覧> なら、その語のどれかを含む文だけ、--count まで。
材料は Tatoeba の日本語の文（CC BY 2.0 FR、一部は CC0。表示: Tatoeba の投稿者）。
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "zenz-finetune"))
sys.path.insert(0, str(HERE))
import build_dataset as bd  # noqa: E402
import colloquial_text as ct  # noqa: E402
import romaji_variants as rv  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tatoeba", required=True)
    ap.add_argument("--table", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=20261017, help="colloquial_text.py と同じ取り分け")
    ap.add_argument("--pool-fraction", type=float, default=0.1)
    ap.add_argument("--repo", default=str(HERE.parent))
    ap.add_argument("--part", choices=("pool", "rest", "check"), default="pool",
                    help="check は 0.8 以上（tools/mine_homophone_cues.py が数えない、確かめ用の文）")
    ap.add_argument("--contains", default="", help="1行1語。どれかを含む文だけ使う")
    ap.add_argument("--count", type=int, default=0, help="0 なら全部")
    ap.add_argument("--skip", type=int, default=0, help="使える文のうち先頭のこの数を飛ばす（前の比べで見た文を避ける）")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    table = rv.load_table(args.table)
    rev = rv.reverse_table(table)
    reader = bd.SudachiReader("core")
    exclusion = bd.TestExclusion(Path(args.repo) / "tests/conversion", bd.load_romaji_table(Path(args.table)))
    words = [w for w in Path(args.contains).read_text(encoding="utf-8").split() if w] if args.contains else []
    lines, seen = [], set()
    stats = {"pool": 0, "shape": 0, "reading": 0, "blocked": 0}
    for sid, text in ct.read_tatoeba(args.tatoeba):
        unit = ct.stable_unit(args.seed, sid)
        if (unit < args.pool_fraction) != (args.part == "pool") or (args.part == "check" and unit < 0.8):
            continue
        if words and not any(w in text for w in words):
            continue
        stats["pool"] += 1
        parts = ct.shape(text)
        key = bd.norm_surface(text)
        if parts is None or key in seen:
            stats["shape"] += 1
            continue
        seen.add(key)
        made = ct.typing_line(parts[0], parts[1], reader, table, rev)
        if made is None:
            stats["reading"] += 1
            continue
        if exclusion.blocked(text, [made[1]]):
            stats["blocked"] += 1
            continue
        if stats.setdefault("skipped", 0) < args.skip:
            stats["skipped"] += 1
            continue
        lines.append(f"{made[0]}\t{text}")
        if args.count and len(lines) >= args.count:
            break
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"{len(lines)} 文", stats)


if __name__ == "__main__":
    main()
