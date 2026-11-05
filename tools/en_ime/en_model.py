"""CentaurIME English の中身（AI なし）: 単語の出やすさと 2 語の並びの表で、
スペースなしの区切り、打ち間違いの直し、単語の補完をする。計測用の試作（tools/en_ime/measure.py）。

表は小文字の単語だけで持つ。大文字・小文字は打った文字のまま戻す。
"""
import math
import re
from collections import Counter, defaultdict

WORD = re.compile(r"[a-z]+(?:'[a-z]+)?")
LETTERS = "abcdefghijklmnopqrstuvwxyz'"


def words_of(text):
    return WORD.findall(text.lower())


class Model:
    def __init__(self, sentences, max_edit=2, prefix_keep=8):
        self.uni = Counter()
        self.bi = Counter()
        for s in sentences:
            ws = ["<s>"] + words_of(s)
            self.uni.update(ws[1:])
            self.bi.update(zip(ws, ws[1:]))
        self.total = sum(self.uni.values())
        self.vocab = len(self.uni)
        self.left = Counter(a for a, _ in self.bi)  # a の後に何回続いたか
        self.max_len = max((len(w) for w in self.uni), default=1)
        self.max_edit = max_edit
        # 打ち間違いの直し用（SymSpell の消し字の索引）
        self.deletes = defaultdict(set)
        for w in self.uni:
            for d in self._deletes(w, max_edit):
                self.deletes[d].add(w)
        # 補完用: 先頭の数文字ごとに、出やすい順の単語
        self.prefix = defaultdict(list)
        by_freq = sorted(self.uni, key=lambda w: -self.uni[w])
        for w in by_freq:
            for k in range(1, len(w)):
                lst = self.prefix[w[:k]]
                if len(lst) < prefix_keep:
                    lst.append(w)

    @staticmethod
    def _deletes(w, n):
        out = {w}
        frontier = {w}
        for _ in range(n):
            nxt = set()
            for x in frontier:
                for i in range(len(x)):
                    nxt.add(x[:i] + x[i + 1:])
            out |= nxt
            frontier = nxt
        return out

    def logp_uni(self, w):
        c = self.uni.get(w, 0)
        if c:
            return math.log(c / self.total)
        # 表に無い語: 長いほど出にくい
        return math.log(1.0 / (self.total * 10 ** len(w)))

    def logp(self, prev, w):
        """2 語の並びの出やすさ（足りない分は 1 語の出やすさに戻す、簡単な補間）。"""
        lam = 0.6
        pu = math.exp(self.logp_uni(w))
        n = self.left.get(prev, 0)
        pb = self.bi.get((prev, w), 0) / n if n else 0.0
        return math.log(lam * pb + (1 - lam) * pu) if pb else math.log((1 - lam) * pu)

    # --- スペースなしの区切り -------------------------------------------------
    def segment(self, text):
        """小文字の並びを単語に分ける（2 語の並びでのビタビ）。"""
        n = len(text)
        # best[i][prev] だと重いので、各位置で直前の語ごとに上位だけ残す
        beams = [dict() for _ in range(n + 1)]
        beams[0]["<s>"] = (0.0, None, None)
        for i in range(n):
            if not beams[i]:
                continue
            top = sorted(beams[i].items(), key=lambda kv: -kv[1][0])[:8]
            for j in range(i + 1, min(n, i + self.max_len) + 1):
                w = text[i:j]
                if w not in self.uni and j - i > 1:
                    # 表に無い長い語は、最後の手段として 1 文字ずつだけ許す
                    continue
                for prev, (score, _, _) in top:
                    s = score + self.logp(prev, w)
                    cur = beams[j].get(w)
                    if cur is None or s > cur[0]:
                        beams[j][w] = (s, i, prev)
        if not beams[n]:
            return [text]
        w = max(beams[n], key=lambda k: beams[n][k][0])
        out, j = [], n
        while j > 0:
            s, i, prev = beams[j][w]
            out.append(w)
            j, w = i, prev
        return out[::-1]

    # --- 打ち間違いの直し -----------------------------------------------------
    def corrections(self, w, prev="<s>", limit=3):
        """w の直しの候補（出やすい順）。w が表にあれば w を先頭に置く。"""
        w = w.lower()
        cands = {}
        for d in self._deletes(w, self.max_edit):
            for c in self.deletes.get(d, ()):
                if c not in cands:
                    dist = edit_distance(w, c)
                    if dist <= self.max_edit:
                        cands[c] = dist
        if w in self.uni:
            cands[w] = 0
        # 1 文字違うごとに出にくくする（打ち間違いはまれ）
        scored = sorted(cands, key=lambda c: -(self.logp(prev, c) - 6.0 * cands[c]))
        return scored[:limit]

    # --- 補完 -----------------------------------------------------------------
    def complete(self, prefix, prev="<s>"):
        """打ちかけ prefix の続きの一番の候補（なければ None）。前の語との並びで選ぶ。"""
        lst = self.prefix.get(prefix.lower())
        if not lst:
            return None
        return max(lst, key=lambda c: self.logp(prev, c))


def edit_distance(a, b):
    """入れ替え（隣どうし）も 1 と数える編集距離。"""
    la, lb = len(a), len(b)
    d = [[0] * (lb + 1) for _ in range(la + 1)]
    for i in range(la + 1):
        d[i][0] = i
    for j in range(lb + 1):
        d[0][j] = j
    for i in range(1, la + 1):
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[la][lb]
