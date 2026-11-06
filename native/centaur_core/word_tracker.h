// 打っている語の追跡（OS に関係ない部分）。キーは素通しにしたまま、打った字を見て
// 「いま打っている語」と「前の語」を覚え、候補（補完と直し）を出す。Tab で補完を入れるときに
// 足す文字を返す。窓の表示やキーの横取りは各 OS の側（native/centaur_tip など）がする。
#ifndef CENTAUR_CORE_WORD_TRACKER_H_
#define CENTAUR_CORE_WORD_TRACKER_H_

#include <string>
#include <vector>

#include "core.h"

namespace centaur {

class WordTracker {
 public:
  explicit WordTracker(const Model* model) : model_(model) {}

  // 字を打った（素通しでアプリに渡った後に呼ぶ）。英字と ' は語の続き、それ以外は語の区切り。
  void OnChar(char32_t ch);
  // Backspace。語の中なら 1 字戻す。語の外なら追跡をやめる（どこを消したか分からないため）。
  void OnBackspace();
  // カーソルが動いた・クリックした・窓が替わったなど、前後が分からなくなったとき。
  void Reset();

  // 補完の候補（今の語の続き）。無ければ空。2 字以上打ってから出す。
  std::u32string Completion() const;
  // Tab を押したときに足す文字（補完の残り）。無ければ空で、そのときは Tab を素通しにする。
  std::u32string TabInsert() const;
  // Tab で今の語ごと入れ替える語（大文字・小文字が打った所から変わるとき。gith → GitHub）。無ければ空。
  std::u32string TabReplacement() const;
  // Tab で補完を入れた後に呼ぶ。
  void OnCompletionInserted();
  // 直しの候補（今の語が表に無いときだけ。勝手には直さず、見せるだけ）。
  std::vector<std::u32string> Corrections() const;

  const std::u32string& word() const { return word_; }
  const std::u32string& prev() const { return prev_; }

 private:
  static bool IsWordChar(char32_t ch);

  const Model* model_;
  std::u32string word_;       // 今の語（打ったままの大文字・小文字）
  std::u32string prev_ = U"<s>";  // 前の語（小文字）。文の頭は <s>
  bool tracking_ = true;
};

}  // namespace centaur

#endif  // CENTAUR_CORE_WORD_TRACKER_H_
