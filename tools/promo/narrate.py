"""紹介動画の声を Kokoro（Kokoro-82M、声 jf_alpha、Apache-2.0）で作る。

ぽるるの動画と同じ声（jf_alpha）。高さはぽるる（1.3 倍）と違い、元のまま。Kokoro の重みは Apache-2.0 で、作った声に
表記の決まりは無い（VOICEVOX の四国めたんは「VOICEVOX:四国めたん」の表記が要った）。
手元（C:\\models\\kokoro\\venv）でも GitHub の流れの中でも同じに動く。

  python narrate.py --out voice/      voice/line-<番号>.wav と voice/lines.json を書く
"""
import argparse
import json
import wave
from pathlib import Path

import numpy as np
import soundfile as sf
from kokoro import KPipeline

VOICE = "jf_alpha"
CREDIT = ""  # 表記は要らない

# (始まり秒, 読む文, 読ませる文)。読ませる文は読み違いを避けるためのかな書き
LINES = [
    (0.3, "Centaur IME。文の流れを読んで変換する、日本語入力です。", "ケンタウロス・アイエムイー。文の流れを読んで変換する日本語入力です。"),
    (6.0, "同じ読みでも、前後の言葉から、合う漢字を選びます。", "同じ読みでも、前後の言葉から、合う漢字を選びます。"),
    (11.3, "英単語は、入力を切り替えずに、そのまま打てます。", "英単語は、入力を切り替えずに、そのまま打てます。"),
    (19.3, "打ち間違いも、文の流れから直します。", "打ち間違いも、文の流れから直します。"),
    (25.3, "手を止めると、変換の結果が先に出ます。", "手を止めると、変換の結果が先に出ます。"),
    (31.4, "まるごと正しく変換できた文は、七十七パーセントです。", "まるごと正しく変換できた文は、七十七パーセントです。"),
    (36.15, "漢字の取り違えは、ほかの IME の半分以下です。", "漢字の取り違えは、ほかのアイエムイーの、半分以下です。"),
    (40.9, "無料で、変換はすべてパソコンの中で行います。", "無料で、変換はすべてパソコンの中で行います。"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--pitch", type=float, default=1.0, help="声の高さ（ぽるるは 1.3。紹介動画は元の高さ）")
    ap.add_argument("--tempo", type=float, default=1.15, help="話す速さ（高さは変わらない）")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    pipe = KPipeline(lang_code="j", repo_id="hexgrad/Kokoro-82M")
    # 高さ: 1/p の速さで話させ、p 倍の標本の速さで書く（速さはそのまま、声だけ p 倍高い）
    rate = int(24000 * a.pitch)
    meta = []
    for i, (at, shown, spoken) in enumerate(LINES):
        audio = np.concatenate([np.asarray(x) for _, _, x in pipe(spoken, voice=VOICE, speed=a.tempo / a.pitch)])
        p = out / f"line-{i}.wav"
        sf.write(str(p), audio, rate, subtype="PCM_16")
        with wave.open(str(p)) as w:
            dur = w.getnframes() / w.getframerate()
        meta.append({"at": at, "text": shown, "file": p.name, "seconds": round(dur, 2)})
        print(f"{at:5.1f} 秒から {dur:4.2f} 秒: {shown}")
    # 次の文と重ならないか、終わりを越えないか
    for m, n in zip(meta, meta[1:] + [{"at": 45.0}]):
        if m["at"] + m["seconds"] > n["at"] - 0.1:
            raise SystemExit(f"声が長すぎる: {m['text']}（{m['seconds']} 秒）")
    (out / "lines.json").write_text(json.dumps({"credit": CREDIT, "lines": meta}, ensure_ascii=False, indent=1),
                                    encoding="utf-8")


if __name__ == "__main__":
    main()
