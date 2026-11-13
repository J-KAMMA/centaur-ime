"""小さいかなの打ち始め（x・l）に続きが無いとき、x・l だけを英字にして残りを打ち直す。

xwo（x を）が「ｘｗお」になり、変換で x が消えて「を」になっていた（11/14 利用者の報告）。
ローマ字表には xwa（ゎ）があるので xw は打ちかけとして待ち、次の o で表に無いと分かると、
Mozc は待っていた xw を2文字とも英字のまま出す。w は「を」の打ち始めなのに使われない。

直し方: 表の x・l で始まる打ちかけ（xw、xk、xy、xt、xts、lw …）の後に、表の続きにならない
英小文字が来る組を、表に足す。出すのは先頭の英字（全角）と、残りを表で読んだもの（xwo → ｘを）。
足すのは残りが「を」になる組だけ。lte → ｌて のように広げると LTE・QOL などの略語が壊れる。
x・l の1文字だけ（xb など）は Mozc がもともと ｘ と b に分けるので要らない。

    python apply_letter_prefix.py <mozc/src>
"""
import string
import sys
from pathlib import Path

src = Path(sys.argv[1])
p = src / "data/preedit/romanji-hiragana.tsv"
raw = p.read_bytes().decode("utf-8")
newline = "\r\n" if "\r\n" in raw else "\n"
lines = raw.split(newline)
table = {}
for line in lines:
    if line and not line.startswith("#"):
        cols = line.split("\t")
        table.setdefault(cols[0], (cols[1] if len(cols) > 1 else "", cols[2] if len(cols) > 2 else ""))
keys = set(table)


def wide(c):
    return chr(ord(c) - ord("!") + ord("！")) if "!" <= c <= "~" else c


def waits(rest):
    """表の組の打ちかけ（rest で始まる、もっと長い組がある）。"""
    return any(k.startswith(rest) and k != rest for k in keys)


def read(rest):
    """Mozc と同じく残りを表で読む（一番長い組。組が無い文字は英字のまま）。読んだものと待ちを返す。"""
    out = ""
    while rest:
        if waits(rest):
            return out, rest
        match = max((k for k in keys if rest.startswith(k)), key=len, default=None)
        if match is None:
            out, rest = out + wide(rest[0]), rest[1:]
            continue
        output, pending = table[match]
        out, rest = out + output, pending + rest[len(match):]
        if pending and rest == pending:
            return out, rest
    return out, ""


prefixes = sorted({k[:n] for k in keys if k[:1] in ("x", "l") for n in range(2, len(k))})
added = []
for prefix in prefixes:
    for c in string.ascii_lowercase:
        key = prefix + c
        if key in keys or waits(key):
            continue
        output, pending = read(key[1:])
        # 足すのは残りが「を」になる組だけ。ほかの読み（lte → ｌて）は LTE・QOL などの略語を壊す
        # （11/14 の全体試験で略語の4つが下がった）。「を」は w から始まる打ちかけでしか打てない。
        if output != "を" or pending:
            continue
        added.append(f"{key}\t{wide(key[0])}{output}" + (f"\t{pending}" if pending else ""))
assert "xwo\tｘを" in added and "lwo\tｌを" in added,"xwo が足されない"

body = lines
while body and body[-1] == "":
    body = body[:-1]
p.write_bytes(newline.join(body + added + [""]).encode("utf-8"))
print(f"{p.name}: x・l の打ちかけの続き {len(added)} 組を足した")
