// 韓国語の見分けが tools/ko_ime/export_detect.py と同じ答えになるかを確かめる道具。
//   ko_detect_cli ko-detect.tsv casing.tsv check.tsv
// check.tsv の行は「キー<TAB>韓国語の語の答え<TAB>ブランド名の答え」。違った行を出し、違いが無ければ 0 を返す。
#include <fstream>
#include <iostream>
#include <string>

#include "core.h"
#include "ko_detect.h"

int main(int argc, char** argv) {
  if (argc != 4) {
    std::cerr << "usage: ko_detect_cli ko-detect.tsv casing.tsv check.tsv\n";
    return 2;
  }
  centaur::KoDetector d;
  if (!d.Load(argv[1]) || !d.LoadCasing(argv[2])) {
    std::cerr << "表を読めない\n";
    return 2;
  }
  std::cout << "韓国語の語 " << d.korean_words() << "、英語の語 " << d.english_words() << "、ブランド名 " << d.brands()
            << '\n';
  std::ifstream in(argv[3], std::ios::binary);
  std::string line;
  size_t n = 0, bad = 0, ko = 0, brand = 0;
  while (std::getline(in, line)) {
    const size_t a = line.find('\t'), b = line.find('\t', a + 1);
    if (a == std::string::npos || b == std::string::npos) continue;
    const auto keys = centaur::FromUtf8(line.substr(0, a));
    const std::string want_ko = line.substr(a + 1, b - a - 1), want_brand = line.substr(b + 1);
    const std::string got_ko = centaur::ToUtf8(d.Korean(keys)), got_brand = centaur::ToUtf8(d.Brand(keys));
    ++n;
    ko += !got_ko.empty();
    brand += !got_brand.empty();
    if (got_ko != want_ko || got_brand != want_brand) {
      if (++bad <= 20) std::cout << "違う " << line << " → " << got_ko << " / " << got_brand << '\n';
    }
  }
  std::cout << n << " 行のうち違った " << bad << "（韓国語の語を出した " << ko << "、ブランド名を出した " << brand << "）\n";
  return bad == 0 && n > 0 ? 0 : 1;
}
