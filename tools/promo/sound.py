"""紹介動画の音。全部この場で合成する（借りた音源を使わないので、使う条件の心配がない）。

fx:   キーの音、Space の音、変換の音
full: fx ＋ 静かな背景の和音
"""
import wave

import numpy as np

SR = 48000


def _env(n, attack, decay):
    t = np.arange(n) / SR
    a = np.minimum(t / max(attack, 1e-4), 1.0)
    return a * np.exp(-t / decay)


def key_click(rng):
    n = int(0.045 * SR)
    noise = rng.standard_normal(n)
    # 高い音を少し落とした短い雑音（打鍵の「カタ」）
    k = 6
    noise = np.convolve(noise, np.ones(k) / k, mode="same")
    t = np.arange(n) / SR
    body = np.sin(2 * np.pi * rng.uniform(1700, 2300) * t) * 0.35
    return (noise + body) * _env(n, 0.0008, 0.009) * 0.30


def space_click(rng):
    n = int(0.09 * SR)
    noise = np.convolve(rng.standard_normal(n), np.ones(14) / 14, mode="same")
    t = np.arange(n) / SR
    body = np.sin(2 * np.pi * 420 * t) * 0.6
    return (noise + body) * _env(n, 0.001, 0.018) * 0.40


def chime(freqs, length=0.9, vol=0.16):
    n = int(length * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for j, f in enumerate(freqs):
        start = int(j * 0.06 * SR)
        m = n - start
        tt = t[:m]
        tone = np.sin(2 * np.pi * f * tt) + 0.25 * np.sin(2 * np.pi * 2 * f * tt)
        out[start:] += tone * _env(m, 0.004, 0.28)
    return out * vol / max(len(freqs), 1)


def pad(length):
    """ゆっくり替わる 4 つの和音（Cmaj7 → Am7 → Fmaj7 → G6）。小さく鳴らす。"""
    n = int(length * SR)
    t = np.arange(n) / SR
    chords = [[261.63, 329.63, 392.00, 493.88], [220.00, 261.63, 329.63, 392.00],
              [174.61, 220.00, 261.63, 329.63], [196.00, 246.94, 293.66, 329.63]]
    seg = length / 4
    out = np.zeros(n)
    for i, ch in enumerate(chords):
        s0, s1 = int(i * seg * SR), int(min((i + 1) * seg + 1.0, length) * SR)
        tt = t[s0:s1] - t[s0]
        m = s1 - s0
        x = np.zeros(m)
        for f in ch:
            for det in (-0.6, 0.6):
                x += np.sin(2 * np.pi * (f + det) * tt)
        fade = np.minimum(tt / 1.2, 1.0) * np.minimum((m / SR - tt) / 1.2, 1.0)
        out[s0:s1] += x * np.clip(fade, 0, 1)
    # 全体の入りと終わり
    g = np.minimum(t / 1.5, 1.0) * np.clip((length - t) / 2.0, 0, 1)
    return out * g * 0.012


def render(events, length, mode, path, seed=20261106):
    rng = np.random.default_rng(seed)
    n = int(length * SR)
    mixbuf = np.zeros(n)

    def put(sig, at):
        i = int(at * SR)
        if i >= n:
            return
        j = min(n, i + len(sig))
        mixbuf[i:j] += sig[: j - i]

    for kind, at in events:
        if kind == "key":
            put(key_click(rng), at)
        elif kind == "space":
            put(space_click(rng), at)
        elif kind == "convert":
            put(chime([880.0, 1318.5]), at)
        elif kind == "title":
            put(chime([523.25, 659.25, 783.99], 1.6, 0.22), at)
        elif kind == "end":
            put(chime([392.0, 523.25, 659.25, 1046.5], 2.0, 0.24), at)
    if mode == "full":
        mixbuf += pad(length)
    peak = np.max(np.abs(mixbuf))
    if peak > 0.89:
        mixbuf *= 0.89 / peak
    data = (np.clip(mixbuf, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())
