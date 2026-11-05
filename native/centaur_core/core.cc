#include "core.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <fstream>
#include <limits>
#include <map>
#include <set>
#include <sstream>
#include <tuple>
#include <unordered_set>

namespace centaur {
namespace {

const char* const kRows[] = {"qwertyuiop", "asdfghjkl", "zxcvbnm"};

// キーの位置（行、列。下の行ほど半キーずつ右にずれる）
bool KeyPos(char32_t ch, double* r, double* c) {
  for (int row = 0; row < 3; ++row) {
    for (int col = 0; kRows[row][col]; ++col) {
      if (static_cast<char32_t>(kRows[row][col]) == ch) {
        *r = row;
        *c = col + 0.5 * row;
        return true;
      }
    }
  }
  return false;
}

bool Near(char32_t a, char32_t b) {
  double r1, c1, r2, c2;
  if (!KeyPos(a, &r1, &c1) || !KeyPos(b, &r2, &c2)) return false;
  return std::abs(r1 - r2) <= 1 && std::abs(c1 - c2) <= 1.0;
}

const std::u32string kBos = U"<s>";
const char kBinaryMagic[8] = {'C', 'T', 'R', 'B', '1', 0, 0, 0};

uint64_t Hash(const std::u32string& s) {
  uint64_t h = 1469598103934665603ULL;  // FNV-1a
  for (char32_t ch : s) {
    for (int k = 0; k < 4; ++k) {
      h ^= (ch >> (8 * k)) & 0xff;
      h *= 1099511628211ULL;
    }
  }
  return h;
}

template <typename T>
void Put(std::ofstream& f, const T& v) {
  f.write(reinterpret_cast<const char*>(&v), sizeof(v));
}
template <typename T>
bool Get(std::ifstream& f, T* v) {
  return static_cast<bool>(f.read(reinterpret_cast<char*>(v), sizeof(*v)));
}
template <typename T>
void PutVec(std::ofstream& f, const std::vector<T>& v) {
  Put(f, static_cast<uint64_t>(v.size()));
  f.write(reinterpret_cast<const char*>(v.data()), static_cast<std::streamsize>(v.size() * sizeof(T)));
}
template <typename T>
bool GetVec(std::ifstream& f, std::vector<T>* v) {
  uint64_t n;
  if (!Get(f, &n)) return false;
  v->resize(n);
  return static_cast<bool>(
      f.read(reinterpret_cast<char*>(v->data()), static_cast<std::streamsize>(n * sizeof(T))));
}

}  // namespace

std::u32string FromUtf8(const std::string& s) {
  std::u32string out;
  for (size_t i = 0; i < s.size();) {
    const unsigned char c = s[i];
    char32_t cp;
    int n;
    if (c < 0x80) {
      cp = c;
      n = 1;
    } else if ((c >> 5) == 6) {
      cp = c & 0x1f;
      n = 2;
    } else if ((c >> 4) == 14) {
      cp = c & 0x0f;
      n = 3;
    } else {
      cp = c & 0x07;
      n = 4;
    }
    for (int k = 1; k < n && i + k < s.size(); ++k) cp = (cp << 6) | (s[i + k] & 0x3f);
    out.push_back(cp);
    i += n;
  }
  return out;
}

std::string ToUtf8(const std::u32string& s) {
  std::string out;
  for (char32_t cp : s) {
    if (cp < 0x80) {
      out += static_cast<char>(cp);
    } else if (cp < 0x800) {
      out += static_cast<char>(0xc0 | (cp >> 6));
      out += static_cast<char>(0x80 | (cp & 0x3f));
    } else if (cp < 0x10000) {
      out += static_cast<char>(0xe0 | (cp >> 12));
      out += static_cast<char>(0x80 | ((cp >> 6) & 0x3f));
      out += static_cast<char>(0x80 | (cp & 0x3f));
    } else {
      out += static_cast<char>(0xf0 | (cp >> 18));
      out += static_cast<char>(0x80 | ((cp >> 12) & 0x3f));
      out += static_cast<char>(0x80 | ((cp >> 6) & 0x3f));
      out += static_cast<char>(0x80 | (cp & 0x3f));
    }
  }
  return out;
}

double TypoCost(const std::u32string& typed, const std::u32string& word) {
  const size_t la = typed.size(), lb = word.size();
  std::vector<std::vector<double>> d(la + 1, std::vector<double>(lb + 1, 0.0));
  for (size_t i = 0; i <= la; ++i) d[i][0] = static_cast<double>(i);
  for (size_t j = 0; j <= lb; ++j) d[0][j] = static_cast<double>(j);
  for (size_t i = 1; i <= la; ++i) {
    for (size_t j = 1; j <= lb; ++j) {
      const char32_t a = typed[i - 1], b = word[j - 1];
      const double sub = a == b ? 0.0 : (Near(a, b) ? 0.6 : 1.0);
      // typed にだけある字（余分）: 前の字と同じか隣なら軽い
      const double extra = (i > 1 && (typed[i - 2] == a || Near(typed[i - 2], a))) ? 0.6 : 1.0;
      d[i][j] = std::min({d[i - 1][j] + extra, d[i][j - 1] + 1.0, d[i - 1][j - 1] + sub});
      if (i > 1 && j > 1 && a == word[j - 2] && typed[i - 2] == b) {
        d[i][j] = std::min(d[i][j], d[i - 2][j - 2] + 0.6);
      }
    }
  }
  double cost = d[la][lb];
  if (la && lb && typed[0] != word[0]) cost += 0.5;
  return cost;
}

int EditDistance(const std::u32string& a, const std::u32string& b) {
  const size_t la = a.size(), lb = b.size();
  std::vector<std::vector<int>> d(la + 1, std::vector<int>(lb + 1, 0));
  for (size_t i = 0; i <= la; ++i) d[i][0] = static_cast<int>(i);
  for (size_t j = 0; j <= lb; ++j) d[0][j] = static_cast<int>(j);
  for (size_t i = 1; i <= la; ++i) {
    for (size_t j = 1; j <= lb; ++j) {
      const int cost = a[i - 1] == b[j - 1] ? 0 : 1;
      d[i][j] = std::min({d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost});
      if (i > 1 && j > 1 && a[i - 1] == b[j - 2] && a[i - 2] == b[j - 1]) {
        d[i][j] = std::min(d[i][j], d[i - 2][j - 2] + 1);
      }
    }
  }
  return d[la][lb];
}

std::vector<std::u32string> Model::Deletes(const std::u32string& w, int n) {
  std::set<std::u32string> out = {w};
  std::set<std::u32string> frontier = {w};
  for (int k = 0; k < n; ++k) {
    std::set<std::u32string> next;
    for (const auto& x : frontier) {
      for (size_t i = 0; i < x.size(); ++i) next.insert(x.substr(0, i) + x.substr(i + 1));
    }
    out.insert(next.begin(), next.end());
    frontier = std::move(next);
  }
  return {out.begin(), out.end()};
}

bool Model::Load(const std::string& path, int max_edit, size_t prefix_keep) {
  {
    std::ifstream f(path, std::ios::binary);
    char magic[8] = {};
    if (f.read(magic, 8) && std::equal(magic, magic + 8, kBinaryMagic)) return LoadBinary(path);
  }
  return LoadText(path, max_edit, prefix_keep);
}

void Model::Finish() {
  total_ = 0;
  max_len_ = 1;
  for (const auto& w : words_) {
    total_ += uni_[w];
    max_len_ = std::max(max_len_, w.size());
  }
}

bool Model::LoadText(const std::string& path, int max_edit, size_t prefix_keep) {
  using Clock = std::chrono::steady_clock;
  const auto t0 = Clock::now();
  std::ifstream f(path, std::ios::binary);
  if (!f) return false;
  max_edit_ = max_edit;
  std::string line;
  while (std::getline(f, line)) {
    std::vector<std::string> p;
    std::stringstream ss(line);
    for (std::string x; std::getline(ss, x, '\t');) p.push_back(x);
    if (p.size() == 3 && p[0] == "U") {
      const std::u32string w = FromUtf8(p[1]);
      if (!uni_.count(w)) words_.push_back(w);
      uni_[w] += std::stoll(p[2]);
    } else if (p.size() == 4 && p[0] == "B") {
      const std::u32string a = FromUtf8(p[1]);
      const int64_t c = std::stoll(p[3]);
      bi_[a][FromUtf8(p[2])] += c;
      left_[a] += c;
    }
  }
  Finish();
  const auto t1 = Clock::now();
  for (uint32_t id = 0; id < words_.size(); ++id) {
    for (const auto& d : Deletes(words_[id], max_edit_)) deletes_.emplace_back(Hash(d), id);
  }
  std::sort(deletes_.begin(), deletes_.end());
  deletes_.erase(std::unique(deletes_.begin(), deletes_.end()), deletes_.end());
  const auto t2 = Clock::now();
  // 補完: 先頭の数字ごとに出やすい順（同じ数は表の順）
  std::vector<uint32_t> by_freq(words_.size());
  for (uint32_t i = 0; i < by_freq.size(); ++i) by_freq[i] = i;
  std::stable_sort(by_freq.begin(), by_freq.end(),
                   [&](uint32_t x, uint32_t y) { return uni_[words_[x]] > uni_[words_[y]]; });
  std::unordered_map<uint64_t, std::vector<uint32_t>> lists;
  for (uint32_t id : by_freq) {
    const auto& w = words_[id];
    for (size_t k = 1; k < w.size(); ++k) {
      auto& lst = lists[Hash(w.substr(0, k))];
      if (lst.size() < prefix_keep) lst.push_back(id);
    }
  }
  for (const auto& kv : lists) prefix_keys_.push_back(kv.first);
  std::sort(prefix_keys_.begin(), prefix_keys_.end());
  prefix_off_.assign(1, 0);
  for (uint64_t k : prefix_keys_) {
    const auto& lst = lists[k];
    prefix_ids_.insert(prefix_ids_.end(), lst.begin(), lst.end());
    prefix_off_.push_back(static_cast<uint32_t>(prefix_ids_.size()));
  }
  const auto t3 = Clock::now();
  load_ms[0] = std::chrono::duration<double, std::milli>(t1 - t0).count();
  load_ms[1] = std::chrono::duration<double, std::milli>(t2 - t1).count();
  load_ms[2] = std::chrono::duration<double, std::milli>(t3 - t2).count();
  return true;
}

bool Model::SaveBinary(const std::string& path) const {
  std::ofstream f(path, std::ios::binary);
  if (!f) return false;
  f.write(kBinaryMagic, 8);
  Put(f, static_cast<int32_t>(max_edit_));
  Put(f, static_cast<uint64_t>(words_.size()));
  std::unordered_map<std::u32string, uint32_t> id;
  auto put_word = [&](const std::u32string& w) {
    Put(f, static_cast<uint32_t>(w.size()));
    f.write(reinterpret_cast<const char*>(w.data()), static_cast<std::streamsize>(w.size() * sizeof(char32_t)));
  };
  for (uint32_t i = 0; i < words_.size(); ++i) {
    id[words_[i]] = i;
    put_word(words_[i]);
    Put(f, uni_.at(words_[i]));
  }
  // 2 語の並び: 語は番号で持つ（<s> は 0xffffffff、1 語の表に無い語は 0x80000000 | 足した語の番号）
  std::vector<uint32_t> bi_prev, bi_word;
  std::vector<int64_t> bi_count;
  std::vector<std::u32string> extra;
  std::unordered_map<std::u32string, uint32_t> extra_id;
  auto number = [&](const std::u32string& w) -> uint32_t {
    if (w == kBos) return 0xffffffffU;
    const auto it = id.find(w);
    if (it != id.end()) return it->second;
    auto [e, added] = extra_id.emplace(w, static_cast<uint32_t>(extra.size()));
    if (added) extra.push_back(w);
    return 0x80000000U | e->second;
  };
  for (const auto& [prev, row] : bi_) {
    for (const auto& [w, c] : row) {
      bi_prev.push_back(number(prev));
      bi_word.push_back(number(w));
      bi_count.push_back(c);
    }
  }
  Put(f, static_cast<uint64_t>(extra.size()));
  for (const auto& w : extra) put_word(w);
  PutVec(f, bi_prev);
  PutVec(f, bi_word);
  PutVec(f, bi_count);
  PutVec(f, deletes_);
  PutVec(f, prefix_keys_);
  PutVec(f, prefix_off_);
  PutVec(f, prefix_ids_);
  return static_cast<bool>(f);
}

bool Model::LoadBinary(const std::string& path) {
  using Clock = std::chrono::steady_clock;
  const auto t0 = Clock::now();
  std::ifstream f(path, std::ios::binary);
  char magic[8];
  int32_t max_edit;
  uint64_t n;
  if (!f.read(magic, 8) || !Get(f, &max_edit) || !Get(f, &n)) return false;
  max_edit_ = max_edit;
  auto read_word = [&](std::u32string* w) {
    uint32_t len;
    if (!Get(f, &len)) return false;
    w->resize(len);
    return static_cast<bool>(f.read(reinterpret_cast<char*>(w->data()), len * sizeof(char32_t)));
  };
  words_.resize(n);
  uni_.reserve(n);
  for (uint64_t i = 0; i < n; ++i) {
    int64_t c;
    if (!read_word(&words_[i]) || !Get(f, &c)) return false;
    uni_[words_[i]] = c;
  }
  uint64_t n_extra;
  if (!Get(f, &n_extra)) return false;
  std::vector<std::u32string> extra(n_extra);
  for (auto& w : extra) {
    if (!read_word(&w)) return false;
  }
  std::vector<uint32_t> bi_prev, bi_word;
  std::vector<int64_t> bi_count;
  if (!GetVec(f, &bi_prev) || !GetVec(f, &bi_word) || !GetVec(f, &bi_count)) return false;
  auto word_of = [&](uint32_t x) -> const std::u32string& {
    if (x == 0xffffffffU) return kBos;
    return (x & 0x80000000U) ? extra[x & 0x7fffffffU] : words_[x];
  };
  for (size_t i = 0; i < bi_prev.size(); ++i) {
    const auto& a = word_of(bi_prev[i]);
    bi_[a][word_of(bi_word[i])] += bi_count[i];
    left_[a] += bi_count[i];
  }
  Finish();
  const auto t1 = Clock::now();
  if (!GetVec(f, &deletes_) || !GetVec(f, &prefix_keys_) || !GetVec(f, &prefix_off_) ||
      !GetVec(f, &prefix_ids_)) {
    return false;
  }
  load_ms[0] = std::chrono::duration<double, std::milli>(t1 - t0).count();
  load_ms[1] = std::chrono::duration<double, std::milli>(Clock::now() - t1).count();
  load_ms[2] = 0;
  return true;
}

double Model::LogpUni(const std::u32string& w) const {
  const auto it = uni_.find(w);
  if (it != uni_.end() && it->second) {
    return std::log(static_cast<double>(it->second) / static_cast<double>(total_));
  }
  // 表に無い語（名前など）: 長いほど出にくい
  return std::log(1.0 / static_cast<double>(total_)) - oov_char * static_cast<double>(w.size());
}

double Model::Logp(const std::u32string& prev, const std::u32string& w) const {
  const double lam = 0.6;
  const double pu = std::exp(LogpUni(w));
  double pb = 0.0;
  const auto l = left_.find(prev);
  if (l != left_.end() && l->second) {
    const auto row = bi_.find(prev);
    if (row != bi_.end()) {
      const auto c = row->second.find(w);
      if (c != row->second.end()) {
        pb = static_cast<double>(c->second) / static_cast<double>(l->second);
      }
    }
  }
  return pb != 0.0 ? std::log(lam * pb + (1 - lam) * pu) : std::log((1 - lam) * pu);
}

std::vector<std::u32string> Model::Segment(const std::u32string& text) const {
  struct Cell {
    double score;
    size_t from;
    std::u32string prev;
  };
  const size_t n = text.size();
  std::vector<std::map<std::u32string, Cell>> beams(n + 1);
  beams[0][kBos] = {0.0, 0, U""};
  const size_t reach = std::max(max_len_, static_cast<size_t>(oov_max));
  for (size_t i = 0; i < n; ++i) {
    if (beams[i].empty()) continue;
    // 上位 8 つ（同点は語の順）
    std::vector<std::pair<std::u32string, double>> top;
    for (const auto& kv : beams[i]) top.emplace_back(kv.first, kv.second.score);
    std::stable_sort(top.begin(), top.end(), [](const auto& x, const auto& y) {
      return x.second != y.second ? x.second > y.second : x.first < y.first;
    });
    if (top.size() > 8) top.resize(8);
    for (size_t j = i + 1; j <= std::min(n, i + reach); ++j) {
      const std::u32string w = text.substr(i, j - i);
      if (!uni_.count(w) && j - i > static_cast<size_t>(oov_max)) continue;
      for (const auto& [prev, score] : top) {
        const double s = score + Logp(prev, w) - word_penalty;
        auto it = beams[j].find(w);
        if (it == beams[j].end()) {
          beams[j].emplace(w, Cell{s, i, prev});
        } else if (s > it->second.score) {
          it->second = Cell{s, i, prev};
        }
      }
    }
  }
  if (beams[n].empty()) return {text};
  // 一番よいもの（同点は語の順で先のもの）
  const std::u32string* best = nullptr;
  double best_score = -std::numeric_limits<double>::infinity();
  for (const auto& kv : beams[n]) {
    if (!best || kv.second.score > best_score) {
      best = &kv.first;
      best_score = kv.second.score;
    }
  }
  std::vector<std::u32string> out;
  std::u32string w = *best;
  size_t j = n;
  while (j > 0) {
    const Cell& c = beams[j].at(w);
    out.push_back(w);
    j = c.from;
    w = c.prev;
  }
  std::reverse(out.begin(), out.end());
  return out;
}

std::vector<std::u32string> Model::Corrections(const std::u32string& w0, const std::u32string& prev,
                                               size_t limit) const {
  std::u32string w = w0;
  for (auto& ch : w) {
    if (ch >= U'A' && ch <= U'Z') ch = ch - U'A' + U'a';
  }
  std::unordered_map<std::u32string, double> cands;
  std::unordered_set<uint32_t> seen;
  for (const auto& d : Deletes(w, max_edit_)) {
    const uint64_t h = Hash(d);
    auto it = std::lower_bound(deletes_.begin(), deletes_.end(), std::make_pair(h, uint32_t{0}));
    for (; it != deletes_.end() && it->first == h; ++it) {
      const uint32_t id = it->second;
      if (!seen.insert(id).second) continue;
      const auto& c = words_[id];
      if (EditDistance(w, c) <= max_edit_) cands[c] = TypoCost(w, c);
    }
  }
  if (uni_.count(w)) cands[w] = 0.0;
  std::vector<std::pair<double, std::u32string>> scored;
  for (const auto& [c, cost] : cands) scored.emplace_back(-(Logp(prev, c) - typo_weight * cost), c);
  std::sort(scored.begin(), scored.end());
  std::vector<std::u32string> out;
  for (size_t i = 0; i < scored.size() && i < limit; ++i) out.push_back(scored[i].second);
  return out;
}

std::u32string Model::Complete(const std::u32string& prefix0, const std::u32string& prev) const {
  std::u32string prefix = prefix0;
  for (auto& ch : prefix) {
    if (ch >= U'A' && ch <= U'Z') ch = ch - U'A' + U'a';
  }
  const uint64_t h = Hash(prefix);
  const auto it = std::lower_bound(prefix_keys_.begin(), prefix_keys_.end(), h);
  if (it == prefix_keys_.end() || *it != h) return U"";
  const size_t k = static_cast<size_t>(it - prefix_keys_.begin());
  const std::u32string* best = nullptr;
  double best_score = 0.0;
  for (uint32_t i = prefix_off_[k]; i < prefix_off_[k + 1]; ++i) {
    const uint32_t id = prefix_ids_[i];
    // ハッシュが偶然重なった別の頭の語は除く
    if (words_[id].size() <= prefix.size() || words_[id].compare(0, prefix.size(), prefix) != 0) continue;
    const double s = Logp(prev, words_[id]);
    if (!best || s > best_score) {
      best = &words_[id];
      best_score = s;
    }
  }
  return best ? *best : U"";
}

}  // namespace centaur
