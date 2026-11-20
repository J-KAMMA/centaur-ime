"""ベトナム語の Telex（キーの打ち方）と、記号つきの文字の行き来。

  compose("tieengs vieetj") → "tiếng việt"
  to_telex("tiếng") → "tieengs"
打ち方: aa→â aw→ă ee→ê oo→ô ow→ơ uw→ư dd→đ（w は直前に近い a o u に付く）。
声調は語のどこで打ってもよい: s=sắc f=huyền r=hỏi x=ngã j=nặng、z=声調を外す。同じ声調のキーを 2 度打つと
声調を外してその字を入れる（ss → s）。声調を置く母音は新しい書き方（oa oe uy は後ろ、ươ は ơ）。
大文字は打ったとおりに残す。C++ の native/centaur_core/telex.cc と同じ計算（tools/vi_ime/telex_parity.py で確かめる）。
"""
BASES = "aăâeêioôơuưy"
TONED = ["aáàảãạ", "ăắằẳẵặ", "âấầẩẫậ", "eéèẻẽẹ", "êếềểễệ", "iíìỉĩị", "oóòỏõọ", "ôốồổỗộ", "ơớờởỡợ",
         "uúùủũụ", "ưứừửữự", "yýỳỷỹỵ"]
TONE_KEYS = "sfrxj"  # 1..5
DOUBLE = {"a": "â", "e": "ê", "o": "ô", "d": "đ"}
HORN = {"a": "ă", "o": "ơ", "u": "ư"}
MODIFIED = set("ăâêôơư")

# 字 → (基の字, 声調 0..5)
SPLIT = {}
for row in TONED:
    for tone, ch in enumerate(row):
        SPLIT[ch] = (row[0], tone)


def _lower(ch):
    return ch.lower()


def tone_position(letters):
    """声調を置く母音の位置（無ければ -1）。letters は声調の無い小文字の字の並び。"""
    v = [i for i, ch in enumerate(letters) if ch in BASES]
    if not v:
        return -1
    word = "".join(letters)
    # qu・gi の u・i は子音として扱う
    if word.startswith("qu") and 1 in v and len(v) > 1:
        v.remove(1)
    if word.startswith("gi") and 1 in v and len(v) > 1:
        v.remove(1)
    # 最初のひと続きの母音
    nucleus = [v[0]]
    for i in v[1:]:
        if i == nucleus[-1] + 1:
            nucleus.append(i)
        else:
            break
    mod = [i for i in nucleus if letters[i] in MODIFIED]
    if mod:
        if any(letters[i] == "ơ" for i in mod):
            return next(i for i in mod if letters[i] == "ơ")
        return mod[-1]
    if len(nucleus) == 1:
        return nucleus[0]
    if nucleus[-1] + 1 < len(letters):  # 後ろに子音がある
        return nucleus[-1]
    if len(nucleus) == 3:
        return nucleus[1]
    pair = letters[nucleus[0]] + letters[nucleus[1]]
    return nucleus[1] if pair in ("oa", "oe", "uy") else nucleus[0]


def render(letters, upper, tone):
    out = list(letters)
    if tone:
        p = tone_position(letters)
        if p >= 0:
            out[p] = TONED[BASES.index(letters[p])][tone]
    return "".join(c.upper() if u else c for c, u in zip(out, upper))


def compose_word(keys):
    letters, upper = [], []  # 声調の無い小文字の字と、大文字だったか
    tone = 0
    for k in keys:
        lk = _lower(k)
        if lk in TONE_KEYS or lk == "z":
            t = TONE_KEYS.index(lk) + 1 if lk in TONE_KEYS else 0
            has_vowel = tone_position(letters) >= 0
            if has_vowel and lk != "z" and tone != t:
                tone = t
                continue
            if has_vowel and lk == "z" and tone:
                tone = 0
                continue
            if has_vowel and tone == t and lk != "z":
                tone = 0  # 同じ声調を 2 度: 外してその字を入れる
            letters.append(lk)
            upper.append(k != lk)
            continue
        if lk in DOUBLE and letters and letters[-1] == lk:
            letters[-1] = DOUBLE[lk]
            continue
        if lk == "w":
            # 一番近い a o u（まだ記号の無いもの）に付ける。ươ の形は u と o の両方
            for i in range(len(letters) - 1, -1, -1):
                if letters[i] in HORN:
                    if letters[i] == "o" and i > 0 and letters[i - 1] == "u":
                        letters[i - 1] = "ư"
                    letters[i] = HORN[letters[i]]
                    break
                if letters[i] in BASES:
                    i = -1
                    break
            else:
                i = -1
            if i >= 0:
                continue
            letters.append("w")
            upper.append(k != lk)
            continue
        letters.append(lk)
        upper.append(k != lk)
    return render(letters, upper, tone)


def compose(keys):
    """英字の続きを 1 語として組み立て、ほかの字はそのまま通す。"""
    out, word = [], []
    for k in keys:
        if k.isascii() and k.isalpha():
            word.append(k)
        else:
            if word:
                out.append(compose_word(word))
                word = []
            out.append(k)
    if word:
        out.append(compose_word(word))
    return "".join(out)


def to_telex(word):
    """記号つきの語を Telex のキーにする（声調は語の終わりで打つ）。"""
    keys, tone = [], 0
    for ch in word:
        lower = ch.lower()
        base, t = SPLIT.get(lower, (lower, 0))
        tone = tone or t
        up = ch != lower
        seq = {"â": "aa", "ê": "ee", "ô": "oo", "đ": "dd", "ă": "aw", "ơ": "ow", "ư": "uw"}.get(base, base)
        keys.append(seq.upper() if up else seq)
    if tone:
        keys.append(TONE_KEYS[tone - 1])
    return "".join(keys)
