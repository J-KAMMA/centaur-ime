// Telex の組み立てを試す小さな道具（tools/vi_ime/telex_parity.py が使う）。1 行のキーを組み立てて 1 行で返す。
#include <iostream>
#include <string>

#include "core.h"
#include "telex.h"

int main() {
  std::ios::sync_with_stdio(false);
  std::string line;
  while (std::getline(std::cin, line)) {
    std::cout << centaur::ToUtf8(centaur::TelexCompose(centaur::FromUtf8(line))) << '\n';
  }
  return 0;
}
