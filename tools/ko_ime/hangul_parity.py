"""C++ の hangul.cc が tools/ko_ime/hangul.py と同じ結果を出すか確かめる。

  python3 tools/ko_ime/hangul_parity.py <hangul_cli>
すべての音節（11,172 字）のキーへの直しと組み立て直し、でたらめなキーの並び 30,000 個の組み立てを両方で比べる。
"""
import random
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hangul import compose, to_keys  # noqa: E402

sylls = [chr(c) for c in range(0xAC00, 0xD7A4)]
rng = random.Random(20261106)
keys = "rRseEfaqQtTdwWczxvgkoiOjpuPhynbml"
rand = ["".join(rng.choice(keys + " 1") for _ in range(rng.randint(1, 12))) for _ in range(30000)]
qs = [("K", s) for s in sylls] + [("C", to_keys(s)) for s in sylls] + [("C", r) for r in rand]
qs += [("K", "안녕하세요 world 123"), ("C", "dkssudgktpdy"), ("C", ""), ("K", "")]
py = [to_keys(a) if k == "K" else compose(a) for k, a in qs]
p = subprocess.run([sys.argv[1]], input="".join(f"{k}\t{a}\n" for k, a in qs), capture_output=True, text=True,
                   encoding="utf-8", check=True)
cc = p.stdout.split("\n")[: len(qs)]
diff = [(q, a, b) for q, a, b in zip(qs, py, cc) if a != b]
round_trip = sum(compose(to_keys(s)) == s for s in sylls)
print(f"問い {len(qs)}、違い {len(diff)}、音節の組み立て直しが元に戻った {round_trip}/{len(sylls)}")
for d in diff[:20]:
    print("  違い", d)
sys.exit(1 if diff or round_trip != len(sylls) else 0)
