"""中国語のウィキ（parquet）を 1 行 1 文にする（模型の学習の足しの材料）。

  python3 tools/models/zh_wiki_lines.py <parquet のある場所> <書き出す先> <文の数>
"""
import glob
import re
import sys

import pyarrow.parquet as pq

src, dst, limit = sys.argv[1], sys.argv[2], int(sys.argv[3])
t = pq.read_table(glob.glob(src + "/*.parquet")[0], columns=["text"])
n = 0
with open(dst, "w", encoding="utf-8") as f:
    for text in t.column("text").to_pylist():
        for s in re.split(r"[。！？\n]", text):
            if 4 <= len(s) <= 60:
                f.write(s + "\n")
                n += 1
        if n >= limit:
            break
print("ウィキの文", n)
