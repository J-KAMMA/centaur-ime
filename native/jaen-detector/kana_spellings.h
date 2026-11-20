// Words the user writes in kana although the dictionary has a kanji spelling
// (ぜんぶ for 全部, とき for 時). A word is remembered when the user picks its
// kana spelling over a kanji candidate of the same reading, and forgotten when
// the user picks the kanji again. The words go to the user dictionary
// 「かなで書く語（自動）」, and after each conversion ReplaceKanaSpellings puts the
// kana back where the converter wrote the remembered kanji inside a longer
// segment (全部食べた -> ぜんぶ食べた, その時は -> そのときは): the converter does
// not pick the user dictionary word there, and the segment history cannot match
// a word learned on its own.
//
// Kept in the user profile as "# v2" and then key<TAB>pos id<TAB>kanji per line
// ("# v1" files, without the kanji, are still read).
// Header only (used by converter.cc and engine.cc, and kana_spellings_test.cc).
#ifndef JAEN_KANA_SPELLINGS_H_
#define JAEN_KANA_SPELLINGS_H_

#include <cstdint>
#include <filesystem>
#include <fstream>
#include <map>
#include <mutex>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace jaen {

namespace kana_spellings_internal {

// Length in bytes of the UTF-8 character at the start of |s| (1 for a broken byte).
inline size_t CharSize(std::string_view s) {
  if (s.empty()) return 0;
  const unsigned char c = static_cast<unsigned char>(s[0]);
  const size_t n = c < 0x80 ? 1 : c < 0xE0 ? 2 : c < 0xF0 ? 3 : 4;
  return n <= s.size() ? n : 1;
}

// Hiragana ぁ (U+3041) to ゖ (U+3096), and ゝ ゞ.
inline bool IsHiraganaChar(std::string_view c) {
  if (c.size() != 3) return false;
  const unsigned u = (static_cast<unsigned char>(c[0]) & 0x0F) << 12 |
                     (static_cast<unsigned char>(c[1]) & 0x3F) << 6 |
                     (static_cast<unsigned char>(c[2]) & 0x3F);
  return (u >= 0x3041 && u <= 0x3096) || u == 0x309D || u == 0x309E;
}

inline bool AllHiragana(std::string_view s) {
  for (size_t i = 0; i < s.size();) {
    const size_t n = CharSize(s.substr(i));
    if (!IsHiraganaChar(s.substr(i, n))) return false;
    i += n;
  }
  return true;
}

inline bool AnyHiragana(std::string_view s) {
  for (size_t i = 0; i < s.size();) {
    const size_t n = CharSize(s.substr(i));
    if (IsHiraganaChar(s.substr(i, n))) return true;
    i += n;
  }
  return false;
}

// Longest common suffix of |a| and |b| in whole UTF-8 characters.
inline size_t CommonSuffix(std::string_view a, std::string_view b) {
  size_t n = 0;
  while (n < a.size() && n < b.size() && a[a.size() - 1 - n] == b[b.size() - 1 - n]) ++n;
  // Back off to a character boundary of |a| (both strings agree on these bytes).
  while (n > 0 && (static_cast<unsigned char>(a[a.size() - n]) & 0xC0) == 0x80) --n;
  return n;
}

// Is the written |after| (what follows the kanji in the converted text) a fair
// match for the reading |rest| (what follows the kana in the typed reading)?
inline bool RestMatches(std::string_view after, std::string_view rest) {
  if (after.empty()) return rest.empty();
  const std::string_view first = after.substr(0, CharSize(after));
  // 時々, 一ヶ月: the kanji is part of a longer word.
  if (first == "々" || first == "ヶ" || first == "ヵ" || first == "〆") return false;
  // その時は: kana right after the word must be the next kana typed.
  if (IsHiraganaChar(first)) return rest.substr(0, first.size()) == first;
  // 全部食べた: a word written with kanji follows. Its kana ending (べた) must end
  // the reading too, and the part before it must be all kanji with some reading
  // left for it (食 / た). 全部分 (no kana ending) is left alone.
  const size_t common = CommonSuffix(after, rest);
  const std::string_view stem = after.substr(0, after.size() - common);
  const std::string_view stem_reading = rest.substr(0, rest.size() - common);
  return common > 0 && AnyHiragana(after.substr(after.size() - common)) && !stem.empty() &&
         !stem_reading.empty() && !AnyHiragana(stem) && AllHiragana(stem_reading);
}

}  // namespace kana_spellings_internal

// Writes the remembered kana (|words|: kana, kanji) in place of the kanji in
// |value|, the converted text of the reading |key|, where the two line up: the
// text before the kanji is kana that the reading starts with, the reading goes
// on with the remembered kana, and what follows matches (RestMatches).
inline std::string ReplaceKanaSpellings(std::string_view key, std::string value,
                                        const std::vector<std::pair<std::string, std::string>>& words) {
  using namespace kana_spellings_internal;
  for (const auto& [kana, kanji] : words) {
    if (kana.empty() || kanji.empty() || kanji == kana) continue;
    for (size_t p = value.find(kanji); p != std::string::npos; p = value.find(kanji, p + 1)) {
      const std::string_view before(value.data(), p);
      if (!AllHiragana(before) || key.substr(0, before.size()) != before ||
          key.substr(before.size(), kana.size()) != kana) {
        continue;
      }
      const std::string_view after = std::string_view(value).substr(p + kanji.size());
      const std::string_view rest = key.substr(before.size() + kana.size());
      if (!RestMatches(after, rest)) continue;
      value = std::string(before) + kana + std::string(after);
      break;
    }
  }
  return value;
}

class KanaSpellings {
 public:
  // At most this many words; the oldest added goes first.
  static constexpr size_t kMaxWords = 2000;

  explicit KanaSpellings(std::filesystem::path path) : path_(std::move(path)) { Load(); }

  // Remembers |key| (hiragana, written as is) with the part of speech id and the
  // spelling of the kanji candidate it replaces. Returns true when the list changed.
  bool Add(std::string_view key, uint16_t pos_id, std::string_view kanji = {}) {
    std::lock_guard<std::mutex> lock(mutex_);
    const auto it = words_.find(std::string(key));
    if (it != words_.end() && it->second.pos == pos_id && it->second.kanji == kanji) return false;
    words_[std::string(key)] = {pos_id, std::string(kanji), ++clock_};
    while (words_.size() > kMaxWords) {
      auto oldest = words_.begin();
      for (auto w = words_.begin(); w != words_.end(); ++w) {
        if (w->second.order < oldest->second.order) oldest = w;
      }
      words_.erase(oldest);
    }
    Save();
    return true;
  }

  // Forgets |key| (the user picked a kanji spelling again). Returns true when
  // the list changed.
  bool Remove(std::string_view key) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (words_.erase(std::string(key)) == 0) return false;
    Save();
    return true;
  }

  bool Contains(std::string_view key) const {
    std::lock_guard<std::mutex> lock(mutex_);
    return words_.contains(std::string(key));
  }

  void Clear() {
    std::lock_guard<std::mutex> lock(mutex_);
    words_.clear();
    std::error_code error;
    std::filesystem::remove(path_, error);
  }

  // The words in key order, with their part of speech ids.
  std::vector<std::pair<std::string, uint16_t>> Words() const {
    std::lock_guard<std::mutex> lock(mutex_);
    std::vector<std::pair<std::string, uint16_t>> out;
    for (const auto& [key, word] : words_) out.emplace_back(key, word.pos);
    return out;
  }

  // The words with a known kanji spelling, as (kana, kanji), for ReplaceKanaSpellings.
  // A word may keep several kanji spellings separated by '|' (はじめて: 初めて|始めて),
  // one pair each.
  std::vector<std::pair<std::string, std::string>> Spellings() const {
    std::lock_guard<std::mutex> lock(mutex_);
    std::vector<std::pair<std::string, std::string>> out;
    for (const auto& [key, word] : words_) {
      for (size_t b = 0; b < word.kanji.size();) {
        size_t e = word.kanji.find('|', b);
        if (e == std::string::npos) e = word.kanji.size();
        if (e > b) out.emplace_back(key, word.kanji.substr(b, e - b));
        b = e + 1;
      }
    }
    return out;
  }

 private:
  struct Word {
    uint16_t pos = 0;
    std::string kanji;
    uint64_t order = 0;
  };

  void Load() {
    std::ifstream in(path_, std::ios::binary);
    std::string line;
    if (!std::getline(in, line) || (line != "# v1" && line != "# v2")) return;
    while (std::getline(in, line)) {
      const size_t tab = line.find('\t');
      if (tab == std::string::npos || tab == 0) continue;
      const size_t tab2 = line.find('\t', tab + 1);
      const std::string id = line.substr(tab + 1, tab2 == std::string::npos ? std::string::npos : tab2 - tab - 1);
      if (id.empty() || id.size() > 5 || id.find_first_not_of("0123456789") != std::string::npos) continue;
      const std::string kanji = tab2 == std::string::npos ? std::string() : line.substr(tab2 + 1);
      words_[line.substr(0, tab)] = {static_cast<uint16_t>(std::stoul(id)), kanji, ++clock_};
    }
  }

  void Save() const {
    std::ofstream out(path_, std::ios::binary | std::ios::trunc);
    out << "# v2\n";
    for (const auto& [key, word] : words_) out << key << '\t' << word.pos << '\t' << word.kanji << '\n';
  }

  const std::filesystem::path path_;
  mutable std::mutex mutex_;
  std::map<std::string, Word> words_;
  uint64_t clock_ = 0;
};

}  // namespace jaen

#endif  // JAEN_KANA_SPELLINGS_H_
