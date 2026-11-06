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
  en  英語: 字の単位の言語の模型（前の文脈に続く字を当てる）。表の仕組み（tools/en_ime/en_model.py）の候補
      （直しの上位 10、補完の上位 8）を、表の点数＋重み×模型の点数で並べ替える。重み 0 が今の表の仕組み。
      試験は compare.py と同じ確かめの文（Tatoeba、文の番号で 1 割のうち後半）。正しい綴りの別の語（form/from など）の直しも測る。
  zh  中国語（簡体字）: 声調なしの拼音（音節を空白で区切ったもの）→ 漢字。答えは字ごとに、その音節の読みを持つ字の中から
      選ばせる。試験は zh_ime/measure.py と同じ Tatoeba の確かめの枠（0.8 以上、5,000 文）。比べる相手: Rime の
      luna_pinyin_simp で まとまりが合った 53.3%、字の誤り 12.94%。音節の区切りは元の文から作った物を渡す
      （実際の入力では拼音を音節に分ける段が要る）。
  rr-vi・rr-hi・rr-ar・rr-ko  並べ替え: 今の方法（lattice.py）の上位 8 個の候補を、その言語の文だけで学んだ字の模型の点数で
      並べ替える（今の方法の点数＋重み×模型の点数）。重みは dev の文で決める。重み 0 が今の方法と同じなので悪くならない。
      候補は vi_measure.py・hi_measure.py・ar_measure.py・ko_ime/measure.py の --nbest-out で作り、--nbest-file で渡す。
      韓国語は分かち書き（空白の入れ方の上位 16 通り）を並べ替え、語（어절）の切れ目が合った数と文で測る。
      （2026-11-06 vi・hi で模型に 1 から変換させたら今の方法に負けたので、この形にした）
学習は決めた分数で止め（--minutes）、そのあと試験の文で測る。結果は out/<task>-result.txt と模型 out/<task>.pt。
"""
import argparse
import bz2
import collections
import json
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
                      next_logp, score_batch, score_continuations)


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
            want = [w for w in n if deva.match(w)]
            have = [w for w in got if deva.match(w)]
            # 語の数がずれても、並びを対応させて合った語を数える（位置だけで比べると 1 語のずれで全部外れる）
            import difflib
            n_words += len(want)
            ok += sum(b.size for b in difflib.SequenceMatcher(None, want, have, autojunk=False).get_matching_blocks())
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
            train_chunks.extend(cs * a.oversample)  # 会話の文を重くする
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


# 正しい綴りの別の語（打ち間違いでできやすい組）
CONFUSABLE = [("from", "form"), ("their", "there"), ("then", "than"), ("lose", "loose"), ("quite", "quiet"),
              ("were", "where"), ("your", "you're"), ("its", "it's"), ("affect", "effect"), ("advice", "advise"),
              ("accept", "except"), ("though", "through"), ("whether", "weather"), ("dose", "does"), ("now", "know")]


def task_en(a):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "en_ime"))
    import en_model as E
    import measure as M
    train, test = [], []
    for sid, text in M.read(a.tatoeba):
        (test if M.unit(20261105, sid) < 0.1 else train).append(text)
    rng = random.Random(20261105)
    rng.shuffle(test)
    verify = test[3000:3000 + min(3000, a.test_limit)]
    model_ngram = E.Model(train)
    model_ngram.word_penalty, model_ngram.oov_char, model_ngram.typo_weight = 3.0, 2.0, 8.0
    lm_text = [" ".join(E.words_of(s)) for s in train]
    for s in cc100_lines(a.cc100, a.extra):
        lm_text.append(" ".join(E.words_of(s)))
    pairs = [("", s) for s in lm_text if 3 <= len(s) <= 200]

    def evaluate(model, vocab):
        def lm(prefix_words, cands):
            ctx = " ".join(w for w in prefix_words[-8:] if w != "<s>")
            pre = [BOS, SEP] + vocab.encode(ctx + (" " if ctx else ""))
            return score_batch(model, pre, [vocab.encode(c + " ") for c in cands])
        betas = (0.0, 0.5, 1.0, 2.0)
        fixed = {b: 0 for b in betas}
        false_fix = {b: 0 for b in betas}
        typed = {b: 0 for b in betas}
        n_typo = n_clean = keys = 0
        rng2 = random.Random(20261106)
        for s in verify:
            ws = E.words_of(s)
            hist = ["<s>"]
            for w in ws:
                prev = hist[-1]
                if len(w) >= 3 and rng2.random() < 0.3:
                    wrong = M.typo(w, rng2)
                    if wrong != w and wrong not in model_ngram.uni:
                        cands = model_ngram.corrections(wrong, prev, 10)
                        if cands:
                            base = [model_ngram.logp(prev, c) - model_ngram.typo_weight * E.typo_cost(wrong, c) for c in cands]
                            neural = lm(hist, cands)
                            n_typo += 1
                            for b in betas:
                                best = max(range(len(cands)), key=lambda i: (base[i] + b * neural[i], -i))
                                fixed[b] += cands[best] == w
                elif n_clean < 4000:
                    cands = model_ngram.corrections(w, prev, 10)
                    if cands:
                        base = [model_ngram.logp(prev, c) - model_ngram.typo_weight * E.typo_cost(w, c) for c in cands]
                        neural = lm(hist, cands)
                        n_clean += 1
                        for b in betas:
                            best = max(range(len(cands)), key=lambda i: (base[i] + b * neural[i], -i))
                            false_fix[b] += cands[best] != w
                hist.append(w)
        # 補完（最初の 600 文）: 一番の候補が正しくなった時点で Tab
        for s in verify[:600]:
            hist = ["<s>"]
            for w in E.words_of(s):
                keys += len(w)
                cost = {b: len(w) for b in betas}
                for k in range(1, len(w)):
                    lst = model_ngram.prefix.get(w[:k])
                    if not lst:
                        break
                    base = [model_ngram.logp(hist[-1], c) for c in lst]
                    neural = lm(hist, lst)
                    for b in betas:
                        if cost[b] == len(w):
                            best = max(range(len(lst)), key=lambda i: (base[i] + b * neural[i], -i))
                            if lst[best] == w:
                                cost[b] = min(k + 1, len(w))
                    if all(cost[b] < len(w) for b in betas):
                        break
                for b in betas:
                    typed[b] += cost[b]
                hist.append(w)
        # 正しい綴りの別の語: 文の中の片方を、もう片方に替えた文で、元に戻せるか
        conf = {b: 0 for b in betas}
        n_conf = 0
        pair_of = {}
        for x, y in CONFUSABLE:
            pair_of[x] = y
            pair_of[y] = x
        for s in verify:
            ws = E.words_of(s)
            for i, w in enumerate(ws):
                if w in pair_of and n_conf < 1500:
                    wrong = pair_of[w]
                    hist = ["<s>"] + ws[:i]
                    cands = [wrong, w]
                    base = [model_ngram.logp(hist[-1], c) for c in cands]
                    neural = lm(hist, cands)
                    n_conf += 1
                    for b in betas:
                        best = max(range(2), key=lambda k: (base[k] + b * neural[k], -k))
                        conf[b] += cands[best] == w
        lines = [f"確かめの文 {len(verify)}、打ち間違い {n_typo}、正しい語 {n_clean}、補完の打数 {keys}、取り違えやすい語 {n_conf}"]
        for b in betas:
            lines.append(f"  重み {b}: 直し {fixed[b] / max(n_typo, 1):.1%}、正しい語を替えた {false_fix[b] / max(n_clean, 1):.2%}、"
                         f"補完 {1 - typed[b] / max(keys, 1):.1%} 減、取り違えやすい語 {conf[b] / max(n_conf, 1):.1%}")
        return "\n".join(lines)
    return pairs, evaluate


def task_rerank(a, lang):
    """今の方法（lattice.py）の上位の候補を、その言語の文だけで学んだ字の模型で並べ替える。

    候補は vi_measure.py・hi_measure.py・ar_measure.py の --nbest-out（a.nbest_file）。重みは dev の文で決め、
    試験の文はその重みで 1 回だけ測る。重み 0 が今の方法（AI なし）と同じ。
    模型が学ぶのは答えの側の文だけ（打った文との組は使わない）。試験と dev の文は学習に入れない。
    """
    texts = []
    if lang == "vi":
        import vi_measure as V
        for key, s in V.read_tatoeba(a.tatoeba):
            syl = V.syllables(s)
            if len(syl) >= 2 and V.unit(20261106, key) >= 0.12:
                texts.append(" ".join(syl))
        for s in cc100_lines(a.cc100, a.extra):
            syl = V.syllables(s)
            if 2 <= len(syl) <= 40:
                texts.append(" ".join(syl))
    elif lang == "hi":
        import gzip
        deva = re.compile(r"^[ऀ-ॿ]+$")
        wiki = next((Path(a.dakshina) / "native_script_wikipedia").glob("*train.text*"))
        with (gzip.open(wiki, "rt", encoding="utf-8") if wiki.suffix == ".gz" else open(wiki, encoding="utf-8")) as f:
            for line in f:
                ws = [w for w in line.split() if deva.match(w)]
                if 2 <= len(ws) <= 30:
                    texts.append(" ".join(ws))
                if len(texts) >= a.extra:
                    break
    elif lang == "ar":
        import ar_measure as A
        for f in sorted(Path(a.darija).glob("*.parquet")):
            for r, w in (t for t in (A.tokens(x, y) for x, y in A.pairs_from(f)) if t):
                if A.unit(" ".join(r)) >= 0.12:
                    texts.append(" ".join(w))
    elif lang == "ko":
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ko_ime"))
        import measure as K  # tools/ko_ime/measure.py（試験は 0.1 未満、dev は 0.1〜0.15）
        for sid, s in K.read_tatoeba(a.tatoeba, "kor"):
            if K.KO_LINE.match(s) and " " in s and K.unit(20261106, "t" + sid) >= 0.15:
                texts.append(s)
        if a.wiki:
            for aid, s in K.read_wiki(a.wiki, a.extra):
                if K.unit(20261106, "w" + aid) >= 0.15:
                    texts.append(s)
        for s in cc100_lines(a.cc100, a.extra):
            s = " ".join(s.split())
            if K.KO_LINE.match(s) and " " in s and 8 <= len(s) <= 120:
                texts.append(s)
    texts = [t for t in texts if len(t) <= 200]
    pairs = [("", t) for t in texts]
    rows = [json.loads(l) for l in open(a.nbest_file, encoding="utf-8") if l.strip()]
    dev = [r for r in rows if r["split"] == "dev"][: a.test_limit]
    test = [r for r in rows if r["split"] == "test"][: a.test_limit]

    def evaluate(model, vocab):
        def neural(rows):
            out = []
            for r in rows:
                # 模型の長さ（max_len）を超える候補は先頭を残して切る（BOS・SEP の分を引く。候補どうしは同じだけ切れる）
                conts = [(vocab.encode(" ".join(c)) + [EOS])[: model.max_len - 3] for c in r["cands"]]
                out.append(score_batch(model, [BOS, SEP], conts))
            return out

        def measure(rows, scores, beta):
            ok = n = sent = 0
            for r, nn in zip(rows, scores):
                best = max(range(len(r["cands"])), key=lambda i: (r["base"][i] + beta * nn[i], -i))
                got, want = r["cands"][best], r["gold"]
                n += len(want)
                if lang == "ko":
                    # 分かち書きは語（어절）の切れ目が丸ごと合った数（ko_ime/measure.py の「語が合った」と同じ）
                    def spans(ws):
                        out, pos = set(), 0
                        for w in ws:
                            out.add((pos, pos + len(w)))
                            pos += len(w)
                        return out
                    ok += len(spans(want) & spans(got))
                else:
                    ok += sum(x == y for x, y in zip(want, got))
                sent += got == want
            return ok / max(n, 1), sent / max(len(rows), 1)

        dev_s, test_s = neural(dev), neural(test)
        betas = (0.0, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0)
        dev_res = {b: measure(dev, dev_s, b) for b in betas}
        beta = max(betas, key=lambda b: (dev_res[b][1], dev_res[b][0], -b))
        unit_name = {"vi": "音節", "ko": "語（어절）"}.get(lang, "語")
        oracle = sum(r["gold"] in r["cands"] for r in test) / max(len(test), 1)
        lines = [f"並べ替え（{lang}）: dev {len(dev)} 文で重みを決め、試験 {len(test)} 文で測る。候補 {len(rows[0]['cands']) if rows else 0} 個、"
                 f"正解が候補に入っている文 {oracle:.1%}"]
        lines += [f"  dev 重み {b}: {unit_name} {dev_res[b][0]:.1%}、文 {dev_res[b][1]:.1%}" for b in betas]
        w0, s0 = measure(test, test_s, 0.0)
        w1, s1 = measure(test, test_s, beta)
        lines.append(f"  試験 重み 0（今の方法）: {unit_name} {w0:.1%}、文 {s0:.1%}")
        lines.append(f"  試験 重み {beta}（dev で決めた）: {unit_name} {w1:.1%}、文 {s1:.1%}")
        return "\n".join(lines)
    return pairs, evaluate


TASKS = {"en": task_en, "vi": task_vi, "ko": task_ko, "hi": task_hi, "ar": task_ar, "zh": task_zh,
         "rr-vi": lambda a: task_rerank(a, "vi"), "rr-hi": lambda a: task_rerank(a, "hi"),
         "rr-ar": lambda a: task_rerank(a, "ar"), "rr-ko": lambda a: task_rerank(a, "ko")}


# ---------------------------------------------------------------- 学習
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--task", required=True, choices=sorted(TASKS))
    ap.add_argument("--tatoeba")
    ap.add_argument("--wiki")
    ap.add_argument("--cc100")
    ap.add_argument("--dakshina")
    ap.add_argument("--darija")
    ap.add_argument("--nbest-file", help="並べ替えの候補（*_measure.py --nbest-out）。rr-* の task で使う")
    ap.add_argument("--wiki-text", help="ウィキの文を 1 行 1 文にしたもの（中国語の足しの材料）")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--heads", type=int, default=4)
    ap.add_argument("--oversample", type=int, default=1, help="会話の文（Tatoeba）の組を何倍に重くするか（中国語）")
    ap.add_argument("--amp", action="store_true", help="GPU で半精度を使う（速くなる見込み。採る前に数字を比べる）")
    ap.add_argument("--test-limit", type=int, default=10 ** 9, help="試験の文の数の上限（動くかを確かめるとき用）")
    ap.add_argument("--extra", type=int, default=300000, help="足す材料の文の数（CC-100・作った組）")
    ap.add_argument("--minutes", type=float, default=200)
    ap.add_argument("--d", type=int, default=256)
    ap.add_argument("--layers", type=int, default=6)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--out", default="out")
    ap.add_argument("--load", help="学習済みの模型（.pt）を読んで、学習せずに測るだけにする")
    a = ap.parse_args()
    torch.manual_seed(20261106)
    torch.set_num_threads(max(1, torch.get_num_threads()))
    t0 = time.time()
    pairs, evaluate = TASKS[a.task](a)
    if a.load:
        # 学習済みの模型を読んで測るだけ（測る所で落ちたときの測り直し）
        ck = torch.load(a.load, map_location=a.device)
        vocab = Vocab.from_state(ck["vocab"])
        model = TinyGPT(**ck["config"]).to(a.device)
        model.load_state_dict(ck["state"])
        model.eval()
        t1 = time.time()
        log = [f"{a.task}: 学習済みの模型 {a.load} を読んで測る", evaluate(model, vocab) + f"（測るのに {time.time() - t1:.0f} 秒）"]
        print("\n".join(log), flush=True)
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{a.task}-result.txt").write_text("\n".join(log) + "\n", encoding="utf-8")
        return
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
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    # 測る前に模型を保存する（測る所で落ちても学習の分を失わない）
    torch.save({"config": model.config, "vocab": vocab.state(), "state": model.state_dict()}, out / f"{a.task}.pt")
    (out / f"{a.task}-result.txt").write_text("\n".join(log) + "\n", encoding="utf-8")
    t1 = time.time()
    log.append(evaluate(model, vocab) + f"（測るのに {time.time() - t1:.0f} 秒）")
    print("\n".join(log[-2:]), flush=True)
    (out / f"{a.task}-result.txt").write_text("\n".join(log) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
