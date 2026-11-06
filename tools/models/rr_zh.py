"""中国語: Rime の答えと、学習済みの字の模型（zh.pt）の答えから、まとまりごとに選ぶ（学習はしない）。

  python3 tools/models/rr_zh.py --model zh.pt --rime rime-chunks-luna_pinyin_simp.tsv --out out

候補は「Rime の答え」と「模型の答え（読みが合う字の中から 1 字ずつ選んだもの）」の 2 つ。
点数は「模型が拼音からその字の並びを出す対数の確からしさ」＋重み×（Rime の答えなら 1）。
重みが大きいほど Rime に寄り、十分大きいと Rime と同じ答えになる。重みは dev の文で決め、試験の文で 1 回だけ測る。
Rime の答えは tools/zh_ime/measure.py --dump（Tatoeba の確かめの枠の試験 5000 文と、その次の dev 2000 文）。
"""
import argparse
import collections
import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tiny_gpt import BOS, SEP, TinyGPT, Vocab, next_logp, score_batch  # noqa: E402


def edit_distance(a, b):
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True)
    ap.add_argument("--rime", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--limit", type=int, default=10 ** 9)
    a = ap.parse_args()

    ck = torch.load(a.model, map_location=a.device)
    vocab = Vocab.from_state(ck["vocab"])
    model = TinyGPT(**ck["config"]).to(a.device)
    model.load_state_dict(ck["state"])
    model.eval()
    from pypinyin import Style, pinyin
    readings = collections.defaultdict(set)  # 音節 → その読みを持つ字（模型が知っている字だけ）
    for ch in vocab.chars:
        for r in pinyin(ch, style=Style.NORMAL, heteronym=True, v_to_u=False)[0]:
            if r.isascii() and r.isalpha():
                readings[r].add(ch)

    rows = {"dev": [], "test": []}
    with open(a.rime, encoding="utf-8") as f:
        next(f)
        for line in f:
            split, sid, py, ref, rime = line.rstrip("\n").split("\t")
            rows[split].append((py.split(), ref, rime))

    @torch.no_grad()
    def model_answer(py):
        prefix = [BOS] + vocab.encode(" ".join(py)) + [SEP]
        out = ""
        for s in py:
            cands = [ch for ch in readings.get(s, ()) if ch in vocab.index]
            if not cands:
                out += "?"
                continue
            lp = next_logp(model, prefix)
            best = max(cands, key=lambda ch: (lp[vocab.index[ch]].item(), ch))
            out += best
            prefix = prefix + [vocab.index[best]]
        return out

    @torch.no_grad()
    def scored(split):
        out = []
        for py, ref, rime in rows[split][: a.limit]:
            mine = model_answer(py)
            cands = list(dict.fromkeys([rime, mine]))
            prefix = [BOS] + vocab.encode(" ".join(py)) + [SEP]
            lp = score_batch(model, prefix, [vocab.encode(c) for c in cands])
            out.append((ref, rime, cands, lp))
        return out

    def measure(items, beta):
        ok = n_char = bad = 0
        for ref, rime, cands, lp in items:
            best = max(range(len(cands)), key=lambda i: (lp[i] + beta * (cands[i] == rime), cands[i] == rime))
            got = cands[best]
            ok += got == ref
            n_char += len(ref)
            bad += edit_distance(ref, got)
        return ok / max(len(items), 1), bad / max(n_char, 1)

    dev, test = scored("dev"), scored("test")
    betas = (0.0, 1.0, 2.0, 3.0, 5.0, 8.0, 12.0, 1e9)
    dev_res = {b: measure(dev, b) for b in betas}
    beta = max(betas, key=lambda b: (dev_res[b][0], -dev_res[b][1], b))
    lines = [f"中国語の組み合わせ: dev まとまり {len(dev)} で重みを決め、試験 まとまり {len(test)} で測る（重み 1e9 = Rime だけ）"]
    lines += [f"  dev 重み {b:g}: まとまり {dev_res[b][0]:.1%}、字の誤り {dev_res[b][1]:.2%}" for b in betas]
    for name, b in (("Rime だけ", 1e9), ("模型の点数だけで選ぶ（重み 0）", 0.0), (f"dev で決めた重み {beta:g}", beta)):
        c, e = measure(test, b)
        lines.append(f"  試験 {name}: まとまりが合った {c:.1%}、字の誤り {e:.2%}")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "rr-zh-result.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
