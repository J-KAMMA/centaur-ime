"""キーボードで直接打てる言語（表とキーボードの並びを替えるだけの言語）の計測（AI なし）。

  python3 tools/lang_measure/keyboard_langs.py --lang deu --tatoeba deu_sentences.tsv.bz2 --out out

英語版と同じ試作（tools/en_ime/en_model.py）を、その言語の語の表とキーボードの並びで使う。
  直し:     3 字以上の語に 1 か所の打ち間違い（その言語の並びで隣のキー・抜け・余分・入れ替え）を入れ、一番の候補で戻る割合。
            打ち間違いの無い語を替えてしまう割合も数える。
  記号なし: 記号つきの字を含む語（café、niño、Straße）を記号なしで打ったとき（cafe、nino、strasse）、一番の候補で戻る割合。
  補完:     英語と同じ（一番の候補が正しくなった時点で Tab）。
  大文字:   全部小文字で打った文を、元の大文字・小文字に戻せる割合（語・文）。表づくりの文の「文の頭でない所」での
            書き方の多い方を使い、文の頭は大文字にする。基準は「文の頭だけ大文字にする」。
比べる相手は Hunspell（その言語の辞書があれば）。文は Tatoeba（CC BY 2.0 FR）を文の番号で 1 割試験、残りを表づくり。
"""
import argparse
import bz2
import random
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "en_ime"))
import en_model  # noqa: E402
import measure  # noqa: E402

# 言語ごと: キーボードの並び（小文字、3 行）、Hunspell の辞書の名前
LANGS = {
    "eng": (["qwertyuiop", "asdfghjkl", "zxcvbnm"], "en_US"),
    "spa": (["qwertyuiop", "asdfghjklñ", "zxcvbnm"], "es_ES"),
    "por": (["qwertyuiop", "asdfghjklç", "zxcvbnm"], "pt_BR"),
    "deu": (["qwertzuiopü", "asdfghjklöä", "yxcvbnm"], "de_DE"),
    "fra": (["azertyuiop", "qsdfghjklm", "wxcvbn"], "fr_FR"),
    "rus": (["йцукенгшщзхъ", "фывапролджэ", "ячсмитьбю"], "ru_RU"),
    "ara": (["ضصثقفغعهخحجد", "شسيبلاتنمكط", "ئءؤرىةوزظ"], "ar"),
    "ind": (["qwertyuiop", "asdfghjkl", "zxcvbnm"], "id_ID"),
    "tur": (["qwertyuıopğü", "asdfghjklşi", "zxcvbnmöç"], "tr_TR"),
    "ita": (["qwertyuiop", "asdfghjklòàù", "zxcvbnm"], "it_IT"),
}
WORD = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)?")


def use_keyboard(rows):
    """試作のキーの位置の表を、その言語の並びに差し替える（直しの重みと、打ち間違いの作り方の両方）。"""
    en_model.ROWS = rows
    en_model.POS = {ch: (r, c + 0.5 * r) for r, row in enumerate(rows) for c, ch in enumerate(row)}
    near = {}
    for r, row in enumerate(rows):
        for c, ch in enumerate(row):
            s = set()
            for dr in (-1, 0, 1):
                rr = r + dr
                if 0 <= rr < len(rows):
                    for dc in (-1, 0, 1):
                        cc = c + dc
                        if 0 <= cc < len(rows[rr]) and (dr, dc) != (0, 0):
                            s.add(rows[rr][cc])
            near[ch] = sorted(s)
    measure.NEAR.clear()
    measure.NEAR.update(near)


def words_of(text):
    return WORD.findall(unicodedata.normalize("NFC", text).lower())


def strip_marks(w):
    w = w.replace("ß", "ss").replace("ı", "i")
    return "".join(c for c in unicodedata.normalize("NFD", w) if unicodedata.category(c) != "Mn")


def read(path, lang):
    with bz2.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            c = line.rstrip("\n").split("\t")
            if len(c) >= 3 and c[1] == lang:
                yield c[0], c[2].strip()


class Hunspell:
    def __init__(self, dic):
        self.p = subprocess.Popen(["hunspell", "-a", "-i", "utf-8", "-d", dic], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1)
        if not self.p.stdout.readline():
            raise RuntimeError("no hunspell " + dic)

    def corrections(self, w, prev="<s>", limit=3):
        self.p.stdin.write("^" + w + "\n")
        self.p.stdin.flush()
        lines = []
        while True:
            l = self.p.stdout.readline().rstrip("\n")
            if l == "":
                break
            lines.append(l)
        r = lines[0] if lines else "*"
        if r[:1] == "&":
            return [x.strip().lower() for x in r.split(":", 1)[1].split(",")][:limit]
        return [w]


def score(fixer, test, uni, seed):
    rng = random.Random(seed)
    fixed = n_typo = top3 = false_fix = n_clean = 0
    acc_ok = acc_n = 0
    t = 0.0
    for s in test:
        prev = "<s>"
        for w in words_of(s):
            plain = strip_marks(w)
            if plain != w and plain not in uni and len(w) >= 3:
                acc_n += 1
                acc_ok += fixer.corrections(plain, prev, 1)[:1] == [w]
            if len(w) >= 3 and rng.random() < 0.3:
                wrong = measure.typo(w, rng)
                if wrong != w and wrong not in uni:
                    t0 = time.perf_counter()
                    c = fixer.corrections(wrong, prev)
                    t += time.perf_counter() - t0
                    n_typo += 1
                    fixed += bool(c) and c[0] == w
                    top3 += w in c
            else:
                c = fixer.corrections(w, prev, 1)
                n_clean += 1
                false_fix += bool(c) and c[0] != w
            prev = w
    return (f"直し {fixed / max(n_typo, 1):.1%}（3 番以内 {top3 / max(n_typo, 1):.1%}）、"
            f"正しい語を替えた {false_fix / max(n_clean, 1):.2%}、記号なしから戻った {acc_ok / max(acc_n, 1):.1%}"
            f"（{acc_n} 語）、1 語 {t / max(n_typo, 1) * 1000:.2f} ミリ秒")


CASED = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)?")


def case_table(train):
    """語（小文字）ごとに、文の頭でない所で一番多い書き方。"""
    forms = {}
    for s in train:
        for i, tok in enumerate(CASED.findall(unicodedata.normalize("NFC", s))):
            if i == 0:
                continue
            forms.setdefault(tok.lower(), {}).setdefault(tok, 0)
            forms[tok.lower()][tok] += 1
    return {w: max(c, key=lambda k: (c[k], k)) for w, c in forms.items()}


def upper_first(w):
    return w[:1].upper() + w[1:]


def truecase_score(train, test):
    table = case_table(train)
    ok = {"文の頭だけ": 0, "表で戻す": 0}
    sent = {"文の頭だけ": 0, "表で戻す": 0}
    n = 0
    bad = []
    for s in test:
        toks = CASED.findall(unicodedata.normalize("NFC", s))
        if not toks:
            continue
        low = [x.lower() for x in toks]
        base = [upper_first(low[0])] + low[1:]
        ours = [upper_first(table.get(low[0], low[0]))] + [table.get(w, w) for w in low[1:]]
        n += len(toks)
        for k, g in (("文の頭だけ", base), ("表で戻す", ours)):
            ok[k] += sum(a == b for a, b in zip(toks, g))
            sent[k] += g == toks
        if ours != toks and len(bad) < 8:
            bad.append("  " + " ".join(toks) + "  →  " + " ".join(ours))
    return ["大文字: " + "、".join(f"{k} 語 {ok[k] / max(n, 1):.1%}・文 {sent[k] / max(len(test), 1):.1%}" for k in ok)] + bad


class Ours:
    def __init__(self, m):
        self.m = m

    def corrections(self, w, prev="<s>", limit=3):
        return self.m.corrections(w, prev, limit)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lang", required=True, choices=sorted(LANGS))
    ap.add_argument("--tatoeba", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=20261106)
    ap.add_argument("--test", type=int, default=2000)
    ap.add_argument("--train-limit", type=int, default=600000)
    args = ap.parse_args()
    rows, dic = LANGS[args.lang]
    use_keyboard(rows)
    en_model.WORD = WORD  # 試作の語の切り出しを、その言語の字に広げる
    en_model.words_of = words_of

    train, test = [], []
    for sid, text in read(args.tatoeba, args.lang):
        (test if measure.unit(args.seed, sid) < 0.1 else train).append(text)
    random.Random(args.seed).shuffle(test)
    test = test[: args.test]
    train = train[: args.train_limit]
    t0 = time.time()
    m = en_model.Model(train)
    m.word_penalty, m.oov_char, m.typo_weight = 3.0, 2.0, 8.0  # 英語で選んだ重みのまま
    out = [f"{args.lang}: 表づくりの文 {len(train)}、語 {m.vocab}、試験の文 {len(test)}、表づくり {time.time() - t0:.0f} 秒"]
    out.append("Centaur IME: " + score(Ours(m), test, m.uni, args.seed + 1))
    try:
        out.append(f"Hunspell（{dic}）: " + score(Hunspell(dic), test, m.uni, args.seed + 1))
    except Exception as e:
        out.append(f"Hunspell（{dic}）なし: {e}")
    keys = typed = 0
    for s in test:
        prev = "<s>"
        for w in words_of(s):
            keys += len(w)
            cost = len(w)
            for k in range(1, len(w)):
                if m.complete(w[:k], prev) == w:
                    cost = k + 1
                    break
            typed += min(cost, len(w))
            prev = w
    out.append(f"補完: {1 - typed / max(keys, 1):.1%} 減")
    out += truecase_score(train, test)
    Path(args.out).mkdir(parents=True, exist_ok=True)
    (Path(args.out) / f"{args.lang}.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
