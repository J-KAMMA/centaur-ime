// Centaur IME の言語に共通の芯（AI なし）: 語の出やすさと 2 語の並びの表で、
// スペースなしの区切り、キーの位置を見た打ち間違いの直し、語の補完をする。
// 英語・中国語・韓国語で同じ計算を使い、言語ごとに違うのは表（と字の単位）だけ。
// 中身は tools/en_ime/en_model.py の試作と同じ計算（同点は語の順）。tools/en_ime/parity.py で一致を確かめる。
#ifndef CENTAUR_CORE_CORE_H_
#define CENTAUR_CORE_CORE_H_

#include <cstdint>
#include <filesystem>
#include <string>
#include <unordered_map>
#include <vector>

namespace centaur {

std::u32string FromUtf8(const std::string& s);
std::string ToUtf8(const std::u32string& s);

// 打った typed が word の打ち間違いである重み（キーの位置を見た編集距離）。
double TypoCost(const std::u32string& typed, const std::u32string& word);
// 入れ替え（隣どうし）も 1 と数える編集距離。
int EditDistance(const std::u32string& a, const std::u32string& b);

class Model {
 public:
  // 区切りで 1 語増えるごとの重み、表に無い語の 1 字あたりの重みと長さの上限、直しの重み
  double word_penalty = 2.0;
  double oov_char = 1.5;
  int oov_max = 20;
  double typo_weight = 6.0;

  // 表を読む。文字の表なら行は「U<TAB>語<TAB>数」と「B<TAB>前の語<TAB>語<TAB>数」（前の語 <s> は文の頭）。
  // SaveBinary で書いた組み立て済みの表なら、索引を作り直さずにそのまま読む。
  bool Load(const std::filesystem::path& path, int max_edit = 2, size_t prefix_keep = 8);
  bool SaveBinary(const std::filesystem::path& path) const;

  double LogpUni(const std::u32string& w) const;
  double Logp(const std::u32string& prev, const std::u32string& w) const;

  std::vector<std::u32string> Segment(const std::u32string& text) const;
  std::vector<std::u32string> Corrections(const std::u32string& w, const std::u32string& prev,
                                          size_t limit = 3) const;
  // 一番の補完の候補。無ければ空。
  std::u32string Complete(const std::u32string& prefix, const std::u32string& prev) const;

  // ブランド・サービス名の正式な書き方（github → GitHub）を読む。行は「打った形<TAB>正式な形」
  // （tools/data/brand-casing.tsv と同じ形。# の行と、正式な形が「-」の行は使わない。3 列目から先は読み飛ばす。
  // 同じ打つ形が何度も出たら後の行が勝つ）。
  bool LoadCasing(const std::filesystem::path& path);
  // 小文字の語 w の正式な書き方。無ければ空。
  std::u32string Cased(const std::u32string& w) const;

  size_t vocab() const { return words_.size(); }
  // 読み込みの内訳（ミリ秒）: 表を読む、消し字の索引、補完の一覧
  double load_ms[3] = {0, 0, 0};

 private:
  bool LoadText(const std::filesystem::path& path, int max_edit, size_t prefix_keep);
  bool LoadBinary(const std::filesystem::path& path);
  void Finish();  // 合計と一番長い語の長さ
  static std::vector<std::u32string> Deletes(const std::u32string& w, int n);

  std::unordered_map<std::u32string, int64_t> uni_;
  std::unordered_map<std::u32string, std::unordered_map<std::u32string, int64_t>> bi_;
  std::unordered_map<std::u32string, int64_t> left_;
  std::unordered_map<std::u32string, std::u32string> casing_;  // 小文字 → 正式な書き方
  int64_t total_ = 0;
  size_t max_len_ = 1;
  int max_edit_ = 2;
  std::vector<std::u32string> words_;
  // 索引は文字列ではなくハッシュの並んだ配列（読み込みが速い）。ハッシュが偶然重なっても、
  // 直しは編集距離で、補完は頭が合うかで確かめ直すので、答えは変わらない。
  std::vector<std::pair<uint64_t, uint32_t>> deletes_;  // 消し字のハッシュ → 語
  std::vector<uint64_t> prefix_keys_;                    // 頭のハッシュ（並べたもの）
  std::vector<uint32_t> prefix_off_;                     // prefix_keys_[i] の語は prefix_ids_[off[i], off[i+1])
  std::vector<uint32_t> prefix_ids_;
};

}  // namespace centaur

#endif  // CENTAUR_CORE_CORE_H_
