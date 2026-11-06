"""紹介動画の声を VOICEVOX（四国めたん、ノーマル）で作る。

使う条件: VOICEVOX と四国めたんの規約により、動画の中と配布ページに「VOICEVOX:四国めたん」と書く。
エンジンは GitHub の流れの中で docker で動かす（http://127.0.0.1:50021）。

  python narrate.py --out voice/      voice/line-<番号>.wav と voice/lines.json を書く
"""
import argparse
import json
import urllib.parse
import urllib.request
import wave
from pathlib import Path

SPEAKER = 2  # 四国めたん ノーマル
CREDIT = "VOICEVOX:四国めたん"

# (始まり秒, 読む文, 読ませる文)。読ませる文は読み違いを避けるためのかな書き
LINES = [
    (0.3, "Centaur IME。文の流れを読んで変換する、日本語入力です。", "ケンタウロス・アイエムイー。文の流れを読んで変換する日本語入力です。"),
    (6.0, "同じ読みでも、前後の言葉から、合う漢字を選びます。", "同じ読みでも、前後の言葉から、合う漢字を選びます。"),
    (11.3, "英単語は、入力を切り替えずに、そのまま打てます。", "英単語は、入力を切り替えずに、そのまま打てます。"),
    (19.3, "打ち間違いも、文の流れから直します。", "打ち間違いも、文の流れから直します。"),
    (25.4, "無料で、変換はすべてパソコンの中で行います。", "無料で、変換はすべてパソコンの中で行います。"),
]


def post(host, path, params, body=None):
    url = f"{host}{path}?{urllib.parse.urlencode(params)}"
    data = json.dumps(body).encode() if body is not None else b""
    req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="http://127.0.0.1:50021")
    ap.add_argument("--out", required=True)
    ap.add_argument("--speed", type=float, default=1.1)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    meta = []
    for i, (at, shown, spoken) in enumerate(LINES):
        q = json.loads(post(a.host, "/audio_query", {"text": spoken, "speaker": SPEAKER}))
        q["speedScale"] = a.speed
        q["prePhonemeLength"] = 0.05
        q["postPhonemeLength"] = 0.1
        wav = post(a.host, "/synthesis", {"speaker": SPEAKER}, q)
        p = out / f"line-{i}.wav"
        p.write_bytes(wav)
        with wave.open(str(p)) as w:
            dur = w.getnframes() / w.getframerate()
        meta.append({"at": at, "text": shown, "file": p.name, "seconds": round(dur, 2)})
        print(f"{at:5.1f} 秒から {dur:4.2f} 秒: {shown}")
    # 次の文と重ならないか、終わりを越えないか
    for m, n in zip(meta, meta[1:] + [{"at": 30.0}]):
        if m["at"] + m["seconds"] > n["at"] - 0.1:
            raise SystemExit(f"声が長すぎる: {m['text']}（{m['seconds']} 秒）")
    (out / "lines.json").write_text(json.dumps({"credit": CREDIT, "lines": meta}, ensure_ascii=False, indent=1),
                                    encoding="utf-8")


if __name__ == "__main__":
    main()
