#!/bin/bash
# segment_candidates.sh <session_handler_main> <engine dir> <model.gguf> <inputs.tsv> <out.tsv>
# inputs.tsv は「ローマ字<TAB>区切りの数」。空白で変換し、区切りごとに右へ動かして候補の窓を開き、
# 「ローマ字<TAB>区切りの番号<TAB>候補<TAB>候補…」（候補は先頭から最大 30）を書く。
# 漢字の取り違えのうち、正しい字が候補の中にあるか（並べ替えで直せるか）を数えるため。
set -e
EXE=$1; ENGINE=$2; MODEL=$3; IN=$4; OUT=$5
w=$(mktemp -d)
cut -f1 "$IN" > $w/inputs
{ printf 'SEND_KEY\tON\n'
  while IFS=$'\t' read -r r n; do
    printf 'SEND_KEYS\t%s\nSEND_KEY\tSpace\nSHOW_OUTPUT\n' "$r"
    for ((j = 1; j < n; j++)); do printf 'SEND_KEY\tRight\nSHOW_OUTPUT\n'; done
    printf 'SEND_KEY\tEnter\nSHOW_OUTPUT\nCLEAR_ALL\nRESET_CONTEXT\nSEND_KEY\tON\n'
  done < "$IN"; } > $w/cmd.tsv
MYIME_ZENZAI_TIME_LIMIT_MS="${MYIME_ZENZAI_TIME_LIMIT_MS:-0}" MYIME_AI_BUDGET_MS=0 MYIME_HERMETIC_TEST=1 MYIME_AZOOKEY_DLL_DIR="$ENGINE" \
  MYIME_AZOOKEY_ZENZAI_WEIGHT="$MODEL" MYIME_AZOOKEY_ZENZAI_GPU=0 TEST_TMPDIR=$w/prof "$EXE" --input $w/cmd.tsv --profile $w/prof \
  --dictionary oss > $w/out 2> $w/err
# 候補の窓ごとに 1 行。result { … } が来たら次の入力へ。
awk -v inputs=$w/inputs 'BEGIN{while((getline l < inputs)>0) in_[++n]=l; i=1; seg=0}
  /^all_candidate_words \{/{c=1; list=""; k=0}
  c&&/^    value:/{v=$0; sub(/.*value: "/,"",v); sub(/"$/,"",v); if (k<30) {list=list "\t" v; k++}}
  c&&/^\}/{c=0; printf "%s\t%d%s\n", in_[i], seg, list; seg++}
  /^result \{/{i++; seg=0}' $w/out > "$OUT"
python3 "$(cd "$(dirname "$0")" && pwd)/protobuf_text_unescape.py" "$OUT"
head -c 40000 $w/out > "$OUT.raw" 2> /dev/null || true
if grep -l -i "failed to load\|dlopen error\|unavailable" $w/err; then echo "変換エンジンを読めませんでした"; exit 1; fi
wc -l "$OUT"
rm -rf $w
