"""ベトナム語: 声調記号を付けずに打った文を、文脈から記号つきに戻す精度（AI なし）。

  python3 tools/lang_measure/vi_measure.py --tatoeba vie_sentences.tsv.bz2 --wiki vi.parquet --out out

材料: Tatoeba のベトナム語の文（CC BY 2.0 FR）と、ベトナム語ウィキペディアの 1 区切り（CC BY-SA 4.0）。
文の番号の SHA-256 で 1 割を試験、残りを表づくりに使う。
音節ごとに、記号を外した形が同じ記号つきの音節を候補にし、音節の 2 つの並びの表で選ぶ（lattice.py）。
比べる基準は「その形で一番よく出る記号つきの音節を選ぶだけ」。大文字・小文字は小文字にそろえて測る。
--nbest-out を付けると、AI の並べ替え（tools/models/train_task.py --task rerank）に渡す上位の候補を 1 行 1 文の
JSON で書く。Tatoeba の番号で 0.1〜0.12 の文は「重みを決める文（dev）」にして、表づくりにも試験にも使わない。
"""
import json
import argparse
import bz2
import collections
import hashlib
import re
import sys
import time
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lattice import Bigram, Trigram, nbest, viterbi  # noqa: E402

SYL = re.compile(r"[a-zàáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]+")


def unit(seed, key):
    return int.from_bytes(hashlib.sha256(f"{seed}\t{key}".encode()).digest()[:8], "big") / 2**64


def strip(s):
    s = s.replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def syllables(text):
    return SYL.findall(unicodedata.normalize("NFC", text.lower()))


def read_tatoeba(path):
    with bz2.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            c = line.rstrip("\n").split("\t")
            if len(c) >= 3 and c[1] == "vie":
                yield "t" + c[0], c[2]


def read_wiki(path, limit):
    import pyarrow.parquet as pq
    t = pq.read_table(path, columns=["id", "text"])
    n = 0
    for aid, text in zip(t.column("id").to_pylist(), t.column("text").to_pylist()):
        for s in re.split(r"(?<=[.?!])\s+|\n", text):
            if 20 <= len(s) <= 200:
                yield "w" + aid, s
                n += 1
                if n >= limit:
                    return


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tatoeba", required=True)
    ap.add_argument("--wiki")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=20261106)
    ap.add_argument("--test", type=int, default=2000)
    ap.add_argument("--wiki-limit", type=int, default=300000)
    ap.add_argument("--nbest-out", help="上位の候補を書く JSON lines のファイル")
    ap.add_argument("--nbest", type=int, default=8)
    ap.add_argument("--extra", help="表づくりに足す文（CC-100 など、1 行 1 文のテキスト）")
    ap.add_argument("--extra-limit", type=int, default=1000000)
    ap.add_argument("--order", type=int, default=2, choices=(2, 3), help="並びの表を何語まで見るか")
    args = ap.parse_args()

    train, tests, dev = [], {"Tatoeba": [], "ウィキ": []}, []
    sources = [read_tatoeba(args.tatoeba)] + ([read_wiki(args.wiki, args.wiki_limit)] if args.wiki else [])
    for src in sources:
        for key, s in src:
            syl = syllables(s)
            if len(syl) < 2:
                continue
            u = unit(args.seed, key)
            if u < 0.1:
                tests["Tatoeba" if key[0] == "t" else "ウィキ"].append(syl)
            elif u < 0.12 and args.nbest_out:
                if key[0] == "t":
                    dev.append(syl)
            else:
                train.append(syl)
    lm = Trigram() if args.order == 3 else Bigram()
    forms = collections.defaultdict(collections.Counter)
    for syl in train:
        lm.add(syl)
        for x in syl:
            forms[strip(x)][x] += 1
    n_extra = 0
    if args.extra:
        with open(args.extra, encoding="utf-8", errors="ignore") as f:
            for line in f:
                syl = syllables(line)
                if len(syl) < 2:
                    continue
                lm.add(syl)
                for x in syl:
                    forms[strip(x)][x] += 1
                n_extra += 1
                if n_extra >= args.extra_limit:
                    break
    out = [f"表づくりの文 {len(train)}（足した文 {n_extra}、並び {args.order} 語）、音節の種類 {len(lm.uni)}、記号を外した形 {len(forms)}"]
    for name, test in tests.items():
        test = test[: args.test]
        if not test:
            continue
        ok = {"一番多い形": 0, "並びで選ぶ": 0}
        sent = {"一番多い形": 0, "並びで選ぶ": 0}
        n = 0
        t = 0.0
        bad = []
        for syl in test:
            plain = [strip(x) for x in syl]
            cands = [sorted(forms[p], key=lambda c: (-forms[p][c], c)) or [p] for p in plain]
            uni = [c[0] for c in cands]
            t0 = time.perf_counter()
            got = viterbi(cands, lm, lambda i, c: 0.0)
            t += time.perf_counter() - t0
            n += len(syl)
            for k, g in (("一番多い形", uni), ("並びで選ぶ", got)):
                ok[k] += sum(a == b for a, b in zip(syl, g))
                sent[k] += g == syl
            if got != syl and len(bad) < 20:
                bad.append(f"  {' '.join(syl)}  →  {' '.join(got)}")
        out.append(f"{name}（文 {len(test)}、音節 {n}）: " + "、".join(
            f"{k} 音節 {ok[k] / max(n, 1):.1%}・文 {sent[k] / max(len(test), 1):.1%}" for k in ok)
            + f"、1 文平均 {t / max(len(test), 1) * 1000:.2f} ミリ秒")
        out += bad
    if args.nbest_out:
        with open(args.nbest_out, "w", encoding="utf-8") as f:
            for split, rows in (("dev", dev[: args.test]), ("test", tests["Tatoeba"][: args.test])):
                for syl in rows:
                    plain = [strip(x) for x in syl]
                    cands = [sorted(forms[p], key=lambda c: (-forms[p][c], c)) or [p] for p in plain]
                    nb = nbest(cands, lm, lambda i, c: 0.0, args.nbest)
                    f.write(json.dumps({"split": split, "gold": syl, "cands": [c for _, c in nb],
                                        "base": [s for s, _ in nb]}, ensure_ascii=False) + "\n")
        out.append(f"並べ替えの候補: dev {len(dev[: args.test])} 文、試験 {len(tests['Tatoeba'][: args.test])} 文 → {args.nbest_out}")
    Path(args.out).mkdir(parents=True, exist_ok=True)
    (Path(args.out) / "vi-measure.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(l for l in out if not l.startswith("  ")))


if __name__ == "__main__":
    main()
