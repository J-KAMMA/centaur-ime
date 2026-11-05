#include "word_tracker.h"

namespace centaur {
namespace {

std::u32string Lower(std::u32string s) {
  for (auto& ch : s) {
    if (ch >= U'A' && ch <= U'Z') ch = ch - U'A' + U'a';
  }
  return s;
}

bool AllUpper(const std::u32string& s) {
  bool any = false;
  for (char32_t ch : s) {
    if (ch >= U'a' && ch <= U'z') return false;
    any = any || (ch >= U'A' && ch <= U'Z');
  }
  return any;
}

}  // namespace

bool WordTracker::IsWordChar(char32_t ch) {
  return (ch >= U'a' && ch <= U'z') || (ch >= U'A' && ch <= U'Z') || ch == U'\'';
}

void WordTracker::OnChar(char32_t ch) {
  if (IsWordChar(ch)) {
    word_ += ch;
    return;
  }
  // 語の区切り。文の終わりなら次は文の頭。
  if (!word_.empty() && tracking_) {
    prev_ = Lower(word_);
  }
  if (ch == U'.' || ch == U'!' || ch == U'?' || ch == U'\n') prev_ = U"<s>";
  word_.clear();
  tracking_ = true;
}

void WordTracker::OnBackspace() {
  if (!word_.empty()) {
    word_.pop_back();
  } else {
    Reset();
  }
}

void WordTracker::Reset() {
  word_.clear();
  prev_ = U"<s>";
  // 語の途中にカーソルが来たかもしれないので、次の区切りまで候補を出さない
  tracking_ = false;
}

std::u32string WordTracker::Completion() const {
  if (!tracking_ || word_.size() < 2 || !model_) return U"";
  const std::u32string lower = Lower(word_);
  std::u32string c = model_->Complete(lower, prev_);
  if (c.size() <= word_.size()) return U"";
  // 打った大文字・小文字に合わせる（全部大文字なら全部大文字、頭が大文字なら頭だけ）
  if (AllUpper(word_)) {
    for (auto& ch : c) {
      if (ch >= U'a' && ch <= U'z') ch = ch - U'a' + U'A';
    }
  } else {
    for (size_t i = 0; i < word_.size() && i < c.size(); ++i) c[i] = word_[i];
  }
  return c;
}

std::u32string WordTracker::TabInsert() const {
  const std::u32string c = Completion();
  return c.empty() ? U"" : c.substr(word_.size());
}

void WordTracker::OnCompletionInserted() {
  const std::u32string c = Completion();
  if (!c.empty()) word_ = c;
}

std::vector<std::u32string> WordTracker::Corrections() const {
  if (!tracking_ || word_.size() < 3 || !model_) return {};
  const std::u32string lower = Lower(word_);
  std::vector<std::u32string> c = model_->Corrections(lower, prev_);
  // 表にある語（一番目が打ったまま）なら直さない
  if (!c.empty() && c[0] == lower) return {};
  return c;
}

}  // namespace centaur
