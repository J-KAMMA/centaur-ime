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
    # 区切りで 1 語増えるごとの重み（細かく切りすぎるのを抑える）と、表に無い語の 1 文字あたりの重み
    word_penalty = 2.0
    oov_char = 1.5
    oov_max = 20
    # 直しで 1 か所違うごとの重み（キーの位置で軽くする。typo_cost を参照）
    typo_weight = 6.0

    def __init__(self, sentences, max_edit=2, prefix_keep=8):
        self.uni = Counter()
        self.bi = Counter()
        for s in sentences:
            ws = ["<s>"] + words_of(s)
            self.uni.update(ws[1:])
            self.bi.update(zip(ws, ws[1:]))
        self.total = sum(self.uni.values())
        self.vocab = len(self.uni)
        # a の後に何回続いたか（前は続いた語の種類の数を数えていて、並びの確率が 1 を超えることがあった）
        self.left = Counter()
        for (a, _), c in self.bi.items():
            self.left[a] += c
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
        # 表に無い語（名前など）: 長いほど出にくい
        return math.log(1.0 / self.total) - self.oov_char * len(w)

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
            top = sorted(beams[i].items(), key=lambda kv: (-kv[1][0], kv[0]))[:8]  # 同点は語の順
            for j in range(i + 1, min(n, i + max(self.max_len, self.oov_max)) + 1):
                w = text[i:j]
                if w not in self.uni and j - i > self.oov_max:
                    continue
                for prev, (score, _, _) in top:
                    s = score + self.logp(prev, w) - self.word_penalty
                    cur = beams[j].get(w)
                    if cur is None or s > cur[0]:
                        beams[j][w] = (s, i, prev)
        if not beams[n]:
            return [text]
        w = min(beams[n], key=lambda k: (-beams[n][k][0], k))
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
                    if edit_distance(w, c) <= self.max_edit:
                        cands[c] = typo_cost(w, c)
        if w in self.uni:
            cands[w] = 0.0
        # 違うごとに出にくくする（打ち間違いはまれ）。隣のキーや入れ替えは軽く数える
        scored = sorted(cands, key=lambda c: (-(self.logp(prev, c) - self.typo_weight * cands[c]), c))
        return scored[:limit]

    # --- 補完 -----------------------------------------------------------------
    def complete(self, prefix, prev="<s>"):
        """打ちかけ prefix の続きの一番の候補（なければ None）。前の語との並びで選ぶ。"""
        lst = self.prefix.get(prefix.lower())
        if not lst:
            return None
        return max(lst, key=lambda c: self.logp(prev, c))


ROWS = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]
POS = {ch: (r, c + 0.5 * r) for r, row in enumerate(ROWS) for c, ch in enumerate(row)}


def near(a, b):
    if a not in POS or b not in POS:
        return False
    (r1, c1), (r2, c2) = POS[a], POS[b]
    return abs(r1 - r2) <= 1 and abs(c1 - c2) <= 1.0


def typo_cost(typed, word):
    """打った typed が word の打ち間違いである重み（キーの位置を見た編集距離）。
    隣のキーへの置き換え・隣どうしの入れ替え・同じ字の重ね打ち・隣のキーの余分は 0.6、ほかは 1。
    先頭の字が違うときは 0.5 足す（先頭はあまり打ち間違えない）。"""
    la, lb = len(typed), len(word)
    d = [[0.0] * (lb + 1) for _ in range(la + 1)]
    for i in range(la + 1):
        d[i][0] = float(i)
    for j in range(lb + 1):
        d[0][j] = float(j)
    for i in range(1, la + 1):
        for j in range(1, lb + 1):
            a, b = typed[i - 1], word[j - 1]
            sub = 0.0 if a == b else (0.6 if near(a, b) else 1.0)
            # typed にだけある字（余分）: 前後の字と同じか隣なら軽い
            extra = 0.6 if (i > 1 and (typed[i - 2] == a or near(typed[i - 2], a))) else 1.0
            d[i][j] = min(d[i - 1][j] + extra, d[i][j - 1] + 1.0, d[i - 1][j - 1] + sub)
            if i > 1 and j > 1 and a == word[j - 2] and typed[i - 2] == b:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 0.6)
    cost = d[la][lb]
    if typed and word and typed[0] != word[0]:
        cost += 0.5
    return cost


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
