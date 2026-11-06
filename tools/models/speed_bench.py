"""並べ替えの模型（tiny_gpt）の CPU での速さを測る（学習した重みは要らない。速さは大きさと形だけで決まる）。

  python3 tools/models/speed_bench.py
1 文（韓国語は 16 候補、ベトナム語は 8 候補、中国語は 2 候補）を採点する計算の時間を、スレッド 1・2・4 で測る。
"""
import statistics
import sys
import time
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tiny_gpt import TinyGPT  # noqa: E402

torch.manual_seed(0)
CASES = [("韓国語", 1922, 384, 8, 6, 16, 34), ("ベトナム語", 99, 384, 8, 6, 8, 47), ("中国語", 6000, 512, 8, 8, 2, 42),
         # 小さくした形（d 256・4 層、d 192・4 層、d 128・3 層）と、候補を減らした形
         ("韓国語 d256・4層", 1922, 256, 4, 4, 16, 34), ("韓国語 d192・4層", 1922, 192, 4, 4, 16, 34),
         ("韓国語 d128・3層", 1922, 128, 3, 4, 16, 34), ("韓国語 d256・4層・4候補", 1922, 256, 4, 4, 4, 34),
         ("韓国語 d192・4層・4候補", 1922, 192, 4, 4, 4, 34), ("中国語 d256・4層", 6000, 256, 4, 4, 2, 42)]
for threads in (1, 2):
    torch.set_num_threads(threads)
    for name, v, d, layers, heads, batch, length in CASES:
        m = TinyGPT(v, d=d, layers=layers, heads=heads, max_len=256).eval()
        x = torch.randint(4, v, (batch, length))
        with torch.no_grad():
            for _ in range(3):
                m(x)
            ts = []
            for _ in range(30):
                t = time.perf_counter()
                torch.log_softmax(m(x), -1)
                ts.append((time.perf_counter() - t) * 1000)
        ts.sort()
        print(f"スレッド {threads} {name}（{batch} 候補×{length} 字）: 中央 {statistics.median(ts):.1f} ms、遅い方1割 {ts[27]:.1f} ms")
