"""配布ページ用の紹介動画（45 秒）を作る。

変換の例は全体試験（基準の結果）で実際に出た出力だけを使う。例を替えるときも試験の出力から選ぶ。

  python make_video.py --font-r <普通の字体> --font-b <太字の字体> --out promo.mp4      動画（ffmpeg が要る）
  python make_video.py --font-r ... --font-b ... --stills 2,6,14,21,27 --out dir     静止画だけ（下見用）
"""
import argparse
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1280, 720, 30
BG = (246, 245, 242)
INK = (32, 33, 36)
SUB = (110, 112, 118)
ACCENT = (37, 99, 235)
MARK = (255, 226, 140)
WARN = (220, 38, 38)
CARD = (255, 255, 255)
LINE = (226, 226, 230)

# 場面: (始まり秒, 終わり秒, 見出し, 説明, 例の並び)
# 例: (打ったキー, 結果の区切り [(文字, 目立たせるか)], 打ち間違いのキーの位置)
SCENES = [
    (3.0, 11.0, "同じ読みでも、文に合う漢字に", "「はし」を、食べる話なら箸、渡る話なら橋に",
     [("hashidegohanwotaberu", [("箸", True), ("でご飯を食べる", False)], None),
      ("hashiwowatattekouennheiku", [("橋", True), ("を渡って公園へ行く", False)], None)]),
    (11.0, 19.0, "英単語は、そのまま打てる", "入力を英語に切り替えなくても、英単語は英語のまま",
     [("githubnipushshita", [("GitHub", True), ("に", False), ("push", True), ("した", False)], None),
      ("ashitanomeetingha10jikara", [("明日の", False), ("meeting", True), ("は10時から", False)], None)]),
    (19.0, 25.0, "打ち間違いも、文から直す", "余計なキーが混じっても、意味の通る文に",
     [("hashidegohaxnwotaberu", [("箸でご飯を食べる", False)], 11)]),
]
# 先出しの場面（1.172）: 打つのを止めると、候補の1番目にスペースの結果が出る。
# 例は全体試験 space-preview（42629255733）で、先頭の候補とスペースの結果が同じだった文
PREVIEW = (25.0, 31.0, "手を止めると、変換の結果が先に出る", "スペースを押す前に、候補の1番目にスペースと同じ結果",
           [("atsuiochawonomu", "あついおちゃをのむ", "熱いお茶を飲む"),
            ("atsuihonwoyonda", "あついほんをよんだ", "厚い本を読んだ")])
STATS_AT = 31.0  # 性能の場面の始まり
END_AT = 40.5    # 終わりの画面の始まり
END = 45.0
# 性能: 例文を打って漢字を取り違えた文の割合（2026-11 の計測。tools の比べの結果。少ないほど良い）
# (始まり, 終わり, 見出し, 説明, [(名前, 値, 自分か)], 棒の最大値)
STATS = [
    (STATS_AT, 35.75, "まるごと正しく変換できた文が、いちばん多い", "例文を打って、元の文と同じになった割合（多いほど良い）",
     [("Mozc", 61.2, False), ("MS-IME", 61.4, False), ("Centaur IME", 73.9, True)], 80.0),
    (35.75, END_AT, "漢字の取り違えが、およそ半分", "例文を打って、漢字を取り違えた文の割合（少ないほど良い）",
     [("Mozc", 13.6, False), ("MS-IME", 10.8, False), ("Centaur IME", 5.6, True)], 15.0),
]
STATS_NOTE = ["Tatoeba の日本語の例文 2,979 文で計測（2026年11月）。表記の揺れ（分かる/わかる）は同じとみなす。",
              "MS-IME は Windows 11 の Microsoft IME"]
LOGO_SRC = Path(__file__).resolve().parents[1] / "data" / "compound-icon.png"  # 製品の印（半人半馬の射手）
_logo_cache = {}


def logo(size, alpha):
    """白地の黒い線の絵を、透きとおった地の INK の色にして返す。"""
    if size not in _logo_cache:
        g = Image.open(LOGO_SRC).convert("L").resize((size, size), Image.LANCZOS)
        im = Image.new("RGBA", (size, size), INK + (0,))
        im.putalpha(g.point(lambda v: 255 - v))
        _logo_cache[size] = im
    im = _logo_cache[size]
    if alpha >= 1:
        return im
    a = im.getchannel("A").point(lambda v: int(v * alpha))
    out = im.copy()
    out.putalpha(a)
    return out


CREDIT = ""  # 声を使うとき「音声: VOICEVOX:四国めたん」（--voice で入る）


def ease(x):
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def mix(c1, c2, a):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * a) for i in range(3))


class Fonts:
    def __init__(self, r, b):
        self.r, self.b = r, b
        self.cache = {}

    def get(self, size, bold=False):
        key = (size, bold)
        if key not in self.cache:
            self.cache[key] = ImageFont.truetype(self.b if bold else self.r, size)
        return self.cache[key]


def text_w(d, s, f):
    return d.textlength(s, font=f)


def draw_title(im, d, F, t):
    a = ease(t / 0.8) * (1 - ease((t - 2.6) / 0.4))
    col = mix(BG, INK, a)
    lg = logo(230, a)
    im.paste(lg, ((W - 230) // 2, int(70 - 14 * (1 - ease(t / 0.8)))), lg)
    f1 = F.get(76, True)
    s = "Centaur IME"
    d.text(((W - text_w(d, s, f1)) / 2, 320 - 20 * (1 - ease((t - 0.15) / 0.8))), s, font=f1, fill=col)
    f2 = F.get(34)
    s2 = "文の流れを読んで変換する日本語入力"
    d.text(((W - text_w(d, s2, f2)) / 2, 430), s2, font=f2, fill=mix(BG, SUB, a))
    bar = 160 * ease((t - 0.4) / 0.8) * (1 - ease((t - 2.6) / 0.4))
    d.rounded_rectangle(((W - bar) / 2, 500, (W + bar) / 2, 506), 3, fill=mix(BG, ACCENT, a))


def draw_window(d, F, x0, y0, x1, y1):
    d.rounded_rectangle((x0 + 4, y0 + 6, x1 + 4, y1 + 6), 18, fill=(232, 231, 228))
    d.rounded_rectangle((x0, y0, x1, y1), 18, fill=CARD, outline=LINE)
    for i, c in enumerate([(255, 95, 87), (254, 188, 46), (40, 200, 64)]):
        d.ellipse((x0 + 22 + i * 24, y0 + 20, x0 + 36 + i * 24, y0 + 34), fill=c)
    d.line((x0, y0 + 52, x1, y0 + 52), fill=LINE, width=1)


def example_times(start, end, n):
    span = (end - start - 0.6) / n
    return [start + 0.6 + i * span for i in range(n)], span


def draw_scene(d, F, t, scene):
    start, end, title, desc, examples = scene
    lt = t - start
    fade = ease(lt / 0.4) * (1 - ease((t - (end - 0.35)) / 0.35))
    # 見出し
    d.text((96, 70 - 10 * (1 - ease(lt / 0.5))), title, font=F.get(46, True), fill=mix(BG, INK, fade))
    d.text((98, 136), desc, font=F.get(26), fill=mix(BG, SUB, fade))
    # 窓
    x0, y0, x1, y1 = 96, 200, W - 96, 520
    draw_window(d, F, x0, y0, x1, y1)
    starts, span = example_times(start, end, len(examples))
    fres = F.get(44)
    fkey = F.get(30)
    key_line = None
    for i, (keys, segs, typo) in enumerate(examples):
        es = starts[i]
        if t < es:
            continue
        et = t - es
        type_dur = len(keys) / 17.0
        typed = keys[: int(min(len(keys), et * 17.0))]
        conv_t = type_dur + 0.45
        line_y = y0 + 84 + i * 96
        if et < conv_t + 0.05:
            key_line = (typed, typo, et - type_dur)
            # 打っている間は、窓の中にカーソルだけ
            if int(et * 2.5) % 2 == 0:
                d.rectangle((x0 + 48, line_y + 4, x0 + 51, line_y + 52), fill=ACCENT)
        else:
            a = ease((et - conv_t) / 0.35)
            x = x0 + 48
            for s, hi in segs:
                w = text_w(d, s, fres)
                if hi:
                    d.rounded_rectangle((x - 3, line_y + 2, x + w + 3, line_y + 58), 8, fill=mix(CARD, MARK, a))
                d.text((x, line_y + 4 + 8 * (1 - a)), s, font=fres, fill=mix(CARD, INK, a))
                x += w
            if i == len(examples) - 1 and et > conv_t + 1.2:
                key_line = None
            elif i == len(examples) - 1:
                key_line = (keys, typo, 99)
    # 打ったキーの帯
    if key_line:
        typed, typo, after = key_line
        by = 560
        label = "打ったローマ字"
        d.text((96, by + 8), label, font=F.get(22), fill=mix(BG, SUB, fade))
        x = 96 + text_w(d, label, F.get(22)) + 24  # 見出しの幅に合わせて、重ならないように
        typo_x = None
        for j, ch in enumerate(typed):
            col = WARN if typo is not None and j == typo else INK
            if col == WARN:
                typo_x = x + text_w(d, ch, fkey) / 2
            d.text((x, by), ch, font=fkey, fill=mix(BG, col, fade))
            x += text_w(d, ch, fkey)
        if 0 < after < 99:
            a = ease(after / 0.2)
            bx = x + 24
            bw = 120
            d.rounded_rectangle((bx, by - 2, bx + bw, by + 42), 8, fill=mix(BG, ACCENT, a))
            s = "Space"
            d.text((bx + (bw - text_w(d, s, F.get(24, True))) / 2, by + 5), s, font=F.get(24, True),
                   fill=mix(BG, (255, 255, 255), a))
        if typo_x is not None:
            s = "↑ 余計な x"
            f = F.get(22)
            d.text((typo_x - text_w(d, "↑", f) / 2, by + 48), s, font=f, fill=mix(BG, WARN, fade))


def preview_times(ex_start, keys):
    """1つの例の時刻: (打ち終わり, 候補が出る)。"""
    type_end = ex_start + len(keys) / 17.0
    return type_end, type_end + 0.55


def draw_preview(d, F, t):
    start, end, title, desc, examples = PREVIEW
    lt = t - start
    fade = ease(lt / 0.4) * (1 - ease((t - (end - 0.35)) / 0.35))
    d.text((96, 70 - 10 * (1 - ease(lt / 0.5))), title, font=F.get(46, True), fill=mix(BG, INK, fade))
    d.text((98, 136), desc, font=F.get(26), fill=mix(BG, SUB, fade))
    x0, y0, x1, y1 = 96, 200, W - 96, 520
    draw_window(d, F, x0, y0, x1, y1)
    starts, span = example_times(start, end, len(examples))
    i = max(k for k in range(len(examples)) if k == 0 or t >= starts[k])
    keys, kana, result = examples[i]
    es = starts[i]
    if t < es:
        return
    et = t - es
    type_end, pop_at = preview_times(es, keys)
    out = ease((t - (es + span - 0.3)) / 0.3) if i < len(examples) - 1 else 0.0
    vis = fade * (1 - out)
    fpre = F.get(44)
    lx, ly = x0 + 48, y0 + 92
    # 打っている途中の読み（下線つき）。ローマ字の進みに合わせて伸ばす
    n = int(len(kana) * min(1.0, et * 17.0 / len(keys)))
    s = kana[:n]
    w = text_w(d, s, fpre)
    d.text((lx, ly), s, font=fpre, fill=mix(CARD, INK, vis))
    d.line((lx, ly + 60, lx + w, ly + 60), fill=mix(CARD, INK, vis), width=2)
    if t < pop_at and int(et * 2.5) % 2 == 0:
        d.rectangle((lx + w + 2, ly + 4, lx + w + 5, ly + 52), fill=mix(CARD, ACCENT, vis))
    # 手を止めた印
    if t >= type_end:
        p = ease((t - type_end) / 0.3)
        f = F.get(22)
        lab = "手を止める"
        d.text((lx + w + 24, ly + 16), lab, font=f, fill=mix(CARD, SUB, vis * p))
    # 候補の窓
    if t >= pop_at:
        a = ease((t - pop_at) / 0.3) * vis
        fc = F.get(36)
        px, py = lx, ly + 84
        cw = text_w(d, "1  " + result, fc) + 48
        d.rounded_rectangle((px + 3, py + 5, px + cw + 3, py + 75), 10, fill=mix(CARD, (226, 226, 230), a))
        d.rounded_rectangle((px, py, px + cw, py + 70), 10, fill=mix(CARD, (255, 255, 255), a), outline=mix(CARD, LINE, a))
        d.rounded_rectangle((px + 6, py + 6, px + cw - 6, py + 64), 8, fill=mix(CARD, MARK, a))
        d.text((px + 20, py + 12), "1", font=fc, fill=mix(CARD, SUB, a))
        d.text((px + 20 + text_w(d, "1  ", fc), py + 12), result, font=fc, fill=mix(CARD, INK, a))
        f = F.get(26, True)
        tag = "＝ スペースを押したときと同じ"
        d.text((px + cw + 28, py + 20), tag, font=f, fill=mix(CARD, ACCENT, a))
    # 打ったキーの帯
    by = 560
    label = "打ったローマ字"
    fk = F.get(30)
    d.text((96, by + 8), label, font=F.get(22), fill=mix(BG, SUB, fade))
    typed = keys[: int(min(len(keys), et * 17.0))]
    d.text((96 + text_w(d, label, F.get(22)) + 24, by), typed, font=fk, fill=mix(BG, INK, vis))


def draw_stats(d, F, t, stat):
    start, end, title, desc, rows, vmax = stat
    lt = t - start
    fade = ease(lt / 0.4) * (1 - ease((t - (end - 0.35)) / 0.35))
    d.text((96, 70 - 10 * (1 - ease(lt / 0.5))), title, font=F.get(46, True), fill=mix(BG, INK, fade))
    d.text((98, 136), desc, font=F.get(26), fill=mix(BG, SUB, fade))
    fl, fv = F.get(32, True), F.get(34, True)
    x0, bar_max, top = 330, 640, 230
    for i, (name, val, ours) in enumerate(rows):
        y = top + i * 100
        g = ease((lt - 0.4 - i * 0.35) / 0.7)
        col = ACCENT if ours else (176, 178, 184)
        d.text((x0 - 24 - text_w(d, name, fl), y + 8), name, font=fl, fill=mix(BG, INK if ours else SUB, fade))
        w = bar_max * (val / vmax) * g
        d.rounded_rectangle((x0, y, x0 + max(w, 1), y + 56), 10, fill=mix(BG, col, fade))
        s = f"{val * g:.1f}%"
        d.text((x0 + w + 18, y + 7), s, font=fv, fill=mix(BG, ACCENT if ours else SUB, fade * g))
    for i, s in enumerate(STATS_NOTE):
        d.text((96, H - 84 + i * 26), s, font=F.get(18), fill=mix(BG, SUB, fade))


def draw_end(im, d, F, t):
    lt = t - END_AT
    a = ease(lt / 0.6)
    lg = logo(150, a)
    im.paste(lg, ((W - 150) // 2, 40), lg)
    f1 = F.get(64, True)
    s = "Centaur IME 日本語"
    d.text(((W - text_w(d, s, f1)) / 2, 200 - 16 * (1 - a)), s, font=f1, fill=mix(BG, INK, a))
    lines = ["無料。変換はすべてパソコンの中で", "Windows 11 ・ macOS ・ Linux（試用）"]
    for i, s in enumerate(lines):
        b = ease((lt - 0.4 - i * 0.25) / 0.5)
        f = F.get(32)
        d.text(((W - text_w(d, s, f)) / 2, 320 + i * 56), s, font=f, fill=mix(BG, SUB, b))
    c = ease((lt - 1.2) / 0.5)
    s = "github.com/J-KAMMA/centaur-ime"
    f = F.get(30, True)
    w = text_w(d, s, f)
    d.rounded_rectangle(((W - w) / 2 - 24, 480, (W + w) / 2 + 24, 536), 12, fill=mix(BG, ACCENT, c))
    d.text(((W - w) / 2, 490), s, font=f, fill=mix(BG, (255, 255, 255), c))
    if CREDIT:
        f = F.get(20)
        d.text((W - 40 - text_w(d, CREDIT, f), H - 44), CREDIT, font=f, fill=mix(BG, SUB, c))


def frame(F, t):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    if t < 3.0:
        draw_title(im, d, F, t)
    elif PREVIEW[0] <= t < PREVIEW[1]:
        draw_preview(d, F, t)
    elif t < STATS_AT:
        for sc in SCENES:
            if sc[0] <= t < sc[1]:
                draw_scene(d, F, t, sc)
    elif t < END_AT:
        for st in STATS:
            if st[0] <= t < st[1]:
                draw_stats(d, F, t, st)
    else:
        draw_end(im, d, F, t)
    # 下の進み具合の線
    d.rectangle((0, H - 4, W * t / END, H), fill=ACCENT)
    return im


def sound_events():
    """絵と同じ時刻の音の出来事（draw_scene の時刻の計算と合わせる）。"""
    ev = [("title", 0.3), ("end", END_AT)]
    for start, end, _, _, examples in SCENES:
        starts, _ = example_times(start, end, len(examples))
        for es, (keys, _, _) in zip(starts, examples):
            for k in range(len(keys)):
                ev.append(("key", es + (k + 1) / 17.0))
            type_dur = len(keys) / 17.0
            ev.append(("space", es + type_dur + 0.02))
            ev.append(("convert", es + type_dur + 0.45))
    starts, _ = example_times(PREVIEW[0], PREVIEW[1], len(PREVIEW[4]))
    for es, (keys, _, _) in zip(starts, PREVIEW[4]):
        for k in range(len(keys)):
            ev.append(("key", es + (k + 1) / 17.0))
        ev.append(("convert", preview_times(es, keys)[1]))
    return ev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--font-r", required=True)
    ap.add_argument("--font-b", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--stills", default="")
    ap.add_argument("--audio", choices=["none", "fx", "full"], default="none")
    ap.add_argument("--voice", default="", help="narrate.py の出力の置き場")
    a = ap.parse_args()
    global CREDIT
    voices = []
    if a.voice:
        import json
        meta = json.loads((Path(a.voice) / "lines.json").read_text(encoding="utf-8"))
        CREDIT = "音声: " + meta["credit"]
        voices = [(m["at"], Path(a.voice) / m["file"]) for m in meta["lines"]]
    F = Fonts(a.font_r, a.font_b)
    if a.stills:
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        for s in a.stills.split(","):
            frame(F, float(s)).save(out / f"still-{float(s):05.1f}.png")
        return
    audio_in, audio_out = [], []
    if a.audio != "none":
        from sound import render
        wav = Path(a.out).with_suffix(".wav")
        render(sound_events(), END, a.audio, wav, voices)
        audio_in = ["-i", str(wav)]
        audio_out = ["-c:a", "aac", "-b:a", "160k", "-shortest"]
    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                          "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", *audio_in, "-c:v", "libx264", "-preset", "slow",
                          "-crf", "20", "-pix_fmt", "yuv420p", *audio_out, "-movflags", "+faststart", a.out],
                         stdin=subprocess.PIPE)
    for i in range(int(END * FPS)):
        p.stdin.write(frame(F, i / FPS).tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise SystemExit("ffmpeg が失敗")
    print("書いた", a.out)


if __name__ == "__main__":
    main()
