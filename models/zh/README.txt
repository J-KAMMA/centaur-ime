Centaur IME Chinese の AI（字の単位の小さな模型、tools/models/tiny_gpt.py の TinyGPT、幅 256・4 層・字 6,556）。

zh-lm.bin       重み（tools/models/export_tiny.py で zh-d256.pt から書き出したもの。native/centaur_core/tiny_lm で読む）
zh-lm-beta.txt  Rime の答えに足す重み（tools/models/rr_zh.py が dev の 2,471 まとまりで選んだ 5）

学習: 2026-11-07、Colab（L4）で 40 分。tools/models/train_task.py --task zh --d 256 --layers 4 --heads 4。
学習に使った文: Tatoeba の中国語の文（CC BY 2.0 FR。表示: Tatoeba の投稿者）、中国語ウィキペディア（CC BY-SA 4.0）、
CC-100（中国語簡体字、Common Crawl から作られた文）。
試験（Tatoeba の確かめの枠、6,142 まとまり）: Rime だけ まとまり 53.3%・字の誤り 12.94% → Rime＋模型 56.6%・10.88%
（Python の rr_zh.py と C++ の Judge で同じ数）。
