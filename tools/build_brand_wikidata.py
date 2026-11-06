"""ブランド・会社・ソフト・サービスの名前と正式な書き方を Wikidata（CC0）から集める。

  python3 tools/build_brand_wikidata.py --eng eng_sentences.tsv.bz2 --out tools/data/brand-casing-wikidata.tsv

Wikidata の問い合わせ（query.wikidata.org）で、下の種類の項目のうち、英語の名前が 1 語（英字・数字・+ . & ' -）で、
記事のある言語の数（sitelinks）が --min-links 以上のものを取る。打つ形は名前の英字と数字を小文字にしたもの。
ふつうの英単語と同じ名前（apple、amazon、shell）は、Tatoeba の英語の文に小文字で --common 回以上出るなら外す
（英語版で apple を勝手に Apple にしないため）。行は「打つ形<TAB>正式な書き方<TAB>sitelinks<TAB>種類」。
同じ打つ形が重なったら sitelinks の多い方。手で直すときは tools/data/brand-casing-fixes.tsv（今までどおり）。
"""
import argparse
import bz2
import collections
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

KINDS = {
    "Q431289": "ブランド", "Q4830453": "会社", "Q783794": "会社", "Q891723": "上場会社", "Q6881511": "会社",
    "Q7397": "ソフト", "Q166142": "アプリ", "Q35127": "ウェブサイト", "Q9143": "プログラミング言語",
    "Q7889": "ゲーム", "Q1137109": "家庭用ゲーム機", "Q22645": "ゲーム機", "Q19967801": "オンラインサービス",
    "Q1668024": "サービス", "Q3220391": "OS", "Q9135": "OS", "Q620615": "スマホのアプリ", "Q2424752": "製品",
    # コンピュータ用語（ライブラリ、フレームワーク、ファイル形式、プロトコル、データベース、ブラウザ、フリーソフト）
    "Q188860": "ライブラリ", "Q271680": "フレームワーク", "Q1330336": "フレームワーク", "Q235557": "ファイル形式",
    "Q15836568": "プロトコル", "Q2310307": "プロトコル", "Q3913213": "データベース", "Q176165": "データベース",
    "Q341": "フリーソフト", "Q506883": "フリーソフト", "Q19541": "ブラウザ",
}
# 日本語版のコンピュータ用語の表（打つ形<TAB>表示する形）も、同じ決まり（ふつうの英単語は外す）で足す
EXTRA = ["jaen-modern-words.tsv", "domain-casing.tsv", "acronyms.tsv"]
NAME = re.compile(r"^[A-Za-z][A-Za-z0-9+.&'\-]{1,30}$")
UA = "CentaurIME-brand-data/1 (https://github.com/J-KAMMA/centaur-ime)"


def query(cls, min_links):
    q = f"""SELECT ?item ?label ?links WHERE {{
  ?item wdt:P31 wd:{cls}; wikibase:sitelinks ?links; rdfs:label ?label.
  FILTER(LANG(?label) = "en") FILTER(?links >= {min_links})
}}"""
    url = "https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"query": q, "format": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/sparql-results+json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.load(r)
            return [(b["item"]["value"].rsplit("/", 1)[1], b["label"]["value"], int(b["links"]["value"]))
                    for b in data["results"]["bindings"]]
        except Exception as e:  # 混んでいるときは待ってやり直す
            print("  やり直し", cls, e)
            time.sleep(20 * (attempt + 1))
    return []


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--eng", required=True, help="Tatoeba の英語の文（ふつうの英単語を外すため）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-links", type=int, default=8)
    ap.add_argument("--common", type=int, default=5)
    ap.add_argument("--data", default="tools/data", help="日本語版の表の置き場")
    ap.add_argument("--ambiguous", help="ふつうの英単語と同じなので外した名前を書く（文脈で選ぶ一覧）")
    a = ap.parse_args()

    lower_count = collections.Counter()
    with bz2.open(a.eng, "rt", encoding="utf-8") as f:
        for line in f:
            c = line.rstrip("\n").split("\t")
            if len(c) >= 3 and c[1] == "eng":
                lower_count.update(w for w in re.findall(r"[A-Za-z][A-Za-z']*", c[2]) if w.islower())

    best = {}
    ambiguous = {}
    stats = collections.Counter()
    for cls, kind in KINDS.items():
        rows = query(cls, a.min_links)
        print(f"{kind}（{cls}）: {len(rows)}")
        time.sleep(2)
        for qid, label, links in rows:
            if not NAME.match(label):
                stats["1 語でない・字の形が合わない"] += 1
                continue
            typed = re.sub(r"[^a-z0-9]", "", label.lower())
            if len(typed) < 3 or not re.search(r"[a-z]", typed):
                stats["短い"] += 1
                continue
            if lower_count[label.lower()] >= a.common:
                stats["ふつうの英単語"] += 1
                ambiguous.setdefault(typed, (label, links, kind))
                continue
            if typed not in best or links > best[typed][1]:
                best[typed] = (label, links, kind)
    for name in EXTRA:
        path = Path(a.data) / name
        for line in path.read_text(encoding="utf-8").splitlines():
            c = line.split("\t")
            if line.startswith("#") or len(c) < 2 or not re.fullmatch(r"[a-z0-9]{2,}", c[0]) or c[1] == "-":
                continue
            typed, label = c[0], c[1]
            if typed == label:
                continue  # 書き方が変わらない（小文字のまま）
            if lower_count[typed] >= a.common:
                ambiguous.setdefault(typed, (label, 0, "日本語版の表"))
                stats["ふつうの英単語（日本語版の表）"] += 1
                continue
            if typed not in best:
                best[typed] = (label, 0, "コンピュータ用語")
    if a.ambiguous:
        with open(a.ambiguous, "w", encoding="utf-8", newline="\n") as f:
            f.write("# typed<TAB>official<TAB>sitelinks<TAB>kind: ふつうの英単語と同じ名前（apple / Apple）。文脈で選ぶ\n")
            for typed, (label, links, kind) in sorted(ambiguous.items()):
                f.write(f"{typed}\t{label}\t{links}\t{kind}\n")
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        f.write("# typed<TAB>official<TAB>sitelinks<TAB>kind (Wikidata, CC0; tools/build_brand_wikidata.py)\n")
        for typed, (label, links, kind) in sorted(best.items(), key=lambda kv: (-kv[1][1], kv[0])):
            f.write(f"{typed}\t{label}\t{links}\t{kind}\n")
    print("書いた", len(best), "語。外した:", dict(stats))


if __name__ == "__main__":
    main()
