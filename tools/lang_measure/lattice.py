"""1 語ごとに候補がいくつかあり、前後の語のつながりで選ぶ問題の共通の部品（AI なし）。

ベトナム語（声調記号を外した音節 → 記号つきの音節）、ヒンディー語（ローマ字の語 → デーヴァナーガリーの語）などで使う。
  lm = Bigram(); lm.add(["tôi", "đi", "học"]); ...
  best = viterbi([["toi", ...候補], ...], lm, emit)
emit(i, cand) は「打った語 i がこの候補である」重み（対数）。候補の並びは同点のとき語の順。
"""
import math
from collections import Counter


class Bigram:
    def __init__(self, lam=0.6):
        self.uni = Counter()
        self.bi = Counter()
        self.left = Counter()
        self.lam = lam
        self.total = 0

    def add(self, words):
        ws = ["<s>"] + list(words)
        self.uni.update(ws[1:])
        for a, b in zip(ws, ws[1:]):
            self.bi[(a, b)] += 1
            self.left[a] += 1
        self.total += len(ws) - 1

    def logp(self, prev, w):
        pu = (self.uni.get(w, 0) + 0.1) / (self.total + 0.1 * (len(self.uni) + 1))
        n = self.left.get(prev, 0)
        pb = self.bi.get((prev, w), 0) / n if n else 0.0
        return math.log(self.lam * pb + (1 - self.lam) * pu)


class Trigram(Bigram):
    """3 つの並びまで見る表。確からしさは 3 つ・2 つ・1 つの並びの割合を重みで混ぜる（足りない並びは 0 として扱う）。"""

    def __init__(self, l3=0.5, l2=0.35):
        super().__init__(lam=1.0)
        self.tri = Counter()
        self.left2 = Counter()
        self.l3, self.l2 = l3, l2

    def add(self, words):
        super().add(words)
        ws = ["<s>", "<s>"] + list(words)
        for a, b, c in zip(ws, ws[1:], ws[2:]):
            self.tri[(a, b, c)] += 1
            self.left2[(a, b)] += 1

    def logp3(self, prev2, prev, w):
        pu = (self.uni.get(w, 0) + 0.1) / (self.total + 0.1 * (len(self.uni) + 1))
        n = self.left.get(prev, 0)
        pb = self.bi.get((prev, w), 0) / n if n else 0.0
        n2 = self.left2.get((prev2, prev), 0)
        pt = self.tri.get((prev2, prev, w), 0) / n2 if n2 else 0.0
        return math.log(self.l3 * pt + self.l2 * pb + (1 - self.l3 - self.l2) * pu)


def viterbi(cands, lm, emit, beam=16):
    if hasattr(lm, "logp3"):
        nb = nbest(cands, lm, emit, n=1, beam=beam * 4)
        return nb[0][1] if nb else []
    """cands[i] は i 番目の語の候補の並び。一番よい候補の並びを返す。"""
    states = {"<s>": (0.0, None)}
    back = []
    for i, cs in enumerate(cands):
        nxt = {}
        for c in cs:
            e = emit(i, c)
            best = None
            for prev, (score, _) in states.items():
                s = score + lm.logp(prev, c) + e
                if best is None or s > best[0] or (s == best[0] and prev < best[1]):
                    best = (s, prev)
            nxt[c] = best
        top = sorted(nxt.items(), key=lambda kv: (-kv[1][0], kv[0]))[:beam]
        states = dict(top)
        back.append(states)
    if not back:
        return []
    w = min(states, key=lambda k: (-states[k][0], k))
    out = [w]
    for i in range(len(back) - 1, 0, -1):
        w = back[i][w][1]
        out.append(w)
    return out[::-1]


def nbest(cands, lm, emit, n=8, beam=64):
    """上位 n 個の候補の並びを [(点数, [語...]), ...] で返す（AI の並べ替えに渡す候補）。

    viterbi と違い、同じ最後の語でも別の道を残す（道ごとの beam）。1 番目は viterbi とほぼ同じになる。
    """
    paths = [(0.0, ("<s>",))]
    for i, cs in enumerate(cands):
        nxt = []
        for score, path in paths:
            for c in cs:
                lp = lm.logp3(path[-2] if len(path) > 1 else "<s>", path[-1], c) if hasattr(lm, "logp3") \
                    else lm.logp(path[-1], c)
                nxt.append((score + lp + emit(i, c), path + (c,)))
        nxt.sort(key=lambda sp: (-sp[0], sp[1]))
        paths = nxt[:beam]
    return [(s, list(p[1:])) for s, p in paths[:n]]
