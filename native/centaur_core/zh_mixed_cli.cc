// 中国語の英単語まじりの分け方が tools/zh_ime/export_mixed.py（mixed.py）と同じ答えになるかを確かめる道具。
//   zh_mixed_cli zh-mixed.tsv zh-mixed-check.tsv
#include <fstream>
#include <iostream>
#include <string>

#include "zh_mixed.h"

int main(int argc, char** argv) {
  if (argc != 3) {
    std::cerr << "usage: zh_mixed_cli zh-mixed.tsv zh-mixed-check.tsv\n";
    return 2;
  }
  centaur::ZhMixed m;
  if (!m.Load(argv[1])) {
    std::cerr << "表を読めない\n";
    return 2;
  }
  std::cout << "拼音の音節 " << m.syllables() << "、英語の語 " << m.english_words() << '\n';
  std::ifstream in(argv[2], std::ios::binary);
  std::string line;
  size_t n = 0, bad = 0, english = 0;
  while (std::getline(in, line)) {
    const size_t tab = line.find('\t');
    if (tab == std::string::npos) continue;
    std::string got;
    bool has_english = false;
    for (const auto& [w, e] : m.Split(line.substr(0, tab))) {
      got += (got.empty() ? "" : "|") + std::string(e ? "E:" : "P:") + w;
      has_english = has_english || e;
    }
    ++n;
    english += has_english;
    if (got != line.substr(tab + 1) && ++bad <= 20) std::cout << "違う " << line << " → " << got << '\n';
  }
  std::cout << n << " 行のうち違った " << bad << "（英語を取った " << english << "）\n";
  return bad == 0 && n > 0 ? 0 : 1;
}
