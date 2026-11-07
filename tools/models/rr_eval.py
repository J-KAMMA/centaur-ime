"""学習済みの並べ替えの模型（train_task.py の rr-*）を、別の候補の一覧（*_measure.py --nbest-out）で測るだけ（学習しない）。

  python tools/models/rr_eval.py --model rr-vi-d256-long.pt --nbest nbest-vi-tri.jsonl --lang vi

土台（AI なし）を替えたとき（3 語の並び、CC-100 を足した表など）、同じ模型がその上でまだ効くかを見る。
重みは dev の文で決め、試験の文で 1 回だけ測る（train_task.py の task_rerank と同じ数え方）。
"""
import argparse
import json
import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tiny_gpt import BOS, EOS, SEP, TinyGPT, Vocab, score_batch  # noqa: E402

BETAS = (0.0, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0)


def spans(ws):
    out, pos = set(), 0
    for w in ws:
        out.add((pos, pos + len(w)))
        pos += len(w)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True)
    ap.add_argument("--nbest", required=True)
    ap.add_argument("--lang", required=True, choices=("vi", "ko", "hi", "ar"))
    ap.add_argument("--limit", type=int, default=3000)
    ap.add_argument("--k", type=int, default=0, help="候補を先頭から k 個だけ使う（0 は全部）")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    ck = torch.load(a.model, map_location="cpu", weights_only=True)
    vocab = Vocab.from_state(ck["vocab"])
    model = TinyGPT(**ck["config"])
    model.load_state_dict(ck["state"])
    model.eval()
    rows = [json.loads(l) for l in open(a.nbest, encoding="utf-8") if l.strip()]
    if a.k:
        for r in rows:
            r["cands"], r["base"] = r["cands"][: a.k], r["base"][: a.k]
    dev = [r for r in rows if r["split"] == "dev"][: a.limit]
    test = [r for r in rows if r["split"] == "test"][: a.limit]

    @torch.no_grad()
    def neural(rs):
        out = []
        for r in rs:
            conts = [(vocab.encode(" ".join(c)) + [EOS])[: model.max_len - 3] for c in r["cands"]]
            out.append(score_batch(model, [BOS, SEP], conts))
        return out

    def measure(rs, scores, beta):
        ok = n = sent = 0
        for r, nn in zip(rs, scores):
            best = max(range(len(r["cands"])), key=lambda i: (r["base"][i] + beta * nn[i], -i))
            got, want = r["cands"][best], r["gold"]
            if a.lang == "ko":
                ok += len(spans(got) & spans(want))
                n += len(want)
            else:
                ok += sum(x == y for x, y in zip(got, want))
                n += len(want)
            sent += got == want
        return ok / max(n, 1), sent / max(len(rs), 1)

    sd, st = neural(dev), neural(test)
    unit = "語（어절）" if a.lang == "ko" else "音節" if a.lang == "vi" else "語"
    res = {b: measure(dev, sd, b) for b in BETAS}
    for b in BETAS:
        print(f"dev 重み {b}: {unit} {res[b][0]:.1%}、文 {res[b][1]:.1%}")
    beta = max(BETAS, key=lambda b: (res[b][1], res[b][0], -b))
    gold_in = sum(r["gold"] in r["cands"] for r in test) / max(len(test), 1)
    for name, b in (("重み 0（土台だけ）", 0.0), (f"重み {beta}（dev で決めた）", beta)):
        w, s = measure(test, st, b)
        print(f"試験 {name}: {unit} {w:.1%}、文 {s:.1%}（候補 {len(test[0]['cands']) if test else 0} 個、正解が候補に {gold_in:.1%}）")


if __name__ == "__main__":
    main()
