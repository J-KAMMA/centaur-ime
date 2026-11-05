// Centaur IME の言語に共通の芯（AI なし）: 語の出やすさと 2 語の並びの表で、
// スペースなしの区切り、キーの位置を見た打ち間違いの直し、語の補完をする。
// 英語・中国語・韓国語で同じ計算を使い、言語ごとに違うのは表（と字の単位）だけ。
// 中身は tools/en_ime/en_model.py の試作と同じ計算（同点は語の順）。tools/en_ime/parity.py で一致を確かめる。
#ifndef CENTAUR_CORE_CORE_H_
#define CENTAUR_CORE_CORE_H_

#include <cstdint>
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

  // 表を読む。行は「U<TAB>語<TAB>数」と「B<TAB>前の語<TAB>語<TAB>数」（前の語 <s> は文の頭）。
  bool Load(const std::string& path, int max_edit = 2, size_t prefix_keep = 8);

  double LogpUni(const std::u32string& w) const;
  double Logp(const std::u32string& prev, const std::u32string& w) const;

  std::vector<std::u32string> Segment(const std::u32string& text) const;
  std::vector<std::u32string> Corrections(const std::u32string& w, const std::u32string& prev,
                                          size_t limit = 3) const;
  // 一番の補完の候補。無ければ空。
  std::u32string Complete(const std::u32string& prefix, const std::u32string& prev) const;

  size_t vocab() const { return words_.size(); }

 private:
  void AddDeletes(const std::u32string& w, uint32_t id);
  static std::vector<std::u32string> Deletes(const std::u32string& w, int n);

  std::unordered_map<std::u32string, int64_t> uni_;
  std::unordered_map<std::u32string, std::unordered_map<std::u32string, int64_t>> bi_;
  std::unordered_map<std::u32string, int64_t> left_;
  int64_t total_ = 0;
  size_t max_len_ = 1;
  int max_edit_ = 2;
  std::vector<std::u32string> words_;
  std::unordered_map<std::u32string, std::vector<uint32_t>> deletes_;
  std::unordered_map<std::u32string, std::vector<uint32_t>> prefix_;
};

}  // namespace centaur

#endif  // CENTAUR_CORE_CORE_H_
