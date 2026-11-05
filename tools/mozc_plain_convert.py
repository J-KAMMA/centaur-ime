"""上流の Mozc（AI も CentaurIME の直しも入れていないもの）で文を変換する（一般的な IME との比べ）。

  python3 tools/mozc_plain_convert.py <converter_main> <sentences.tsv> <converted.tsv>
sentences.tsv は ローマ字<TAB>元の文（tools/tatoeba_pool_typing.py）。ローマ字は msime_compare.py と同じ表で
ひらがなに直し、Mozc の converter_main に「s ひらがな」で渡して、各文節の一番の候補をつなぐ。
converted.tsv は tools/batch_convert.sh と同じ形（ローマ字<TAB>文節を | で区切ったもの<TAB>確定した文）。
ひらがなに直せない文は書かない。
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from msime_compare import to_kana  # noqa: E402


def main():
    exe, src, dst = sys.argv[1:4]
    rows = []
    for line in open(src, encoding="utf-8"):
        if line.startswith("#") or not line.strip():
            continue
        romaji = line.split("\t", 1)[0]
        kana = to_kana(romaji)
        if kana:
            rows.append((romaji, kana))
    p = subprocess.run([exe, "--max_candidates_to_show=1"], input="".join(f"s {k}\n" for _, k in rows),
                       capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        sys.exit(p.stderr[-3000:])
    # 1 文ごとに「---------- Segment 0/n」から始まる塊か、「ExecCommand() return false」が出る
    blocks, cur = [], None
    for l in p.stdout.split("\n"):
        if l.startswith("---------- Segment 0/") or l.startswith("ExecCommand() return false"):
            if cur is not None:
                blocks.append(cur)
            cur = [] if l.startswith("-") else None
            if cur is None:
                blocks.append(None)
            continue
        if cur is not None and l.startswith("  0/"):
            cur.append(l.split(" ", 3)[3] if l.count(" ") >= 3 else "")
    if cur is not None:
        blocks.append(cur)
    assert len(blocks) == len(rows), (len(blocks), len(rows), p.stderr[-2000:])
    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        for (romaji, _), segs in zip(rows, blocks):
            segs = segs or []
            f.write(f"{romaji}\t{'|'.join(segs)}\t{''.join(segs)}\n")
    print(f"変換した文 {len(rows)}")


if __name__ == "__main__":
    main()
