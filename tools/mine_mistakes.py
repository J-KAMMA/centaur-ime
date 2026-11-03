"""Collects the sentences the converter got wrong (人工知能の学び直しの材料).

  python tools/mine_mistakes.py <sentences.tsv> <converted.tsv> <mistakes.tsv>

sentences.tsv is romaji<TAB>original (tools/wiki_typing_test.py), converted.tsv the
output of tools/batch_convert.sh (input<TAB>segments<TAB>committed). A sentence that
matches the original only loosely (lenient_match: 気づく/気付く, 達/たち) is no mistake.
mistakes.tsv: romaji<TAB>original<TAB>output<TAB>kind<TAB>original part<TAB>output part,
one line per differing part. kind is
  kanji: both parts are written in kanji (a homophone or another word with the same reading),
  letters: English letters in the output (a Japanese reading taken as English),
  other: segmentation, okurigana, katakana and the rest.
Prints the counts of each kind and the parts most often confused.
"""
import collections
import difflib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lenient_match import lenient_match  # noqa: E402

KANJI = re.compile(r"^[一-鿿々]+$")
LETTER = re.compile(r"[A-Za-z]")
WORD_EDGE = re.compile(r"[぀-ゟ、。ー]")


def widen(text, i, j):
    """Widens text[i:j] to the kanji run around it (同音語 is a whole word, not a character)."""
    while i > 0 and KANJI.match(text[i - 1]):
        i -= 1
    while j < len(text) and KANJI.match(text[j]):
        j += 1
    return i, j


def parts(original, output):
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, original, output, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        a1, a2 = widen(original, i1, i2)
        b1, b2 = widen(output, j1, j2)
        a, b = original[a1:a2], output[b1:b2]
        if LETTER.search(b):
            kind = "letters"
        elif a and b and KANJI.match(a) and KANJI.match(b):
            kind = "kanji"
        else:
            kind = "other"
        yield kind, a, b


def main():
    original = {}
    for line in open(sys.argv[1], encoding="utf-8"):
        if line.startswith("#") or not line.strip():
            continue
        p = line.rstrip("\n").split("\t")
        original[p[0]] = p[1]
    total = wrong = 0
    kinds = collections.Counter()
    pairs = collections.Counter()
    with open(sys.argv[3], "w", encoding="utf-8") as out:
        for line in open(sys.argv[2], encoding="utf-8"):
            p = line.rstrip("\n").split("\t")
            if len(p) < 3 or p[0] not in original:
                continue
            total += 1
            want, got = original[p[0]], p[2]
            if got == want or lenient_match(got, want):
                continue
            wrong += 1
            seen = set()
            for kind, a, b in parts(want, got):
                if (a, b) in seen:
                    continue
                seen.add((a, b))
                kinds[kind] += 1
                if kind == "kanji":
                    pairs[(a, b)] += 1
                out.write("\t".join([p[0], want, got, kind, a, b]) + "\n")
    print(f"変換した文 {total}、元の文と違った文 {wrong}（ゆるい一致は除く）")
    for kind, n in kinds.most_common():
        print(f"  {kind}: {n}")
    print("漢字どうしの取り違え（元 → 出力）の多いもの:")
    for (a, b), n in pairs.most_common(40):
        print(f"  {n:>3}  {a} → {b}")


if __name__ == "__main__":
    main()
