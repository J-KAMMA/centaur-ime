// 中国語の拼音の中の英単語を残す決まり（tools/zh_ime/mixed.py の Splitter と同じ計算）。
//   打った英字（声調なしの全拼）を、拼音の音節と英単語に分ける一番安い分け方を探す。全部を拼音として読める
//   入力では英語を取らない（ふつうの中国語の入力は必ず拼音として読める）。
#ifndef CENTAUR_CORE_ZH_MIXED_H_
#define CENTAUR_CORE_ZH_MIXED_H_

#include <filesystem>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

namespace centaur {

class ZhMixed {
 public:
  // 表を読む。行は「S<TAB>拼音の音節」と「E<TAB>英語の語（小文字）」（tools/zh_ime/export_mixed.py）。
  bool Load(const std::filesystem::path& path);
  // ブランド名の正式な書き方（Model::LoadCasing と同じ形の表）。英語の部分の表示に使う。
  bool LoadCasing(const std::filesystem::path& path);

  // [(部分, 英語か)]。隣り合う拼音の音節は 1 つにまとめる。
  std::vector<std::pair<std::string, bool>> Split(const std::string& s) const;
  bool IsPinyin(const std::string& s) const;
  // 英語の部分の表示（github → GitHub。表に無ければそのまま）
  std::string Shown(const std::string& english) const;

  size_t syllables() const { return syl_.size(); }
  size_t english_words() const { return eng_.size(); }

 private:
  std::unordered_set<std::string> syl_;
  std::unordered_set<std::string> eng_;
  std::unordered_map<std::string, std::string> casing_;
  size_t max_syl_ = 1;
};

}  // namespace centaur

#endif  // CENTAUR_CORE_ZH_MIXED_H_
