"""言語ごとの小さな模型を学習し、AI なしの土台と同じ試験の文で測る（GitHub の CPU で動く大きさ）。

  python3 tools/models/train_task.py --task vi --data data --out out --minutes 200

task:
  vi  ベトナム語: 記号なしの音節 → 記号つき。答えは音節ごとに、記号を外した形が同じ候補の中から選ばせる。
      試験は vi_measure.py と同じ Tatoeba の文（文の番号で 1 割）。比べる相手: 並びで選ぶ 文 66.2%。
  ko  韓国語: 空白なしの文 → 分かち書き。答えは字と字の間ごとに「空白か、次の字か」から選ばせる。
      試験は ko_ime/measure.py と同じ（Tatoeba・ウィキ）。比べる相手: 文 68.8%、kiwipiepy 77.3%。
  hi  ヒンディー語: ローマ字の文 → デーヴァナーガリーの文（自由に書かせる）。試験は Dakshina の test（hi_measure.py と同じ）。
      学習は Dakshina の dev の文の組と、ウィキの文に語の組の表から打ち方を付けて作った組（test は使わない）。
  ar  アラビア語（モロッコ方言）: Arabizi → アラビア文字（自由に書かせる）。試験は ar_measure.py と同じ 1 割。
  zh  中国語（簡体字）: 声調なしの拼音（音節を空白で区切ったもの）→ 漢字。答えは字ごとに、その音節の読みを持つ字の中から
      選ばせる。試験は zh_ime/measure.py と同じ Tatoeba の確かめの枠（0.8 以上、5,000 文）。比べる相手: Rime の
      luna_pinyin_simp で まとまりが合った 53.3%、字の誤り 12.94%。音節の区切りは元の文から作った物を渡す
      （実際の入力では拼音を音節に分ける段が要る）。
学習は決めた分数で止め（--minutes）、そのあと試験の文で測る。結果は out/<task>-result.txt と模型 out/<task>.pt。
"""
import argparse
import bz2
import collections
import random
import re
import sys
import time
import unicodedata
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lang_measure"))
from tiny_gpt import (BOS, EOS, SEP, TinyGPT, Vocab, batch_loss, generate, lr_at, make_example,  # noqa: E402
                      next_logp, score_continuations)


# ---------------------------------------------------------------- 材料
def cc100_lines(path, limit):
    if not path or not Path(path).exists():
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(line)
            if len(out) >= limit:
                break
    return out


def task_vi(a):
    import vi_measure as V
    train, test = [], []
    for key, s in V.read_tatoeba(a.tatoeba):
        syl = V.syllables(s)
        if len(syl) < 2:
            continue
        (test if V.unit(20261106, key) < 0.1 else train).append(syl)
    test = test[:min(2000, a.test_limit)]
    for s in cc100_lines(a.cc100, a.extra):
        syl = V.syllables(s)
        if 2 <= len(syl) <= 40:
            train.append(syl)
    forms = collections.defaultdict(collections.Counter)
    for syl in train:
        for x in syl:
            forms[V.strip(x)][x] += 1
    pairs = [(" ".join(V.strip(x) for x in syl), " ".join(syl)) for syl in train]

    def evaluate(model, vocab):
        ok_syl = n_syl = ok_sent = 0
        for syl in test:
            prefix = [BOS] + vocab.encode(" ".join(V.strip(x) for x in syl)) + [SEP]
            out = []
            for i, x in enumerate(syl):
                p = V.strip(x)
                cands = sorted(forms[p], key=lambda c: (-forms[p][c], c))[:6] or [p]
                sep = " " if i else ""
                scores = score_continuations(model, prefix, [vocab.encode(sep + c) for c in cands])
                best = cands[max(range(len(cands)), key=lambda k: scores[k])]
                prefix = prefix + vocab.encode(sep + best)
                out.append(best)
            n_syl += len(syl)
            ok_syl += sum(a == b for a, b in zip(syl, out))
            ok_sent += out == syl
        return f"Tatoeba（文 {len(test)}）: 音節 {ok_syl / max(n_syl, 1):.1%}、文 {ok_sent / max(len(test), 1):.1%}"
    return pairs, evaluate


def task_ko(a):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ko_ime"))
    import measure as K  # tools/ko_ime/measure.py
    train, tests = [], {"Tatoeba": [], "ウィキ": []}
    for sid, s in K.read_tatoeba(a.tatoeba, "kor"):
        if not K.KO_LINE.match(s) or " " not in s:
            continue
        (tests["Tatoeba"] if K.unit(20261106, "t" + sid) < 0.1 else train).append(s)
    if a.wiki:
        for aid, s in K.read_wiki(a.wiki, 120000):
            (tests["ウィキ"] if K.unit(20261106, "w" + aid) < 0.1 else train).append(s)
    for s in cc100_lines(a.cc100, a.extra):
        if K.KO_LINE.match(s) and " " in s and len(s) <= 100:
            train.append(s)
    tests = {k: v[:min(2000, a.test_limit)] for k, v in tests.items()}
    pairs = [(s.replace(" ", ""), s) for s in train if len(s) <= 110]

    def evaluate(model, vocab):
        lines = []
        for name, test in tests.items():
            ok = 0
            for s in test:
                chars = s.replace(" ", "")
                prefix = [BOS] + vocab.encode(chars) + [SEP] + vocab.encode(chars[:1])
                out = chars[:1]
                for ch in chars[1:]:
                    sp, no = score_continuations(model, prefix, [vocab.encode(" " + ch), vocab.encode(ch)])
                    add = (" " + ch) if sp > no else ch
                    prefix = prefix + vocab.encode(add)
                    out += add
                ok += out == s
            lines.append(f"{name}（文 {len(test)}）: 文が合った {ok / max(len(test), 1):.1%}")
        return "、".join(lines)
    return pairs, evaluate


def task_hi(a):
    d = Path(a.dakshina)
    import gzip

    def text_open(p):
        return gzip.open(p, "rt", encoding="utf-8") if p.suffix == ".gz" else open(p, encoding="utf-8")

    def lines(folder, stem):
        with text_open(next((d / folder).glob(stem + "*"))) as f:
            return f.read().split("\n")
    deva = re.compile(r"^[ऀ-ॿ]+$")
    romans = collections.defaultdict(collections.Counter)  # 元の語 → ローマ字の書き方
    for line in lines("lexicons", "hi.translit.sampled.train.tsv"):
        p = line.split("\t")
        if len(p) >= 3:
            romans[p[0]][p[1].lower()] += int(p[2])
    pairs = []
    for r, n in zip(lines("romanized", "hi.romanized.rejoined.dev.roman.txt"),
                    lines("romanized", "hi.romanized.rejoined.dev.native.txt")):
        if r.strip() and len(r) <= 120:
            pairs.append((r.lower(), n))
    rng = random.Random(20261106)
    wiki = next((d / "native_script_wikipedia").glob("*train.text*"))
    with text_open(wiki) as f:
        for line in f:
            ws = line.split()
            if not ws or len(line) > 120:
                continue
            if all(not deva.match(w) or w in romans for w in ws):
                rs = []
                for w in ws:
                    if deva.match(w):
                        c = romans[w]
                        rs.append(rng.choices(list(c), weights=list(c.values()))[0])
                    else:
                        rs.append(w)
                pairs.append((" ".join(rs), " ".join(ws)))
            if len(pairs) >= a.extra:
                break
    test = [(r.split(), n.split()) for r, n in zip(lines("romanized", "hi.romanized.rejoined.test.roman.txt"),
                                                   lines("romanized", "hi.romanized.rejoined.test.native.txt"))
            if r.strip()]
    test = [(r, n) for r, n in test if len(r) == len(n)][:min(3000, a.test_limit)]

    def evaluate(model, vocab):
        ok = n_words = sent = 0
        for r, n in test:
            got = vocab.decode(generate(model, [BOS] + vocab.encode(" ".join(r).lower()) + [SEP], 160)).split()
            idx = [i for i, w in enumerate(n) if deva.match(w)]
            want = [n[i] for i in idx]
            have = [got[i] if i < len(got) else "" for i in idx]
            n_words += len(want)
            ok += sum(x == y for x, y in zip(want, have))
            sent += want == have
        return f"Dakshina test（文 {len(test)}）: 語 {ok / max(n_words, 1):.1%}、文 {sent / max(len(test), 1):.1%}"
    return pairs, evaluate


def task_ar(a):
    import ar_measure as A
    ps = []
    for f in sorted(Path(a.darija).glob("*.parquet")):
        ps += [t for t in (A.tokens(r, x) for r, x in A.pairs_from(f)) if t]
    train, test = [], []
    for r, w in ps:
        (test if A.unit(" ".join(r)) < 0.1 else train).append((r, w))
    test = test[:a.test_limit]
    pairs = [(" ".join(r), " ".join(w)) for r, w in train if len(" ".join(r)) <= 110]

    def evaluate(model, vocab):
        ok = n = sent = 0
        for r, want in test:
            got = vocab.decode(generate(model, [BOS] + vocab.encode(" ".join(r)) + [SEP], 160)).split()
            n += len(want)
            ok += sum(x == y for x, y in zip(want, got))
            sent += got == want
        return f"モロッコ方言（文 {len(test)}）: 語 {ok / max(n, 1):.1%}、文 {sent / max(len(test), 1):.1%}"
    return pairs, evaluate


def task_zh(a):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "zh_ime"))
    import measure as Z  # tools/zh_ime/measure.py
    from opencc import OpenCC
    from pypinyin import Style, pinyin
    t2s = OpenCC("t2s")

    def chunks_of(text):
        out = []
        for c in Z.HAN.findall(text):
            py = Z.syllables(c)
            if py is None:
                return None
            out.append((c, py))
        return out
    train_chunks, test_sents = [], []
    for sid, text in Z.read_tatoeba(a.tatoeba):
        if not Z.ONLY_HAN_PUNCT.match(text) or t2s.convert(text) != text:
            continue
        cs = chunks_of(text)
        if not cs:
            continue
        if Z.stable_unit(20261017, sid) >= 0.8:
            test_sents.append((sid, cs))
        else:
            train_chunks.extend(cs)
    test_sents.sort(key=lambda s: Z.stable_unit(20261018, s[0]))
    test_sents = test_sents[:min(5000, a.test_limit)]
    extra = 0
    for path in (a.wiki_text, a.cc100):
        for line in cc100_lines(path, a.extra):
            for c in Z.HAN.findall(t2s.convert(line)):
                if 2 <= len(c) <= 40:
                    py = Z.syllables(c)
                    if py:
                        train_chunks.append((c, py))
                        extra += 1
    pairs = [(" ".join(py), c) for c, py in train_chunks if len(c) <= 60]
    chars = sorted({ch for _, c in pairs for ch in c})
    readings = collections.defaultdict(set)  # 音節 → その読みを持つ字
    for ch in chars:
        for r in pinyin(ch, style=Style.NORMAL, heteronym=True, v_to_u=False)[0]:
            if r.isascii() and r.isalpha():
                readings[r].add(ch)

    def evaluate(model, vocab):
        n_chunk = ok_chunk = n_char = bad_char = 0
        for _, cs in test_sents:
            for ref, py in cs:
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
                n_chunk += 1
                ok_chunk += out == ref
                n_char += len(ref)
                bad_char += sum(x != y for x, y in zip(ref, out))
        return (f"Tatoeba 確かめの枠（文 {len(test_sents)}、まとまり {n_chunk}）: まとまりが合った {ok_chunk / max(n_chunk, 1):.1%}、"
                f"字の誤り {bad_char / max(n_char, 1):.2%}（足した材料のまとまり {extra}）")
    return pairs, evaluate


TASKS = {"vi": task_vi, "ko": task_ko, "hi": task_hi, "ar": task_ar, "zh": task_zh}


# ---------------------------------------------------------------- 学習
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--task", required=True, choices=sorted(TASKS))
    ap.add_argument("--tatoeba")
    ap.add_argument("--wiki")
    ap.add_argument("--cc100")
    ap.add_argument("--dakshina")
    ap.add_argument("--darija")
    ap.add_argument("--wiki-text", help="ウィキの文を 1 行 1 文にしたもの（中国語の足しの材料）")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--heads", type=int, default=4)
    ap.add_argument("--amp", action="store_true", help="GPU で半精度を使う（速くなる見込み。採る前に数字を比べる）")
    ap.add_argument("--test-limit", type=int, default=10 ** 9, help="試験の文の数の上限（動くかを確かめるとき用）")
    ap.add_argument("--extra", type=int, default=300000, help="足す材料の文の数（CC-100・作った組）")
    ap.add_argument("--minutes", type=float, default=200)
    ap.add_argument("--d", type=int, default=256)
    ap.add_argument("--layers", type=int, default=6)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    torch.manual_seed(20261106)
    torch.set_num_threads(max(1, torch.get_num_threads()))
    t0 = time.time()
    pairs, evaluate = TASKS[a.task](a)
    vocab = Vocab([s + t for s, t in pairs], min_count=2)
    exs = [e for e in (make_example(vocab, s, t, 256) for s, t in pairs) if e]
    random.Random(1).shuffle(exs)
    model = TinyGPT(len(vocab), d=a.d, layers=a.layers, heads=a.heads, max_len=256).to(a.device)
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=0.01)
    use_amp = a.amp and a.device.startswith("cuda")
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)
    log = [f"{a.task}（{a.device}）: 学習の組 {len(exs)}（長すぎるものを除く）、字の種類 {len(vocab)}、模型 {model.params() / 1e6:.1f}M、"
           f"材料づくり {time.time() - t0:.0f} 秒"]
    print(log[-1], flush=True)
    # 時間で止める。全体の歩数は、最初の 50 歩の速さから見積もって学習率の下げ方に使う
    deadline = time.time() + a.minutes * 60
    step, k, total = 0, 0, 10 ** 9
    t_start = time.time()
    model.train()
    while time.time() < deadline:
        batch = exs[k: k + a.batch]
        k += a.batch
        if len(batch) < a.batch:
            random.Random(step).shuffle(exs)
            k = 0
            continue
        for g in opt.param_groups:
            g["lr"] = lr_at(step, total, a.lr)
        with torch.autocast("cuda", dtype=torch.float16, enabled=use_amp):
            loss = batch_loss(model, batch)
        opt.zero_grad()
        scaler.scale(loss).backward()
        scaler.unscale_(opt)
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        scaler.step(opt)
        scaler.update()
        step += 1
        if step == 50:
            total = int(50 * a.minutes * 60 / max(time.time() - t_start, 1e-6))
            log.append(f"見積もり: 全体 {total} 歩（{total * a.batch / len(exs):.1f} 回り）")
            print(log[-1], flush=True)
        if step % 500 == 0:
            print(f"歩 {step} 誤差 {loss.item():.3f} 経過 {(time.time() - t_start) / 60:.0f} 分", flush=True)
    log.append(f"学習 {step} 歩、最後の誤差 {loss.item():.3f}、{(time.time() - t_start) / 60:.0f} 分")
    model.eval()
    t1 = time.time()
    log.append(evaluate(model, vocab) + f"（測るのに {time.time() - t1:.0f} 秒）")
    print("\n".join(log[-2:]), flush=True)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{a.task}-result.txt").write_text("\n".join(log) + "\n", encoding="utf-8")
    torch.save({"config": model.config, "vocab": vocab.state(), "state": model.state_dict()}, out / f"{a.task}.pt")


if __name__ == "__main__":
    main()
