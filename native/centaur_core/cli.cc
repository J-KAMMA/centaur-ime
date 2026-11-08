// 芯を試す小さな道具（tools/en_ime/parity.py が使う）。
//
//   centaur_core_cli <表> <1 語の重み> <表に無い字の重み> <直しの重み>  < 入力 > 出力
// 入力の行: 「S<TAB>文字の並び」区切り、「C<TAB>前の語<TAB>語」直し、「P<TAB>前の語<TAB>打ちかけ」補完。
// 出力は 1 行ずつ（区切りは空白で、直しはタブで並べる）。最後に種類ごとの時間を標準エラーに出す。
#include <chrono>
#include <iostream>
#include <string>

#include "core.h"

int main(int argc, char* argv[]) {
  if (argc == 4 && std::string(argv[1]) == "--save") {
    // 組み立て済みの表を書く: centaur_core_cli --save <文字の表> <書き出す先>
    centaur::Model m;
    return m.Load(argv[2]) && m.SaveBinary(argv[3]) ? 0 : 1;
  }
  if (argc != 5) {
    std::cerr << "usage: centaur_core_cli table word_penalty oov_char typo_weight\n"
                 "       centaur_core_cli --save table.tsv table.bin\n";
    return 2;
  }
  centaur::Model m;
  const auto t0 = std::chrono::steady_clock::now();
  if (!m.Load(argv[1])) {
    std::cerr << "cannot read " << argv[1] << "\n";
    return 1;
  }
  const auto t1 = std::chrono::steady_clock::now();
  std::cerr << "load_ms " << std::chrono::duration<double, std::milli>(t1 - t0).count() << " vocab " << m.vocab()
            << " (read " << m.load_ms[0] << " deletes " << m.load_ms[1] << " prefix " << m.load_ms[2] << ")\n";
  m.word_penalty = std::stod(argv[2]);
  m.oov_char = std::stod(argv[3]);
  m.typo_weight = std::stod(argv[4]);
  double us[3] = {0, 0, 0};
  long n[3] = {0, 0, 0};
  std::ios::sync_with_stdio(false);
  std::string line;
  while (std::getline(std::cin, line)) {
    const size_t a = line.find('\t');
    const char kind = line[0];
    const auto s0 = std::chrono::steady_clock::now();
    std::string out;
    if (kind == 'S') {
      for (const auto& w : m.Segment(centaur::FromUtf8(line.substr(a + 1)))) {
        if (!out.empty()) out += ' ';
        out += centaur::ToUtf8(w);
      }
    } else {
      const size_t b = line.find('\t', a + 1);
      const auto prev = centaur::FromUtf8(line.substr(a + 1, b - a - 1));
      const auto arg = centaur::FromUtf8(line.substr(b + 1));
      if (kind == 'C') {
        for (const auto& w : m.Corrections(arg, prev)) {
          if (!out.empty()) out += '\t';
          out += centaur::ToUtf8(w);
        }
      } else {
        out = centaur::ToUtf8(m.Complete(arg, prev));
      }
    }
    const int k = kind == 'S' ? 0 : kind == 'C' ? 1 : 2;
    us[k] += std::chrono::duration<double, std::micro>(std::chrono::steady_clock::now() - s0).count();
    ++n[k];
    std::cout << out << '\n';
  }
  std::cerr << "segment_us " << (n[0] ? us[0] / n[0] : 0) << " correct_us " << (n[1] ? us[1] / n[1] : 0)
            << " complete_us " << (n[2] ? us[2] / n[2] : 0) << "\n";
  return 0;
}
