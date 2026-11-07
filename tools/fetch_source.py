"""材料の台帳（tools/data/sources.tsv）の名前を指定して、決まった版を取ってくる。

  python3 tools/fetch_source.py <名前> <置き場> [--lines N]
  python3 tools/fetch_source.py --list

- tatoeba: そのまま落とす。毎日書き出し直されるので、落としたものの SHA-256 を出す。
- hf:      Hugging Face の版を固定した場所から落とす。台帳に SHA-256 があれば確かめる（違えば止める）。
           場所が / で終わるものは、その版のその場所にあるファイルを全部落とす。
- cc100:   大きいので、先頭から --lines 行（既定 200,000 行）だけ流して読み、テキストで置く。読んだ分の SHA-256 を出す。
- tar:     Dakshina。--member で取り出す場所を絞る（例 dakshina_dataset_v1.0/hi/*）。
- apt・pip・git: 取り方を出すだけ（計測の流れの中で入れる）。
材料はこの道具で落とした所（GitHub の計測の機械など）でだけ使い、配布物や配布ページには置かない。
"""
import argparse
import hashlib
import json
import lzma
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

CATALOG = Path(__file__).resolve().parent / "data" / "sources.tsv"


def catalog():
    rows = {}
    for line in CATALOG.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        p = line.split("\t")
        rows[p[0]] = dict(zip(["name", "lang", "kind", "url", "size", "sha256", "license", "use"], p))
    return rows


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def download(url, dest, tries=3):
    dest.parent.mkdir(parents=True, exist_ok=True)
    for k in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=120) as r, open(dest, "wb") as f:
                shutil.copyfileobj(r, f, 1 << 20)
            return
        except Exception as e:  # 一時的な失敗（504 など）はやり直す
            if k + 1 == tries:
                raise
            print(f"やり直し {k + 1}: {e}", file=sys.stderr)


def hf_folder(url):
    """https://huggingface.co/datasets/<repo>/resolve/<rev>/<path>/ のファイルの一覧（版の固定のまま）。"""
    head, rest = url.split("/datasets/", 1)
    repo_part, path = rest.split("/resolve/", 1)
    rev, folder = path.split("/", 1)
    api = f"{head}/api/datasets/{repo_part}/tree/{rev}/{folder.rstrip('/')}"
    items = json.load(urllib.request.urlopen(api, timeout=60))
    return [(f"{head}/datasets/{repo_part}/resolve/{rev}/{x['path']}", x["path"].rsplit("/", 1)[-1],
             x.get("lfs", {}).get("oid", "")) for x in items if x["type"] == "file" and not x["path"].endswith(".gitattributes")]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name", nargs="?")
    ap.add_argument("dest", nargs="?")
    ap.add_argument("--lines", type=int, default=200000)
    ap.add_argument("--member", default="")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    rows = catalog()
    if args.list or not args.name:
        for r in rows.values():
            print(f"{r['name']}\t{r['lang']}\t{r['kind']}\t{r['license']}")
        return
    r = rows[args.name]
    dest = Path(args.dest)
    kind, url = r["kind"], r["url"]
    if kind in ("apt", "pip", "git"):
        print(f"{args.name}: {kind} で入れる: {url}")
        return
    if kind == "tatoeba":
        out = dest / url.rsplit("/", 1)[-1]
        download(url, out)
        print(f"{args.name}\t{out}\t{out.stat().st_size}\t{sha256_of(out)}")
    elif kind == "hf":
        targets = hf_folder(url) if url.endswith("/") else [(url, url.rsplit("/", 1)[-1], r["sha256"])]
        for u, fname, want in targets:
            out = dest / fname
            download(u, out)
            got = sha256_of(out)
            if len(want) == 64 and got != want:
                sys.exit(f"SHA-256 が違う: {fname} {got} != {want}")
            print(f"{args.name}\t{out}\t{out.stat().st_size}\t{got}")
    elif kind == "cc100":
        out = dest / f"{args.name}.{args.lines}.txt"
        dest.mkdir(parents=True, exist_ok=True)
        h = hashlib.sha256()
        n = 0
        with urllib.request.urlopen(url, timeout=120) as resp, lzma.open(resp, "rt", encoding="utf-8") as f, \
                open(out, "w", encoding="utf-8", newline="\n") as w:
            for line in f:
                w.write(line)
                h.update(line.encode("utf-8"))
                n += 1
                if n >= args.lines:
                    break
        print(f"{args.name}\t{out}\t{n} 行\t{h.hexdigest()}")
    elif kind == "tar":
        dest.mkdir(parents=True, exist_ok=True)
        cmd = f"curl -fsSL --retry 3 '{url}' | tar -x -C '{dest}'" + (f" --wildcards '{args.member}'" if args.member else "")
        subprocess.run(["bash", "-o", "pipefail", "-c", cmd], check=True)
        print(f"{args.name}\t{dest}\t{args.member or '全部'}")
    else:
        sys.exit("知らない種類: " + kind)


if __name__ == "__main__":
    main()
