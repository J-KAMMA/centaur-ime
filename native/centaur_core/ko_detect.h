// 韓国語の打ち方の見分け（tools/ko_ime/measure.py の looks_korean と brand_of と同じ決まり）。
//   英語モードのまま打った語（dkssud）: 英語の表に無く、組み立てると字母が残らず、韓国語の表にある語なら 안녕 を出す。
//   韓国語モードのまま打ったブランド名（iphone → ㅑㅔㅗㅐㅜㄷ）: 打ったキーがブランドの表にあり、組み立てた形が
//   韓国語の表に無いなら iPhone を出す。
#ifndef CENTAUR_CORE_KO_DETECT_H_
#define CENTAUR_CORE_KO_DETECT_H_

#include <filesystem>
#include <string>
#include <unordered_map>
#include <unordered_set>

namespace centaur {

class KoDetector {
 public:
  // 語の表を読む。行は「K<TAB>韓国語の語」と「E<TAB>英語の語（小文字）」（tools/ko_ime/export_detect.py）。
  bool Load(const std::filesystem::path& path);
  // ブランド名の正式な書き方（Model::LoadCasing と同じ形の表。打つ形が 3 字以上の英小文字の行だけ使う）。
  bool LoadCasing(const std::filesystem::path& path);

  // 英語モードのまま打ったキーが韓国語の語なら、その語。違えば空。
  std::u32string Korean(const std::u32string& keys) const;
  // 韓国語モードのまま打ったキーがブランド名なら、正式な書き方。違えば空。
  std::u32string Brand(const std::u32string& keys) const;

  size_t korean_words() const { return korean_.size(); }
  size_t english_words() const { return english_.size(); }
  size_t brands() const { return brands_.size(); }

 private:
  // 組み立てると字母が残らず、韓国語の表にある語か
  bool IsKoreanWord(const std::u32string& keys) const;

  std::unordered_set<std::u32string> korean_;
  std::unordered_set<std::u32string> english_;
  std::unordered_map<std::u32string, std::u32string> brands_;
};

}  // namespace centaur

#endif  // CENTAUR_CORE_KO_DETECT_H_
