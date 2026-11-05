"""中国語（簡体字・全拼）の基本の精度を Rime で測る。

  python3 tools/zh_ime/measure.py --tatoeba cmn_sentences.tsv.bz2 --rime ./rime_convert \
      --shared /usr/share/rime-data --schema luna_pinyin_simp --out out

Tatoeba の中国語の文のうち簡体字のものを、句読点で切ったまとまりごとに声調なしの拼音へ直し
（pypinyin）、Rime に打ち込んで毎回一番の候補を選んだ結果を元の文と比べる。
文は日本語と同じく id で振り分け、0.8 以上（手がかり選びに使わない側）だけで測る。
簡拼（各音節の頭の字だけ）で 2〜4 字の語を打ったときの一番の候補の当たりも測る。
"""
import argparse
import bz2
import collections
import hashlib
import re
import subprocess
import sys
from pathlib import Path

from opencc import OpenCC
from pypinyin import Style, lazy_pinyin

HAN = re.compile(r"[一-鿿]+")
ONLY_HAN_PUNCT = re.compile(r"^[一-鿿，。？！、；：“”‘’（）《》…—\s,.?!;:\"'()]+$")


def stable_unit(seed, key):
    value = hashlib.sha256(f"{seed}\t{key}".encode("utf-8")).digest()
    return int.from_bytes(value[:8], "big") / 2**64


def read_tatoeba(path):
    opener = bz2.open if path.endswith(".bz2") else open
    with opener(path, "rt", encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 3:
                yield parts[0], parts[2]


# 注音の大千式の並び（台湾で一番使われているキーの割り当て）
DAQIAN = dict(zip("ㄅㄉㄓㄚㄞㄢㄦㄆㄊㄍㄐㄔㄗㄧㄛㄟㄣㄇㄋㄎㄑㄕㄘㄨㄜㄠㄤㄈㄌㄏㄒㄖㄙㄩㄝㄡㄥ",
                  "125890-qwertyuiopasdfghjkl;zxcvbnm,./"))
assert len(DAQIAN) == 37


def zhuyin_keys(chunk):
    """字ごとの注音（声調なし）を、大千式のキーの並びにする。直せない字があれば None。"""
    zy = lazy_pinyin(chunk, style=Style.BOPOMOFO, errors="ignore")
    if len(zy) != len(chunk):
        return None
    out = []
    for z in zy:
        z = z.strip("ˊˇˋ˙")
        if not z or any(ch not in DAQIAN for ch in z):
            return None
        out.append("".join(DAQIAN[ch] for ch in z))
    return out


def syllables(chunk):
    py = lazy_pinyin(chunk, style=Style.NORMAL, v_to_u=False, errors="ignore")
    if len(py) != len(chunk) or not all(p.isalpha() and p.isascii() for p in py):
        return None
    return py


def edit_distance(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def run_rime(args, user_dir, inputs):
    p = subprocess.run([args.rime, args.shared, str(user_dir), args.schema],
                       input="\n".join(inputs) + "\n", capture_output=True, text=True, check=True)
    rows = [l.split("\t") for l in p.stdout.split("\n") if l]
    assert len(rows) == len(inputs), (len(rows), len(inputs), p.stderr[-2000:])
    return [(r[0], int(r[1])) for r in rows]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tatoeba", required=True)
    ap.add_argument("--rime", required=True)
    ap.add_argument("--shared", required=True)
    ap.add_argument("--schema", required=True)
    ap.add_argument("--script", choices=["simp", "trad"], default="simp", help="簡体字の文か繁体字の文か")
    ap.add_argument("--keys", choices=["pinyin", "zhuyin"], default="pinyin", help="拼音で打つか注音（大千式、声調なし）で打つか")
    ap.add_argument("--user-dir", default="rime-user")
    ap.add_argument("--out", default="out")
    ap.add_argument("--seed", type=int, default=20261017)
    ap.add_argument("--test", type=int, default=5000)
    ap.add_argument("--examples", type=int, default=40)
    args = ap.parse_args()

    t2s = OpenCC("t2s")
    sents = []
    for sid, text in read_tatoeba(args.tatoeba):
        if stable_unit(args.seed, sid) < 0.8 or not ONLY_HAN_PUNCT.match(text):
            continue
        if (t2s.convert(text) != text) != (args.script == "trad"):  # 簡体字か繁体字の文だけ
            continue
        chunks = []
        for c in HAN.findall(text):
            py = syllables(c) if args.keys == "pinyin" else zhuyin_keys(c)
            if py is None:
                chunks = None
                break
            chunks.append((c, py))
        if chunks:
            sents.append((sid, chunks))
    sents.sort(key=lambda s: stable_unit(args.seed + 1, s[0]))
    sents = sents[: args.test]

    flat = [(i, c, py) for i, (_, chunks) in enumerate(sents) for c, py in chunks]
    got = run_rime(args, args.user_dir, ["".join(py) for _, _, py in flat])

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    sent_ok = [True] * len(sents)
    n_char = bad_char = chunk_ok = 0
    times = []
    confusions = collections.Counter()
    rows = []
    for (i, ref, py), (hyp, us) in zip(flat, got):
        times.append(us)
        n_char += len(ref)
        if hyp == ref:
            chunk_ok += 1
            continue
        sent_ok[i] = False
        bad_char += edit_distance(ref, hyp)
        rows.append(f"{sents[i][0]}\t{' '.join(py)}\t{ref}\t{hyp}")
        if len(hyp) == len(ref):
            for a, b in zip(ref, hyp):
                if a != b:
                    confusions[(a, b)] += 1
    (out_dir / f"mistakes-{args.schema}.tsv").write_text(
        "id\tpinyin\tref\tgot\n" + "\n".join(rows) + "\n", encoding="utf-8")
    (out_dir / f"confusions-{args.schema}.tsv").write_text(
        "".join(f"{a}\t{b}\t{lazy_pinyin(a)[0]}\t{lazy_pinyin(b)[0]}\t{n}\n"
                for (a, b), n in confusions.most_common()), encoding="utf-8")

    # 簡拼: 2〜4 字のまとまりを頭の字だけで打つ
    short = [(c, py) for _, c, py in flat if 2 <= len(c) <= 4]
    short = list(dict.fromkeys((c, tuple(py)) for c, py in short))[:3000]
    jp = run_rime(args, args.user_dir, ["".join(p[0] for p in py) for _, py in short])
    jp_ok = sum(h == c for (c, _), (h, _) in zip(short, jp))

    times.sort()
    lines = [
        f"方式 {args.schema}: 文 {len(sents)}・まとまり {len(flat)}・字 {n_char}",
        f"全拼: 文が全部合った {sum(sent_ok) / max(len(sents), 1):.1%}、"
        f"まとまりが合った {chunk_ok / max(len(flat), 1):.1%}、字の誤り {bad_char / max(n_char, 1):.2%}",
        f"全拼の時間（まとまり 1 つ）: 中央 {times[len(times) // 2] / 1000:.2f} ミリ秒、"
        f"遅い方 1% {times[int(len(times) * 0.99)] / 1000:.2f} ミリ秒",
        f"簡拼（2〜4 字、{len(short)} 語）: 一番の候補で合った {jp_ok / max(len(short), 1):.1%}",
        "字の取り違え（多い順）:",
    ]
    lines += [f"  {a}→{b} {n}" for (a, b), n in confusions.most_common(args.examples)]
    lines.append("誤りの例:")
    lines += ["  " + r for r in rows[: args.examples]]
    (out_dir / f"zh-measure-{args.schema}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:5]))


if __name__ == "__main__":
    sys.exit(main())
