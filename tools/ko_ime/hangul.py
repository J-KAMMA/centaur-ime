"""ハングルと 2 ボル式（두벌식）のキーの行き来。

  to_keys("안녕")  → "dkssud"   （ハングルの字を、打つキーの並びに直す）
  compose("dkssud") → "안녕"     （キーの並びを、2 ボル式の打ち方どおりに組み立てる）
大文字は Shift（ㄲ ㄸ ㅃ ㅆ ㅉ ㅒ ㅖ）。組み立ては、母音が続くと前の字の終声を次の字の初声に移す、ふつうの決まり。
"""
INITIALS = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
VOWELS = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
FINALS = ["", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ", "ㄻ", "ㄼ", "ㄽ", "ㄾ", "ㄿ", "ㅀ", "ㅁ", "ㅂ", "ㅄ",
          "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"]
KEY = {"ㄱ": "r", "ㄲ": "R", "ㄴ": "s", "ㄷ": "e", "ㄸ": "E", "ㄹ": "f", "ㅁ": "a", "ㅂ": "q", "ㅃ": "Q", "ㅅ": "t",
       "ㅆ": "T", "ㅇ": "d", "ㅈ": "w", "ㅉ": "W", "ㅊ": "c", "ㅋ": "z", "ㅌ": "x", "ㅍ": "v", "ㅎ": "g",
       "ㅏ": "k", "ㅐ": "o", "ㅑ": "i", "ㅒ": "O", "ㅓ": "j", "ㅔ": "p", "ㅕ": "u", "ㅖ": "P", "ㅗ": "h", "ㅛ": "y",
       "ㅜ": "n", "ㅠ": "b", "ㅡ": "m", "ㅣ": "l"}
JAMO = {v: k for k, v in KEY.items()}
# 2 つのキーで打つ母音と終声
VOWEL2 = {"ㅘ": "ㅗㅏ", "ㅙ": "ㅗㅐ", "ㅚ": "ㅗㅣ", "ㅝ": "ㅜㅓ", "ㅞ": "ㅜㅔ", "ㅟ": "ㅜㅣ", "ㅢ": "ㅡㅣ"}
FINAL2 = {"ㄳ": "ㄱㅅ", "ㄵ": "ㄴㅈ", "ㄶ": "ㄴㅎ", "ㄺ": "ㄹㄱ", "ㄻ": "ㄹㅁ", "ㄼ": "ㄹㅂ", "ㄽ": "ㄹㅅ", "ㄾ": "ㄹㅌ",
          "ㄿ": "ㄹㅍ", "ㅀ": "ㄹㅎ", "ㅄ": "ㅂㅅ"}
JOIN_V = {v: k for k, v in VOWEL2.items()}
JOIN_F = {v: k for k, v in FINAL2.items()}


def is_syllable(ch):
    return "가" <= ch <= "힣"


def to_jamo(text):
    out = []
    for ch in text:
        if is_syllable(ch):
            i = ord(ch) - 0xAC00
            out.append(INITIALS[i // 588])
            v = VOWELS[(i % 588) // 28]
            out.append(VOWEL2.get(v, v))
            f = FINALS[i % 28]
            out.append(FINAL2.get(f, f))
        else:
            out.append(ch)
    return "".join(out)


def to_keys(text):
    return "".join(KEY.get(j, j) for j in to_jamo(text))


def _syl(l, v, f=""):
    return chr(0xAC00 + INITIALS.index(l) * 588 + VOWELS.index(v) * 28 + FINALS.index(f))


def compose(keys):
    """キーの並びを組み立てる。組み立てられない所は字母のまま残す。"""
    jamo = [JAMO.get(k, k) for k in keys]
    out = []
    l = v = f = ""  # 組み立て中の初声・中声・終声

    def flush():
        nonlocal l, v, f
        if l and v:
            out.append(_syl(l, v, f))
        else:
            out.extend(x for x in (l, v, f) if x)
        l = v = f = ""

    for j in jamo:
        if j in VOWELS:
            if l and not v:
                v = j
            elif v and not f and (v + j) in JOIN_V:
                v = JOIN_V[v + j]
            elif f:
                # 終声を次の字の初声に移す（겹받침なら後ろの字母だけ移す）
                if f in FINAL2:
                    keep, move = FINAL2[f]
                    f = keep
                else:
                    move, f = f, ""
                flush()
                l, v = move, j
            else:
                flush()
                out.append(j)
        elif j in INITIALS:
            if l and v and not f and j in FINALS:
                f = j
            elif f and (f + j) in JOIN_F:
                f = JOIN_F[f + j]
            else:
                flush()
                l = j
        else:
            flush()
            out.append(j)
    flush()
    return "".join(out)
