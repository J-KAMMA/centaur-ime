"""アラビア語: ローマ字と数字で打った文（Arabizi。例 7abibi → حبيبي）をアラビア文字に直す精度（AI なし）。

  python3 tools/lang_measure/ar_measure.py --data data_dir --wiki ar.parquet --out out

材料（data_dir に置いたもの。どれも Hugging Face の公開の材料。測ると表づくりに使い、配らない）:
  arbml/Arabizi_Transliteration、elkababi2/Darija-Text-Ar-Arabizi（モロッコ）、
  rabeeeehh/arabizi-kit-corpus（MIT）、akhanafer/arabic-to-arabizi（CC BY 4.0）
  並びの表の足しにアラビア語ウィキペディアの 1 区切り（CC BY-SA 4.0、標準語）。
組（Arabizi の文、アラビア文字の文）は語の数が同じものだけ使い、文の SHA-256 で 1 割を試験にする（材料ごとに数える）。
選び方はヒンディー語と同じ（lattice.py）: 語ごとに、そのローマ字で書かれたアラビア文字の語を候補にし、組の重みと 2 語の並びで選ぶ。
表に無いローマ字は決まった読み方（3→ع、7→ح など）で直す。比べる基準: ①決まった読み方だけ ②組の重みだけ。
"""
import argparse
import collections
import hashlib
import json
import math
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lattice import Bigram, viterbi  # noqa: E402

AR = re.compile(r"[؀-ۿ]")
AR_WORD = re.compile(r"^[ء-ي٠-٩ٱ-ۓ]+$")
DIACRITICS = re.compile(r"[ً-ْٰـ]")  # 短い母音の記号とタトウィールは外して比べる

# 決まった読み方（長い組から）
RULES = [("sh", "ش"), ("ch", "ش"), ("gh", "غ"), ("kh", "خ"), ("th", "ث"), ("dh", "ذ"), ("ou", "و"), ("oo", "و"),
         ("ee", "ي"), ("aa", "ا"), ("2", "ء"), ("3", "ع"), ("5", "خ"), ("6", "ط"), ("7", "ح"), ("8", "ق"), ("9", "ص"),
         ("b", "ب"), ("t", "ت"), ("j", "ج"), ("g", "ج"), ("d", "د"), ("r", "ر"), ("z", "ز"), ("s", "س"), ("f", "ف"),
         ("q", "ق"), ("k", "ك"), ("l", "ل"), ("m", "م"), ("n", "ن"), ("h", "ه"), ("w", "و"), ("y", "ي"), ("v", "ف"),
         ("p", "ب"), ("x", "كس"), ("c", "ك"), ("i", "ي"), ("u", "و"), ("o", "و"), ("e", ""), ("a", "ا")]


def rule(word):
    out, i = [], 0
    w = word.lower()
    while i < len(w):
        for a, b in RULES:
            if w.startswith(a, i):
                # 語の中の短い母音（a e i o u の 1 字）は書かない
                if len(a) == 1 and a in "aeiou" and 0 < i < len(w) - 1:
                    b = ""
                out.append(b)
                i += len(a)
                break
        else:
            i += 1
    return "".join(out)


def norm(w):
    return DIACRITICS.sub("", w)


def unit(key):
    return int.from_bytes(hashlib.sha256(f"20261106\t{key}".encode()).digest()[:8], "big") / 2**64


def pairs_from(path):
    """ファイルから（Arabizi、アラビア文字）の組を取り出す。列の名前が分からないものは中身で見分ける。"""
    rows = []
    if path.suffix == ".parquet":
        import pyarrow.parquet as pq
        t = pq.read_table(path).to_pylist()
        rows = [list(r.values()) for r in t]
    elif path.suffix == ".jsonl":
        rows = [list(json.loads(l).values()) for l in open(path, encoding="utf-8") if l.strip()]
    elif path.suffix == ".json":
        d = json.load(open(path, encoding="utf-8"))
        rows = [list(e.values()) for e in d.get("entries", [])]
    out = []
    for r in rows:
        texts = [x for x in r if isinstance(x, str)]
        ar = next((x for x in texts if len(AR.findall(x)) > len(x) * 0.5), None)
        # Arabizi は、アラビア文字を含まず英字を含む文字列のうち一番長いもの（id などの短い列を避ける）
        latin = [x for x in texts if not AR.search(x) and re.search(r"[a-zA-Z]", x) and not re.fullmatch(r"[\w-]*\d{3,}[\w-]*", x)]
        rz = max(latin, key=len) if latin else None
        if ar and rz:
            out.append((rz.strip(), ar.strip()))
    return out


def tokens(rz, ar):
    r = re.findall(r"[a-zA-Z0-9']+", rz.lower())
    a = [norm(w) for w in ar.split()]
    a = [w for w in (re.sub(r"[^ء-يٱ-ۓ]", "", x) for x in a) if w]
    return (r, a) if len(r) == len(a) and r else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True)
    ap.add_argument("--wiki")
    ap.add_argument("--out", required=True)
    ap.add_argument("--wiki-limit", type=int, default=200000)
    args = ap.parse_args()

    sets = {}
    for f in sorted(Path(args.data).rglob("*")):
        if f.suffix in (".parquet", ".json", ".jsonl"):
            name = f.parent.name if f.parent.name != "data" else f.parent.parent.name
            ps = [t for t in (tokens(r, a) for r, a in pairs_from(f)) if t]
            sets.setdefault(name, []).extend(ps)
    out = []
    table = collections.defaultdict(collections.Counter)
    lm = Bigram()
    tests = {}
    for name, ps in sets.items():
        test = []
        for r, a in ps:
            if unit(" ".join(r)) < 0.1:
                test.append((r, a))
            else:
                for x, y in zip(r, a):
                    table[x][y] += 1
                lm.add(a)
        tests[name] = test
        out.append(f"材料 {name}: 組 {len(ps)}（語の数が合うもの）、試験 {len(test)}")
    if args.wiki:
        import pyarrow.parquet as pq
        n = 0
        for text in pq.read_table(args.wiki, columns=["text"]).column("text").to_pylist():
            for s in re.split(r"[.!?؟\n]", text):
                ws = [norm(w) for w in s.split() if AR_WORD.match(norm(w))]
                if len(ws) >= 3:
                    lm.add(ws)
                    n += 1
            if n >= args.wiki_limit:
                break
        out.append(f"ウィキの文 {n} を並びの表に足した")
    out.append(f"組の表のローマ字 {len(table)}、並びの表の語 {len(lm.uni)}")

    for name, test in tests.items():
        if not test:
            continue
        ok, sent, nw, oov, t = collections.Counter(), collections.Counter(), 0, 0, 0.0
        bad = []
        for r, want in test:
            cands, emits = [], []
            for w in r:
                c = table.get(w)
                if c:
                    tot = sum(c.values())
                    cs = sorted(c, key=lambda x: (-c[x], x))[:8]
                    cands.append(cs)
                    emits.append({x: math.log(c[x] / tot) for x in cs})
                else:
                    oov += 1
                    x = rule(w)
                    cands.append([x])
                    emits.append({x: 0.0})
            t0 = time.perf_counter()
            got = viterbi(cands, lm, lambda i, x: emits[i][x])
            t += time.perf_counter() - t0
            nw += len(want)
            for k, g in (("決まった読み方だけ", [rule(w) for w in r]), ("組の重みだけ", [c[0] for c in cands]),
                         ("並びも見る", got)):
                ok[k] += sum(a == b for a, b in zip(want, g))
                sent[k] += g == want
            if got != want and len(bad) < 15:
                bad.append(f"  {' '.join(r)}  →  {' '.join(got)}  （正しくは {' '.join(want)}）")
        out.append(f"{name}（文 {len(test)}、語 {nw}、表に無いローマ字 {oov / max(nw, 1):.1%}）: " + "、".join(
            f"{k} 語 {ok[k] / max(nw, 1):.1%}・文 {sent[k] / max(len(test), 1):.1%}" for k in ok))
        out += bad
    Path(args.out).mkdir(parents=True, exist_ok=True)
    (Path(args.out) / "ar-measure.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(l for l in out if not l.startswith("  ")))


if __name__ == "__main__":
    main()
