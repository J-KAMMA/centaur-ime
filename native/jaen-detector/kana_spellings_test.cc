// Tests for kana_spellings.h (the words the user writes in kana).
//   g++ -std=c++20 -I native/jaen-detector native/jaen-detector/kana_spellings_test.cc -o kana_spellings_test
#include "kana_spellings.h"

#include <filesystem>
#include <iostream>

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
  std::cout << "SUMMARY\t" << failures << '\n';
  return failures == 0 ? 0 : 1;
}
