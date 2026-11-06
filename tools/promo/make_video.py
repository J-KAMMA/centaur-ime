"""配布ページ用の紹介動画（30 秒、音なし）を作る。

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
    (3.0, 11.0, "前後の言葉で漢字を選ぶ", "同じ「はし」でも、文に合う字に",
     [("hashidegohanwotaberu", [("箸", True), ("でご飯を食べる", False)], None),
      ("hashiwowatattekouennheiku", [("橋", True), ("を渡って公園へ行く", False)], None)]),
    (11.0, 19.0, "英単語は切り替えずにそのまま", "日本語の中の英語を、打ったまま残す",
     [("githubnipushshita", [("GitHub", True), ("に", False), ("push", True), ("した", False)], None),
      ("ashitanomeetingha10jikara", [("明日の", False), ("meeting", True), ("は10時から", False)], None)]),
    (19.0, 25.0, "打ち間違いも文脈で直す", "余計なキーが入っても、正しい文に",
     [("hashidegohaxnwotaberu", [("箸でご飯を食べる", False)], 11)]),
]
END = 30.0
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
    s2 = "文脈で選ぶ日本語入力"
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
        d.text((96, by + 8), "打ったキー", font=F.get(22), fill=mix(BG, SUB, fade))
        x = 230
        for j, ch in enumerate(typed):
            col = WARN if typo is not None and j == typo else INK
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
        if typo is not None and len(typed) > typo:
            d.text((96, by + 52), "← 余計な x が入った", font=F.get(22), fill=mix(BG, WARN, fade))


def draw_end(im, d, F, t):
    lt = t - 25.0
    a = ease(lt / 0.6)
    lg = logo(150, a)
    im.paste(lg, ((W - 150) // 2, 40), lg)
    f1 = F.get(64, True)
    s = "Centaur IME 日本語"
    d.text(((W - text_w(d, s, f1)) / 2, 200 - 16 * (1 - a)), s, font=f1, fill=mix(BG, INK, a))
    lines = ["変換はすべてパソコンの中で", "Windows 11 ・ macOS ・ Linux（試用）"]
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
    elif t < 25.0:
        for sc in SCENES:
            if sc[0] <= t < sc[1]:
                draw_scene(d, F, t, sc)
    else:
        draw_end(im, d, F, t)
    # 下の進み具合の線
    d.rectangle((0, H - 4, W * t / END, H), fill=ACCENT)
    return im


def sound_events():
    """絵と同じ時刻の音の出来事（draw_scene の時刻の計算と合わせる）。"""
    ev = [("title", 0.3), ("end", 25.0)]
    for start, end, _, _, examples in SCENES:
        starts, _ = example_times(start, end, len(examples))
        for es, (keys, _, _) in zip(starts, examples):
            for k in range(len(keys)):
                ev.append(("key", es + (k + 1) / 17.0))
            type_dur = len(keys) / 17.0
            ev.append(("space", es + type_dur + 0.02))
            ev.append(("convert", es + type_dur + 0.45))
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
