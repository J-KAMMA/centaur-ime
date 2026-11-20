"""英語版に入れる語の表を作る（文字の表。native/centaur_core の centaur_core_cli --save で組み立て済みにする）。

  python3 tools/en_ime/export_table.py --tatoeba eng_sentences.tsv.bz2 --out table.tsv
配る表なので、計測のときと違い Tatoeba の英語の文を全部使う（CC BY 2.0 FR。表示は README に書く）。
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from en_model import Model  # noqa: E402
from measure import read  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tatoeba", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    m = Model([text for _, text in read(args.tatoeba)])
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        for w, c in m.uni.items():
            f.write(f"U\t{w}\t{c}\n")
        for (a, b), c in m.bi.items():
            f.write(f"B\t{a}\t{b}\t{c}\n")
    print(f"語 {len(m.uni)}、並び {len(m.bi)}")


if __name__ == "__main__":
    main()
