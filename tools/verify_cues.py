"""自動で作った手がかり（tools/auto_cues.py）を、確かめの枠の文で変換した結果で判定する。

  python tools/verify_cues.py --sentences body.tsv --base converted-base.tsv --cand converted-cand.tsv \
      --cues new-cues.tsv --keep kept-cues.tsv --base-cues tools/data/homophone-cues.tsv --report verify.txt

body.tsv はローマ字<TAB>元の文（tools/tatoeba_pool_typing.py --part check）、converted-*.tsv は tools/batch_convert.sh の
出力（ローマ字<TAB>区切り<TAB>確定した文）。base は今の main、cand は手がかりを足した版。
2 つの出力が違った文ごとに、違った部分に語幹が出る組に「直した」（cand が元の文に合い base が合わない）か
「壊した」（逆）を数える（合うかは tools/lenient_match.py のゆるい一致）。壊した数が直した数以上の組は外し
（新しい組は行ごと、今の組に足した手がかりは足す前に戻す）、残りを --keep に書く。
"""
import argparse
import difflib
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lenient_match import lenient_match  # noqa: E402


def read_conv(path):
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        c = line.split("\t")
        if len(c) >= 3:
            out[c[0]] = c[2]
    return out


def groups_of(path):
    """{行の中身: [語幹...]}（# の行と空の行は除く）"""
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            out[line] = line.split("\t")[0::2]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sentences", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--cand", required=True)
    ap.add_argument("--cues", required=True, help="手がかりを足した表（試した版）")
    ap.add_argument("--base-cues", required=True, help="今の main の手がかりの表")
    ap.add_argument("--keep", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    gold = {}
    for line in Path(args.sentences).read_text(encoding="utf-8").splitlines():
        c = line.split("\t")
        if len(c) >= 2:
            gold[c[0]] = c[1]
    base, cand = read_conv(args.base), read_conv(args.cand)
    old = groups_of(args.base_cues)
    new = groups_of(args.cues)
    changed = [line for line in new if line not in old]  # 新しい組か、手がかりを足した組
    stems_of = {line: stems for line, stems in new.items() if line in changed}

    fixed, broken = Counter(), Counter()
    n_diff = 0
    examples = []
    for r, g in gold.items():
        b, c = base.get(r), cand.get(r)
        if b is None or c is None or b == c:
            continue
        n_diff += 1
        ok_b, ok_c = lenient_match(g, b), lenient_match(g, c)
        if ok_b == ok_c:
            continue
        sm = difflib.SequenceMatcher(None, b, c)
        parts = "".join(b[i1:i2] + c[j1:j2] for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal")
        hit = [line for line, stems in stems_of.items() if any(s in parts for s in stems)]
        for line in hit:
            (fixed if ok_c else broken)[line] += 1
        if len(examples) < 40:
            examples.append(f"  {'直した' if ok_c else '壊した'}: {b} → {c}（元 {g}）")

    keep_lines = []
    report = [f"確かめの文 {len(gold)}、出力が違った文 {n_diff}、変えた組 {len(changed)}"]
    dropped = 0
    old_by_first = {stems[0]: line for line, stems in old.items()}
    for line in Path(args.cues).read_text(encoding="utf-8").splitlines():
        if line in stems_of:
            f, b = fixed[line], broken[line]
            name = "/".join(stems_of[line])
            if b > 0 and b >= f:
                dropped += 1
                report.append(f"  外す {name}: 直した {f}、壊した {b}")
                prev = old_by_first.get(stems_of[line][0])
                if prev is not None and set(old[prev]) == set(stems_of[line]):
                    keep_lines.append(prev)  # 今の組に足した手がかりは足す前に戻す
                continue
            report.append(f"  残す {name}: 直した {f}、壊した {b}")
        keep_lines.append(line)
    report.insert(1, f"外した組 {dropped}、残した組 {len(changed) - dropped}")
    report += ["例:"] + examples
    Path(args.keep).write_text("\n".join(keep_lines) + "\n", encoding="utf-8", newline="\n")
    Path(args.report).write_text("\n".join(report) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(report[:2]))


if __name__ == "__main__":
    main()
