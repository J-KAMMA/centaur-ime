#!/bin/bash
# Colab のノート（notebooks/train_all.ipynb）の材料のセルと同じことをする（ノートを開き直さずに使えるように）。
#   bash repo/tools/models/colab_prepare.sh   （repo/ の上で）
set -eo pipefail
F=repo/tools/fetch_source.py
python $F tatoeba-cmn data/zh
python $F wiki-zh data/zh
python $F cc100-zh-Hans data/zh --lines 400000
python $F tatoeba-vie data/vi
python $F cc100-vi data/vi --lines 400000
python $F dakshina data/hi --member 'dakshina_dataset_v1.0/hi/*'
python $F tatoeba-kor data/ko
python $F wiki-ko data/ko
python $F cc100-ko data/ko --lines 300000
python $F arabizi-darija data/darija
python repo/tools/models/zh_wiki_lines.py data/zh data/zh/wiki.txt 400000
