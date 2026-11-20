#include "zh_mixed.h"

#include <algorithm>
#include <fstream>
#include <optional>

namespace centaur {

bool ZhMixed::Load(const std::filesystem::path& path) {
  std::ifstream in(path, std::ios::binary);
  if (!in) return false;
  std::string line;
  while (std::getline(in, line)) {
    if (!line.empty() && line.back() == '\r') line.pop_back();
    if (line.size() < 3 || line[1] != '\t') continue;
    const std::string w = line.substr(2);
    if (line[0] == 'S') {
      syl_.insert(w);
      max_syl_ = std::max(max_syl_, w.size());
    } else if (line[0] == 'E') {
      eng_.insert(w);
    }
  }
  return !syl_.empty();
}

bool ZhMixed::LoadCasing(const std::filesystem::path& path) {
  std::ifstream in(path, std::ios::binary);
  if (!in) return false;
  std::string line;
  while (std::getline(in, line)) {
    if (!line.empty() && line.back() == '\r') line.pop_back();
    if (line.size() >= 3 && static_cast<unsigned char>(line[0]) == 0xEF) line.erase(0, 3);  // BOM
    if (line.empty() || line[0] == '#') continue;
    const size_t tab = line.find('\t');
    if (tab == std::string::npos || tab == 0) continue;
    const size_t end = line.find('\t', tab + 1);
    const std::string official = line.substr(tab + 1, end == std::string::npos ? std::string::npos : end - tab - 1);
    if (official.empty() || official == "-") continue;
    casing_[line.substr(0, tab)] = official;  // 後の行が勝つ（手で作った表を後に置く）
  }
  return !casing_.empty();
}

bool ZhMixed::IsPinyin(const std::string& s) const {
  std::vector<bool> ok(s.size() + 1, false);
  ok[0] = true;
  for (size_t i = 0; i < s.size(); ++i) {
    if (!ok[i]) continue;
    for (size_t j = i + 1; j <= std::min(s.size(), i + max_syl_); ++j) {
      if (syl_.count(s.substr(i, j - i))) ok[j] = true;
    }
  }
  return ok[s.size()];
}

std::vector<std::pair<std::string, bool>> ZhMixed::Split(const std::string& s) const {
  if (IsPinyin(s)) return {{s, false}};
  const size_t n = s.size();
  struct Best {
    double cost;
    size_t from;
    bool english;
  };
  std::vector<std::optional<Best>> best(n + 1);
  best[0] = Best{0.0, 0, false};
  for (size_t i = 0; i < n; ++i) {
    if (!best[i]) continue;
    const double c0 = best[i]->cost;
    for (size_t j = i + 1; j <= std::min(n, i + 30); ++j) {
      const std::string w = s.substr(i, j - i);
      const size_t len = j - i;
      std::vector<std::pair<double, bool>> opts;
      if (len <= max_syl_ && syl_.count(w)) {
        // 1 字だけで読める拼音（n、m、a、e、o）と ng、hm は重くする（英語がその間に入り込まないように）
        opts.emplace_back(len == 1 || w == "ng" || w == "hm" ? 2.5 : 1.0, false);
      }
      if (len >= 3 && eng_.count(w)) {
        opts.emplace_back(1.5 + (IsPinyin(w) ? 3.0 : 0.0), true);
      } else if (len >= 3 && !IsPinyin(w)) {
        opts.emplace_back(2.0 + 0.7 * static_cast<double>(len), true);  // 表に無い名前
      }
      for (const auto& [cost, eng] : opts) {
        if (!best[j] || c0 + cost < best[j]->cost) best[j] = Best{c0 + cost, i, eng};
      }
    }
  }
  if (!best[n]) return {{s, true}};
  std::vector<std::pair<std::string, bool>> out;
  for (size_t j = n; j > 0;) {
    const Best& b = *best[j];
    out.emplace_back(s.substr(b.from, j - b.from), b.english);
    j = b.from;
  }
  std::reverse(out.begin(), out.end());
  std::vector<std::pair<std::string, bool>> merged;  // となりあう拼音の音節はまとめる
  for (auto& [w, eng] : out) {
    if (!merged.empty() && !eng && !merged.back().second) {
      merged.back().first += w;
    } else {
      merged.emplace_back(std::move(w), eng);
    }
  }
  return merged;
}

std::string ZhMixed::Shown(const std::string& english) const {
  const auto it = casing_.find(english);
  return it == casing_.end() ? english : it->second;
}

}  // namespace centaur
