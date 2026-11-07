// 字の模型の C++ の計算が Python（tools/models/export_tiny.py --check）と同じ答えになるかを確かめる道具。
//   tiny_lm_cli zh-lm.bin zh-lm-check.tsv
// 模型の答え（音節ごとに選んだ字）は全く同じ、点数は 32 ビットの小数の計算の違いの分だけずれてよい。
#include <chrono>
#include <cmath>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "tiny_lm.h"

int main(int argc, char** argv) {
  if (argc != 3) {
    std::cerr << "usage: tiny_lm_cli model.bin check.tsv\n";
    return 2;
  }
  centaur::TinyLm lm;
  if (!lm.Load(argv[1])) {
    std::cerr << "模型を読めない\n";
    return 2;
  }
  std::cout << "字 " << lm.vocab() << '\n';
  std::ifstream in(argv[2], std::ios::binary);
  std::string line;
  size_t n = 0, bad = 0;
  double worst = 0, ms = 0;
  while (std::getline(in, line)) {
    std::vector<std::string> col;
    std::stringstream ss(line);
    for (std::string c; std::getline(ss, c, '\t');) col.push_back(c);
    if (col.size() != 5) continue;
    std::vector<std::string> py;
    std::stringstream ps(col[0]);
    for (std::string s; ps >> s;) py.push_back(s);
    const auto t0 = std::chrono::steady_clock::now();
    const std::string mine = lm.Greedy(py);
    const double sr = lm.Score(py, col[1]), sm = lm.Score(py, col[2]);
    ms += std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
    const double want_r = std::stod(col[3]), want_m = std::stod(col[4]);
    const double diff = std::max(std::fabs(sr - want_r), std::fabs(sm - want_m));
    const double tol = 2e-3 + 1e-4 * std::max(std::fabs(want_r), std::fabs(want_m));
    worst = std::max(worst, diff);
    ++n;
    if (mine != col[2] || diff > tol) {
      if (++bad <= 20) std::cout << "違う " << line << " → " << mine << " " << sr << " " << sm << '\n';
    }
  }
  std::cout << n << " 行のうち違った " << bad << "（点数の一番大きいずれ " << worst << "、1 句平均 " << ms / std::max<size_t>(n, 1)
            << " ミリ秒: 答えと 2 つの点数）\n";
  return bad == 0 && n > 0 ? 0 : 1;
}
