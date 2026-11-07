"""今の変換が間違えた文（.github/workflows/mine-mistakes.yml の mistakes-*.tsv）を、学び直しの材料にする。

  python tools/zenz-finetune/make_hard_sentences.py --out tools/zenz-finetune/hard-sentences.jsonl \
      --wiki m1/mistakes.tsv m2/mistakes.tsv ... --tatoeba pool/mistakes.tsv

mistakes-*.tsv は ローマ字<TAB>元の文<TAB>出力<TAB>種類<TAB>... 。元の文を使う（英字の取り違え letters は除く）。
ウィキペディアは train-00011（試験は train-00003・00007 から作るので重ならない）、Tatoeba は pool の枠。
build_dataset.py の tatoeba の出典として読ませるため source は "tatoeba"、doc で出どころを分ける。
"""
import argparse
import json
from pathlib import Path


def rows(path):
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        c = line.split("\t")
        if len(c) >= 4 and c[3] != "letters" and c[1].strip():
            yield c[1].strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--wiki", nargs="*", default=[])
    ap.add_argument("--tatoeba", nargs="*", default=[])
    a = ap.parse_args()
    seen, out = set(), []
    for kind, paths in (("wiki", a.wiki), ("tatoeba", a.tatoeba)):
        for p in paths:
            for text in rows(p):
                if text in seen:
                    continue
                seen.add(text)
                out.append({"source": "tatoeba", "doc": f"hard-{kind}:{len(out)}", "split": "train", "text": text})
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    n_wiki = sum(r["doc"].startswith("hard-wiki") for r in out)
    print(f"文 {len(out)}（ウィキペディア {n_wiki}、Tatoeba {len(out) - n_wiki}）")


if __name__ == "__main__":
    main()
