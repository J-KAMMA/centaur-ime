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


def viterbi(cands, lm, emit, beam=16):
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
