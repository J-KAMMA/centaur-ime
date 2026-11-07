"""学習済みの字の模型（tiny_gpt.py の TinyGPT、.pt）を、C++（native/centaur_core/tiny_lm）で読む形に書き出す。
C++ と同じ答えになるかの確かめの材料も書く。

  python tools/models/export_tiny.py --model zh-d256.pt --out zh-lm.bin --check zh-lm-check.tsv --tatoeba cmn_sentences.tsv.bz2
  python tools/models/export_tiny.py --random --out zh-lm.bin ...   （学習済みの模型の代わりにでたらめな重みで、計算の形だけを確かめる）

形: "CTLM1"、int32 で 字の数・幅・層の数・頭の数・長さの上限、float32 で 字の重み・位置の重み・層ごとの重み
（ln1、in_proj、out_proj、ln2、mlp の 2 つ）・最後の ln、int32 字の数と字（長さ＋UTF-8）、int32 読みの数と
（音節、その読みを持つ字をつないだもの）。読みは rr_zh.py と同じく pypinyin で、模型が知っている字だけ。
確かめの材料の行: 「音節を空白でつないだもの<TAB>Tatoeba の元の句<TAB>模型の答え<TAB>元の句の点数<TAB>模型の答えの点数」。
"""
import argparse
import collections
import struct
import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "zh_ime"))
from tiny_gpt import BOS, SEP, TinyGPT, Vocab, next_logp, score_batch  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model")
    ap.add_argument("--random", action="store_true")
    ap.add_argument("--out", required=True)
    ap.add_argument("--check")
    ap.add_argument("--tatoeba")
    ap.add_argument("--n", type=int, default=200)
    a = ap.parse_args()

    import measure as Z  # zh_ime/measure.py（拼音の音節）
    from pypinyin import Style, pinyin

    chunks = []
    if a.tatoeba:
        for sid, text in Z.read_tatoeba(a.tatoeba):
            if Z.stable_unit(20261017, sid) < 0.8:
                continue
            for c in Z.HAN.findall(text):
                py = Z.syllables(c)
                if py and len(c) <= 20:
                    chunks.append((py, c))
            if len(chunks) >= a.n:
                break
    if a.random:
        torch.manual_seed(20261107)
        texts = [" ".join(py) for py, _ in chunks] + [c for _, c in chunks]
        vocab = Vocab(texts)
        model = TinyGPT(len(vocab), d=64, layers=2, heads=4, max_len=256)
    else:
        ck = torch.load(a.model, map_location="cpu")
        vocab = Vocab.from_state(ck["vocab"])
        model = TinyGPT(**ck["config"])
        model.load_state_dict(ck["state"])
    model.eval()
    cfg = model.config

    readings = collections.defaultdict(set)
    for ch in vocab.chars:
        for r in pinyin(ch, style=Style.NORMAL, heteronym=True, v_to_u=False)[0]:
            if r.isascii() and r.isalpha():
                readings[r].add(ch)

    def f32(t):
        v = t.detach().float().flatten().tolist()  # numpy を使わない（無い所でも動くように）
        return struct.pack(f"<{len(v)}f", *v)

    with open(a.out, "wb") as f:
        f.write(b"CTLM1")
        f.write(struct.pack("<5i", len(vocab), cfg["d"], cfg["layers"], cfg["heads"], cfg["max_len"]))
        f.write(f32(model.tok.weight))
        f.write(f32(model.pos.weight))
        for b in model.blocks:
            for t in (b.ln1.weight, b.ln1.bias, b.attn.in_proj_weight, b.attn.in_proj_bias, b.attn.out_proj.weight,
                      b.attn.out_proj.bias, b.ln2.weight, b.ln2.bias, b.mlp[0].weight, b.mlp[0].bias, b.mlp[2].weight,
                      b.mlp[2].bias):
                f.write(f32(t))
        f.write(f32(model.ln.weight))
        f.write(f32(model.ln.bias))

        def s(x):
            bs = x.encode("utf-8")
            f.write(struct.pack("<i", len(bs)))
            f.write(bs)
        f.write(struct.pack("<i", len(vocab.chars)))
        for ch in vocab.chars:
            s(ch)
        f.write(struct.pack("<i", len(readings)))
        for syl in sorted(readings):
            s(syl)
            s("".join(sorted(readings[syl])))
    print(f"字 {len(vocab.chars)}、幅 {cfg['d']}、層 {cfg['layers']}、読み {len(readings)}、{Path(a.out).stat().st_size} バイト")

    if a.check:
        @torch.no_grad()
        def greedy(py):  # rr_zh.py の model_answer と同じ
            prefix = [BOS] + vocab.encode(" ".join(py)) + [SEP]
            out = ""
            for syl in py:
                cands = [ch for ch in readings.get(syl, ()) if ch in vocab.index]
                if not cands:
                    out += "?"
                    continue
                lp = next_logp(model, prefix)
                best = max(cands, key=lambda ch: (lp[vocab.index[ch]].item(), ch))
                out += best
                prefix = prefix + [vocab.index[best]]
            return out

        with open(a.check, "w", encoding="utf-8", newline="\n") as f:
            for py, ref in chunks:
                mine = greedy(py)
                prefix = [BOS] + vocab.encode(" ".join(py)) + [SEP]
                sr, sm = score_batch(model, prefix, [vocab.encode(ref), vocab.encode(mine)])
                f.write(f"{' '.join(py)}\t{ref}\t{mine}\t{sr:.6f}\t{sm:.6f}\n")
        print(f"確かめの材料 {len(chunks)}")


if __name__ == "__main__":
    main()
