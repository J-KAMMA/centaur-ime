// 字の単位の小さな模型（tools/models/tiny_gpt.py の TinyGPT）を CPU で動かす。学習はしない。
// 重みは tools/models/export_tiny.py が書いた形（頭に "CTLM1"）。前の字の計算を覚えて（KV キャッシュ）、1 字ずつ進める。
// 中国語では、拼音の音節ごとに、その読みを持つ字の中から一番確からしい字を選んだ答えを作り（Greedy）、
// Rime の答えと比べる点数（Score: 拼音の後にその字の並びが続く対数の確からしさ）を出す（tools/models/rr_zh.py と同じ）。
#ifndef CENTAUR_CORE_TINY_LM_H_
#define CENTAUR_CORE_TINY_LM_H_

#include <filesystem>
#include <string>
#include <unordered_map>
#include <vector>

namespace centaur {

class TinyLm {
 public:
  bool Load(const std::filesystem::path& path);
  bool loaded() const { return d_ > 0; }

  // 字（UTF-8 の 1 字）の番号。知らない字は unk。
  int Id(const std::string& ch) const;
  std::vector<int> Encode(const std::string& utf8) const;

  // 拼音の音節の並び（ni hao）から、音節ごとに読みの合う字を 1 字ずつ選ぶ。選べない音節があれば空。
  std::string Greedy(const std::vector<std::string>& syllables) const;
  // 「<始め>音節を空白でつないだもの<区切り>」の後に text が続く対数の確からしさ。長すぎれば非常に小さい値。
  double Score(const std::vector<std::string>& syllables, const std::string& text) const;

  size_t vocab() const { return chars_.size(); }

  static constexpr int kPad = 0, kBos = 1, kSep = 2, kEos = 3, kSpecial = 4;

 private:
  struct Layer {
    std::vector<float> ln1_w, ln1_b, in_w, in_b, out_w, out_b, ln2_w, ln2_b, fc1_w, fc1_b, fc2_w, fc2_b;
  };
  // 1 つの並びを読んでいる途中の様子（字ごとの K と V）
  struct State {
    std::vector<std::vector<float>> k, v;  // 層ごと: [位置 * d]
    int n = 0;
  };
  // 次の字を読み、その後に続く字の対数の確からしさ（全部の字）を返す
  std::vector<float> Step(State* st, int id) const;
  std::vector<int> Prefix(const std::vector<std::string>& syllables) const;

  int vocab_size_ = 0, d_ = 0, layers_ = 0, heads_ = 0, max_len_ = 0;
  std::vector<float> tok_, pos_, ln_w_, ln_b_;
  std::vector<Layer> layer_;
  std::vector<std::string> chars_;
  std::unordered_map<std::string, int> index_;
  std::unordered_map<std::string, std::vector<int>> readings_;  // 音節 → その読みを持つ字の番号
};

}  // namespace centaur

#endif  // CENTAUR_CORE_TINY_LM_H_
