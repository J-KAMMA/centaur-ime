#include "ko_detect.h"

#include <fstream>

#include "core.h"
#include "hangul.h"

namespace centaur {
namespace {

std::u32string Lower(std::u32string s) {
  for (auto& c : s) {
    if (c >= U'A' && c <= U'Z') c = c - U'A' + U'a';
  }
  return s;
}

}  // namespace

bool KoDetector::Load(const std::filesystem::path& path) {
  std::ifstream in(path, std::ios::binary);
  if (!in) return false;
  std::string line;
  while (std::getline(in, line)) {
    if (!line.empty() && line.back() == '\r') line.pop_back();
    if (line.size() < 3 || line[1] != '\t') continue;
    const std::u32string w = FromUtf8(line.substr(2));
    if (line[0] == 'K') korean_.insert(w);
    if (line[0] == 'E') english_.insert(w);
  }
  return !korean_.empty();
}

bool KoDetector::LoadCasing(const std::filesystem::path& path) {
  std::ifstream in(path, std::ios::binary);
  if (!in) return false;
  std::string line;
  while (std::getline(in, line)) {
    if (!line.empty() && line.back() == '\r') line.pop_back();
    if (line.size() >= 3 && static_cast<unsigned char>(line[0]) == 0xEF) line.erase(0, 3);  // BOM
    if (line.empty() || line[0] == '#') continue;
    const size_t tab = line.find('\t');
    if (tab == std::string::npos || tab < 3) continue;
    const size_t end = line.find('\t', tab + 1);
    const std::string typed = line.substr(0, tab);
    const std::string official = line.substr(tab + 1, end == std::string::npos ? std::string::npos : end - tab - 1);
    bool lower = true;
    for (char c : typed) lower = lower && c >= 'a' && c <= 'z';
    if (!lower || official.empty() || official == "-") continue;
    brands_[FromUtf8(typed)] = FromUtf8(official);  // 後の行が勝つ（手で作った表を後に置く）
  }
  return !brands_.empty();
}

bool KoDetector::IsKoreanWord(const std::u32string& keys) const {
  const std::u32string ko = Compose(keys);
  if (ko.empty()) return false;
  for (char32_t c : ko) {
    if (!IsHangulSyllable(c)) return false;
  }
  return korean_.count(ko) > 0;
}

std::u32string KoDetector::Korean(const std::u32string& keys) const {
  if (keys.empty() || english_.count(Lower(keys))) return {};
  return IsKoreanWord(keys) ? Compose(keys) : std::u32string();
}

std::u32string KoDetector::Brand(const std::u32string& keys) const {
  const auto it = brands_.find(Lower(keys));
  if (it == brands_.end() || IsKoreanWord(keys)) return {};
  return it->second;
}

}  // namespace centaur
