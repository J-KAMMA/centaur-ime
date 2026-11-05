// ハングルの行き来を試す小さな道具（tools/ko_ime/hangul_parity.py が使う）。
// 入力の行: 「K<TAB>ハングル」キーの並びに直す、「C<TAB>キーの並び」組み立てる。出力は 1 行ずつ。
#include <iostream>
#include <string>

#include "core.h"
#include "hangul.h"

int main() {
  std::ios::sync_with_stdio(false);
  std::string line;
  while (std::getline(std::cin, line)) {
    const auto arg = centaur::FromUtf8(line.substr(2));
    std::cout << centaur::ToUtf8(line[0] == 'K' ? centaur::ToKeys(arg) : centaur::Compose(arg)) << '\n';
  }
  return 0;
}
