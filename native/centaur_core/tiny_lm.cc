#include "tiny_lm.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>

namespace centaur {
namespace {

bool ReadI32(std::ifstream& in, int32_t* v) { return static_cast<bool>(in.read(reinterpret_cast<char*>(v), 4)); }

bool ReadF(std::ifstream& in, std::vector<float>* v, size_t n) {
  v->resize(n);
  return static_cast<bool>(in.read(reinterpret_cast<char*>(v->data()), static_cast<std::streamsize>(n * 4)));
}

bool ReadStr(std::ifstream& in, std::string* s) {
  int32_t n = 0;
  if (!ReadI32(in, &n) || n < 0 || n > (1 << 20)) return false;
  s->resize(static_cast<size_t>(n));
  return n == 0 || static_cast<bool>(in.read(s->data(), n));
}

void LayerNorm(const float* x, const std::vector<float>& w, const std::vector<float>& b, int d, float* out) {
  double mean = 0, var = 0;
  for (int i = 0; i < d; ++i) mean += x[i];
  mean /= d;
  for (int i = 0; i < d; ++i) var += (x[i] - mean) * (x[i] - mean);
  var /= d;
  const double inv = 1.0 / std::sqrt(var + 1e-5);
  for (int i = 0; i < d; ++i) out[i] = static_cast<float>((x[i] - mean) * inv) * w[i] + b[i];
}

// out[r] = W[r, :] · x + b[r]（W は rows × cols、行ごとに並ぶ。PyTorch の Linear と同じ）
void MatVec(const std::vector<float>& w, const float* b, const float* x, int rows, int cols, float* out) {
  for (int r = 0; r < rows; ++r) {
    const float* row = w.data() + static_cast<size_t>(r) * cols;
    float s = 0;
    for (int c = 0; c < cols; ++c) s += row[c] * x[c];
    out[r] = s + (b ? b[r] : 0.0f);
  }
}

// UTF-8 を 1 字ずつに分ける
std::vector<std::string> Chars(const std::string& s) {
  std::vector<std::string> out;
  for (size_t i = 0; i < s.size();) {
    const auto c = static_cast<unsigned char>(s[i]);
    const size_t len = c < 0x80 ? 1 : c < 0xE0 ? 2 : c < 0xF0 ? 3 : 4;
    out.push_back(s.substr(i, len));
    i += len;
  }
  return out;
}

}  // namespace

bool TinyLm::Load(const std::filesystem::path& path) {
  std::ifstream in(path, std::ios::binary);
  char magic[5] = {};
  if (!in.read(magic, 5) || memcmp(magic, "CTLM1", 5) != 0) return false;
  int32_t v = 0, d = 0, l = 0, h = 0, m = 0;
  if (!ReadI32(in, &v) || !ReadI32(in, &d) || !ReadI32(in, &l) || !ReadI32(in, &h) || !ReadI32(in, &m)) return false;
  if (v <= kSpecial || d <= 0 || l <= 0 || h <= 0 || d % h || m <= 0) return false;
  const size_t D = static_cast<size_t>(d);
  if (!ReadF(in, &tok_, static_cast<size_t>(v) * D) || !ReadF(in, &pos_, static_cast<size_t>(m) * D)) return false;
  layer_.resize(static_cast<size_t>(l));
  for (Layer& y : layer_) {
    if (!ReadF(in, &y.ln1_w, D) || !ReadF(in, &y.ln1_b, D) || !ReadF(in, &y.in_w, 3 * D * D) ||
        !ReadF(in, &y.in_b, 3 * D) || !ReadF(in, &y.out_w, D * D) || !ReadF(in, &y.out_b, D) ||
        !ReadF(in, &y.ln2_w, D) || !ReadF(in, &y.ln2_b, D) || !ReadF(in, &y.fc1_w, 4 * D * D) ||
        !ReadF(in, &y.fc1_b, 4 * D) || !ReadF(in, &y.fc2_w, 4 * D * D) || !ReadF(in, &y.fc2_b, D)) {
      return false;
    }
  }
  if (!ReadF(in, &ln_w_, D) || !ReadF(in, &ln_b_, D)) return false;
  int32_t nchars = 0;
  if (!ReadI32(in, &nchars) || nchars != v - kSpecial - 1) return false;
  chars_.resize(static_cast<size_t>(nchars));
  for (int i = 0; i < nchars; ++i) {
    if (!ReadStr(in, &chars_[i])) return false;
    index_[chars_[i]] = i + kSpecial;
  }
  int32_t nread = 0;
  if (!ReadI32(in, &nread)) return false;
  for (int i = 0; i < nread; ++i) {
    std::string syl, chars;
    if (!ReadStr(in, &syl) || !ReadStr(in, &chars)) return false;
    auto& ids = readings_[syl];
    for (const auto& ch : Chars(chars)) {
      const auto it = index_.find(ch);
      if (it != index_.end()) ids.push_back(it->second);
    }
  }
  vocab_size_ = v;
  d_ = d;
  layers_ = l;
  heads_ = h;
  max_len_ = m;
  return true;
}

int TinyLm::Id(const std::string& ch) const {
  const auto it = index_.find(ch);
  return it == index_.end() ? kSpecial + static_cast<int>(chars_.size()) : it->second;
}

std::vector<int> TinyLm::Encode(const std::string& utf8) const {
  std::vector<int> out;
  for (const auto& ch : Chars(utf8)) out.push_back(Id(ch));
  return out;
}

std::vector<float> TinyLm::Step(State* st, int id) const {
  const int d = d_, dh = d_ / heads_, t = st->n;
  if (st->k.empty()) {
    st->k.resize(static_cast<size_t>(layers_));
    st->v.resize(static_cast<size_t>(layers_));
  }
  std::vector<float> x(d), h(d), qkv(3 * d), att(d), a(d), m(4 * d), y(d);
  for (int i = 0; i < d; ++i) x[i] = tok_[static_cast<size_t>(id) * d + i] + pos_[static_cast<size_t>(t) * d + i];
  for (int L = 0; L < layers_; ++L) {
    const Layer& w = layer_[L];
    LayerNorm(x.data(), w.ln1_w, w.ln1_b, d, h.data());
    MatVec(w.in_w, w.in_b.data(), h.data(), 3 * d, d, qkv.data());
    auto& K = st->k[L];
    auto& V = st->v[L];
    K.insert(K.end(), qkv.begin() + d, qkv.begin() + 2 * d);
    V.insert(V.end(), qkv.begin() + 2 * d, qkv.end());
    const float scale = 1.0f / std::sqrt(static_cast<float>(dh));
    std::vector<float> s(static_cast<size_t>(t) + 1);
    for (int hd = 0; hd < heads_; ++hd) {
      const float* q = qkv.data() + hd * dh;
      float mx = -1e30f;
      for (int j = 0; j <= t; ++j) {
        const float* kk = K.data() + static_cast<size_t>(j) * d + hd * dh;
        float dot = 0;
        for (int c = 0; c < dh; ++c) dot += q[c] * kk[c];
        s[j] = dot * scale;
        mx = std::max(mx, s[j]);
      }
      double sum = 0;
      for (int j = 0; j <= t; ++j) sum += (s[j] = std::exp(s[j] - mx));
      for (int c = 0; c < dh; ++c) {
        double o = 0;
        for (int j = 0; j <= t; ++j) o += s[j] * V[static_cast<size_t>(j) * d + hd * dh + c];
        att[hd * dh + c] = static_cast<float>(o / sum);
      }
    }
    MatVec(w.out_w, w.out_b.data(), att.data(), d, d, a.data());
    for (int i = 0; i < d; ++i) x[i] += a[i];
    LayerNorm(x.data(), w.ln2_w, w.ln2_b, d, h.data());
    MatVec(w.fc1_w, w.fc1_b.data(), h.data(), 4 * d, d, m.data());
    for (auto& z : m) z = 0.5f * z * (1.0f + std::erf(z / std::sqrt(2.0f)));  // GELU（PyTorch の既定と同じ erf の形）
    MatVec(w.fc2_w, w.fc2_b.data(), m.data(), d, 4 * d, y.data());
    for (int i = 0; i < d; ++i) x[i] += y[i];
  }
  LayerNorm(x.data(), ln_w_, ln_b_, d, h.data());
  std::vector<float> logits(static_cast<size_t>(vocab_size_));
  MatVec(tok_, nullptr, h.data(), vocab_size_, d, logits.data());  // 出の重みは入りの重みと同じ
  float mx = -1e30f;
  for (float z : logits) mx = std::max(mx, z);
  double sum = 0;
  for (float z : logits) sum += std::exp(static_cast<double>(z - mx));
  const float lse = mx + static_cast<float>(std::log(sum));
  for (auto& z : logits) z -= lse;
  st->n = t + 1;
  return logits;
}

std::vector<int> TinyLm::Prefix(const std::vector<std::string>& syllables) const {
  std::string joined;
  for (size_t i = 0; i < syllables.size(); ++i) joined += (i ? " " : "") + syllables[i];
  std::vector<int> ids{kBos};
  for (int id : Encode(joined)) ids.push_back(id);
  ids.push_back(kSep);
  return ids;
}

std::string TinyLm::Greedy(const std::vector<std::string>& syllables) const {
  if (!loaded()) return {};
  const std::vector<int> prefix = Prefix(syllables);
  if (static_cast<int>(prefix.size() + syllables.size()) > max_len_) return {};
  State st;
  std::vector<float> lp;
  for (int id : prefix) lp = Step(&st, id);
  std::string out;
  for (const auto& s : syllables) {
    const auto it = readings_.find(s);
    if (it == readings_.end() || it->second.empty()) {
      out += "?";  // rr_zh.py と同じ（読みの合う字が無い音節）
      continue;
    }
    int best = -1;
    for (int id : it->second) {
      if (best < 0 || lp[id] > lp[best] || (lp[id] == lp[best] && chars_[id - kSpecial] > chars_[best - kSpecial])) {
        best = id;
      }
    }
    out += chars_[best - kSpecial];
    lp = Step(&st, best);
  }
  return out;
}

double TinyLm::Score(const std::vector<std::string>& syllables, const std::string& text) const {
  if (!loaded()) return -1e30;
  const std::vector<int> prefix = Prefix(syllables);
  const std::vector<int> cont = Encode(text);
  if (static_cast<int>(prefix.size() + cont.size()) > max_len_) return -1e30;
  State st;
  std::vector<float> lp;
  for (int id : prefix) lp = Step(&st, id);
  double s = 0;
  for (size_t k = 0; k < cont.size(); ++k) {
    s += lp[cont[k]];
    if (k + 1 < cont.size()) lp = Step(&st, cont[k]);
  }
  return s;
}

}  // namespace centaur
