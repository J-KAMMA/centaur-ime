// Tests for kana_spellings.h (the words the user writes in kana).
//   g++ -std=c++20 -I native/jaen-detector native/jaen-detector/kana_spellings_test.cc -o kana_spellings_test
#include "kana_spellings.h"

#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <utility>
#include <vector>

namespace {
int failures = 0;
void Expect(bool ok, const char* name) {
  if (!ok) { ++failures; std::cout << "FAIL\t" << name << '\n'; }
}
}  // namespace

int main() {
  const auto path = std::filesystem::temp_directory_path() / "kana_spellings_test.txt";
  std::filesystem::remove(path);
  {
    jaen::KanaSpellings words(path);
    Expect(words.Words().empty(), "starts empty without a file");
    Expect(words.Add("ぜんぶ", 1851), "adding a word changes the list");
    Expect(!words.Add("ぜんぶ", 1851), "adding the same word again changes nothing");
    Expect(words.Add("とき", 1851), "a second word");
    Expect(words.Contains("ぜんぶ") && words.Contains("とき"), "both words are kept");
  }
  {
    jaen::KanaSpellings words(path);
    const auto list = words.Words();
    Expect(list.size() == 2 && list[0].first == "ぜんぶ" && list[0].second == 1851,
           "the words are read back from the file, in key order");
    Expect(words.Remove("ぜんぶ") && !words.Contains("ぜんぶ"), "picking the kanji again forgets the word");
    Expect(!words.Remove("ぜんぶ"), "forgetting an unknown word changes nothing");
    words.Clear();
    Expect(words.Words().empty() && !std::filesystem::exists(path), "clearing the history removes the file");
  }
  {
    jaen::KanaSpellings words(path);
    for (size_t i = 0; i < jaen::KanaSpellings::kMaxWords + 5; ++i) words.Add("w" + std::to_string(i), 1);
    Expect(words.Words().size() == jaen::KanaSpellings::kMaxWords && !words.Contains("w0") &&
               words.Contains("w2004"),
           "the oldest words go first when the list is full");
    words.Clear();
  }
  {
    jaen::KanaSpellings words(path);
    Expect(words.Add("ぜんぶ", 1851, "全部") && words.Add("とき", 1852, "時"), "words with their kanji");
    jaen::KanaSpellings again(path);
    const auto spellings = again.Spellings();
    Expect(spellings.size() == 2 && spellings[0] == std::make_pair(std::string("ぜんぶ"), std::string("全部")),
           "the kanji spellings are read back (v2)");
    words.Clear();
    Expect(words.Add("はじめて", 1851, "初めて|始めて"), "a word with two kanji spellings");
    const auto two = words.Spellings();
    Expect(two.size() == 2 && two[0].second == "初めて" && two[1].second == "始めて",
           "each kanji spelling is its own pair");
    Expect(jaen::ReplaceKanaSpellings("はじめてみた", "始めてみた", two) == "はじめてみた",
           "the second kanji spelling is put back too");
    words.Clear();
  }
  {
    // A v1 file (no kanji) is still read; such words are not replaced in text.
    { std::ofstream out(path, std::ios::binary); out << "# v1\nぜんぶ\t1851\n"; }
    jaen::KanaSpellings words(path);
    Expect(words.Contains("ぜんぶ") && words.Spellings().empty(), "v1 files are read, without kanji");
    words.Clear();
  }
  // ReplaceKanaSpellings: (reading, converted, expected)
  const std::vector<std::pair<std::string, std::string>> learned = {
      {"ぜんぶ", "全部"}, {"とき", "時"}, {"はじめて", "初めて"}, {"すべて", "全て"}, {"こと", "事"}};
  const struct { const char* key; const char* value; const char* want; } cases[] = {
      // put back
      {"ぜんぶたべた", "全部食べた", "ぜんぶ食べた"},
      {"ぜんぶたべた。", "全部食べた。", "ぜんぶ食べた。"},
      {"そのときは", "その時は", "そのときは"},
      {"そのときに", "その時に", "そのときに"},
      {"はじめてみた", "初めて見た", "はじめて見た"},
      {"すべてわかった", "全てわかった", "すべてわかった"},
      {"ぜんぶわかった", "全部分かった", "ぜんぶ分かった"},
      {"ぜんぶ", "全部", "ぜんぶ"},
      {"ときどき", "時々", "時々"},
      // left alone: the kanji is part of another word or does not line up
      {"とけい", "時計", "時計"},
      {"ときおり", "時折", "時折"},
      {"ぜんぶぶん", "全部分", "全部分"},
      {"ぜんぶひん", "全部品", "全部品"},
      {"じかん", "時間", "時間"},
      {"そのじだいに", "その時代に", "その時代に"},
      {"きょうぜんぶたべた", "今日全部食べた", "今日全部食べた"},
      {"ことしは", "今年は", "今年は"},
      {"ことば", "言葉", "言葉"},
      {"こと", "古都", "古都"},
      {"ぜんぶちょう", "全部長", "全部長"},
      {"いっかげつ", "一ヶ月", "一ヶ月"},
      {"とき", "時", "とき"},
      {"ときの", "時の", "ときの"},
      {"とくに", "特に", "特に"},
  };
  for (const auto& c : cases) {
    const std::string got = jaen::ReplaceKanaSpellings(c.key, c.value, learned);
    if (got != c.want) std::cout << "  " << c.key << " " << c.value << " -> " << got << " (want " << c.want << ")\n";
    Expect(got == c.want, c.value);
  }
  std::cout << "SUMMARY\t" << failures << '\n';
  return failures == 0 ? 0 : 1;
}
