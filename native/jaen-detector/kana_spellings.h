// Words the user writes in kana although the dictionary has a kanji spelling
// (ぜんぶ for 全部, とき for 時). A word is remembered when the user picks its
// kana spelling over a kanji candidate of the same reading, and forgotten when
// the user picks the kanji again. The words go to the user dictionary
// 「かなで書く語（自動）」, so both Mozc and the AI see them inside longer
// segments too (ぜんぶ食べた), where the segment history cannot match a word
// learned on its own.
//
// Kept in the user profile as "# v1" and then key<TAB>pos id per line.
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

class KanaSpellings {
 public:
  // At most this many words; the oldest added goes first.
  static constexpr size_t kMaxWords = 2000;

  explicit KanaSpellings(std::filesystem::path path) : path_(std::move(path)) { Load(); }

  // Remembers |key| (hiragana, written as is) with the part of speech id of the
  // kanji spelling it replaces. Returns true when the list changed.
  bool Add(std::string_view key, uint16_t pos_id) {
    std::lock_guard<std::mutex> lock(mutex_);
    const auto it = words_.find(std::string(key));
    if (it != words_.end() && it->second.first == pos_id) return false;
    words_[std::string(key)] = {pos_id, ++clock_};
    while (words_.size() > kMaxWords) {
      auto oldest = words_.begin();
      for (auto w = words_.begin(); w != words_.end(); ++w) {
        if (w->second.second < oldest->second.second) oldest = w;
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
    for (const auto& [key, value] : words_) out.emplace_back(key, value.first);
    return out;
  }

 private:
  void Load() {
    std::ifstream in(path_, std::ios::binary);
    std::string line;
    if (!std::getline(in, line) || line != "# v1") return;
    while (std::getline(in, line)) {
      const size_t tab = line.find('\t');
      if (tab == std::string::npos || tab == 0) continue;
      const std::string id = line.substr(tab + 1);
      if (id.empty() || id.size() > 5 || id.find_first_not_of("0123456789") != std::string::npos) continue;
      words_[line.substr(0, tab)] = {static_cast<uint16_t>(std::stoul(id)), ++clock_};
    }
  }

  void Save() const {
    std::ofstream out(path_, std::ios::binary | std::ios::trunc);
    out << "# v1\n";
    for (const auto& [key, value] : words_) out << key << '\t' << value.first << '\n';
  }

  const std::filesystem::path path_;
  mutable std::mutex mutex_;
  // key -> (pos id, order added)
  std::map<std::string, std::pair<uint16_t, uint64_t>> words_;
  uint64_t clock_ = 0;
};

}  // namespace jaen

#endif  // JAEN_KANA_SPELLINGS_H_
