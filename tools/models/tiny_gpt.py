"""字の単位の小さな模型（GPT と同じ、前の字から次の字を当てる形）。CPU でも学習できる大きさ（数 M）。

入出力の形は zenz に合わせる:  <始め>入力<区切り>出力<終わり>
学習は「出力」の字だけを当てる（入力の字の誤差は数えない）。
"""
import math

import torch
import torch.nn as nn
import torch.nn.functional as F

PAD, BOS, SEP, EOS = 0, 1, 2, 3
SPECIAL = 4


class Vocab:
    def __init__(self, texts, min_count=1):
        counts = {}
        for t in texts:
            for ch in t:
                counts[ch] = counts.get(ch, 0) + 1
        self.chars = sorted(c for c, n in counts.items() if n >= min_count)
        self.index = {c: i + SPECIAL for i, c in enumerate(self.chars)}
        self.unk = SPECIAL + len(self.chars)

    def __len__(self):
        return SPECIAL + len(self.chars) + 1

    def encode(self, s):
        return [self.index.get(c, self.unk) for c in s]

    def decode(self, ids):
        return "".join(self.chars[i - SPECIAL] for i in ids if SPECIAL <= i < self.unk)

    def state(self):
        return {"chars": self.chars}

    @classmethod
    def from_state(cls, st):
        v = cls([])
        v.chars = st["chars"]
        v.index = {c: i + SPECIAL for i, c in enumerate(v.chars)}
        v.unk = SPECIAL + len(v.chars)
        return v


class Block(nn.Module):
    def __init__(self, d, heads, drop):
        super().__init__()
        self.ln1 = nn.LayerNorm(d)
        self.attn = nn.MultiheadAttention(d, heads, dropout=drop, batch_first=True)
        self.ln2 = nn.LayerNorm(d)
        self.mlp = nn.Sequential(nn.Linear(d, 4 * d), nn.GELU(), nn.Linear(4 * d, d), nn.Dropout(drop))

    def forward(self, x, mask):
        h = self.ln1(x)
        a, _ = self.attn(h, h, h, attn_mask=mask, need_weights=False)
        x = x + a
        return x + self.mlp(self.ln2(x))


class TinyGPT(nn.Module):
    def __init__(self, vocab_size, d=256, layers=4, heads=4, max_len=256, drop=0.1):
        super().__init__()
        self.max_len = max_len
        self.tok = nn.Embedding(vocab_size, d)
        self.pos = nn.Embedding(max_len, d)
        self.blocks = nn.ModuleList(Block(d, heads, drop) for _ in range(layers))
        self.ln = nn.LayerNorm(d)
        self.head = nn.Linear(d, vocab_size, bias=False)
        self.head.weight = self.tok.weight  # 入りと出の重みを共有（小さくする）
        self.config = dict(vocab_size=vocab_size, d=d, layers=layers, heads=heads, max_len=max_len, drop=drop)

    def forward(self, ids):
        # 受け付ける長さを超える並びは後ろの max_len 字だけを見る（試験の文が長いときに位置の表の外を読まないように）
        if ids.size(1) > self.max_len:
            ids = ids[:, -self.max_len:]
        n = ids.size(1)
        x = self.tok(ids) + self.pos(torch.arange(n, device=ids.device))
        mask = torch.triu(torch.full((n, n), float("-inf"), device=ids.device), 1)
        for b in self.blocks:
            x = b(x, mask)
        return self.head(self.ln(x))

    def params(self):
        return sum(p.numel() for p in self.parameters())


def make_example(vocab, src, tgt, max_len):
    """（並び、誤差を数える所の印）。長すぎるものは None。"""
    ids = [BOS] + vocab.encode(src) + [SEP] + vocab.encode(tgt) + [EOS]
    if len(ids) > max_len:
        return None
    start = len(src) + 2  # 出力の最初の字の位置
    return ids, start


def batch_loss(model, batch):
    n = max(len(ids) for ids, _ in batch)
    x = torch.full((len(batch), n), PAD, dtype=torch.long)
    w = torch.zeros((len(batch), n), dtype=torch.bool)
    for i, (ids, start) in enumerate(batch):
        x[i, : len(ids)] = torch.tensor(ids)
        w[i, start: len(ids)] = True
    dev = next(model.parameters()).device
    x, w = x.to(dev), w.to(dev)
    logits = model(x[:, :-1])
    target = x[:, 1:]
    mask = w[:, 1:]
    loss = F.cross_entropy(logits.reshape(-1, logits.size(-1)), target.reshape(-1), reduction="none")
    return (loss * mask.reshape(-1)).sum() / mask.sum().clamp(min=1)


@torch.no_grad()
def score_continuations(model, prefix, conts):
    """prefix（字の番号の並び）の後に、各 conts（番号の並び）が続く対数の確からしさ。"""
    out = []
    for c in conts:
        if not c:
            out.append(0.0)
            continue
        ids = torch.tensor([prefix + c], device=next(model.parameters()).device)
        logp = F.log_softmax(model(ids[:, :-1])[0], -1)
        base = logp.size(0) - len(c)  # 長い並びは前が切られるので、終わりから数える
        s = 0.0
        for k, t in enumerate(c):
            s += logp[base + k, t].item()
        out.append(s)
    return out


@torch.no_grad()
def generate(model, prefix, max_new=128):
    ids = list(prefix)
    for _ in range(max_new):
        if len(ids) >= model.max_len:
            break
        nxt = int(model(torch.tensor([ids], device=next(model.parameters()).device))[0, -1].argmax())
        if nxt == EOS:
            break
        ids.append(nxt)
    return ids[len(prefix):]


@torch.no_grad()
def score_batch(model, prefix, conts):
    """score_continuations と同じ値を、候補をまとめて 1 回で計算する（並べ替えを速くする）。"""
    conts = [c for c in conts]
    if not conts:
        return []
    dev = next(model.parameters()).device
    keep = model.max_len - max(len(c) for c in conts) - 1
    pre = prefix[-keep:] if keep > 0 and len(prefix) > keep else prefix
    n = len(pre) + max(len(c) for c in conts)
    x = torch.full((len(conts), n), PAD, dtype=torch.long, device=dev)
    for i, c in enumerate(conts):
        x[i, : len(pre) + len(c)] = torch.tensor(pre + c, device=dev)
    logp = F.log_softmax(model(x[:, :-1]), -1)
    out = []
    for i, c in enumerate(conts):
        s = 0.0
        for k, tok in enumerate(c):
            s += logp[i, len(pre) - 1 + k, tok].item()
        out.append(s)
    return out


@torch.no_grad()
def next_logp(model, prefix):
    """prefix の次の字の対数の確からしさ（字の番号ごと）。"""
    ids = torch.tensor([prefix], device=next(model.parameters()).device)
    return F.log_softmax(model(ids)[0, -1], -1)


def lr_at(step, total, base, warm=200):
    if step < warm:
        return base * step / warm
    return base * 0.5 * (1 + math.cos(math.pi * min(1.0, (step - warm) / max(1, total - warm))))
