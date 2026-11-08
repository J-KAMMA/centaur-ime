#include "hangul.h"

#include <map>
#include <vector>

namespace centaur {
namespace {

const std::u32string kInitials = U"ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ";
const std::u32string kVowels = U"ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ";
// 終声（先頭の 0 は無し。0 を含むので長さを指定して作る）
const std::u32string kFinals(U"\0ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ", 28);

const std::map<char32_t, char32_t>& JamoToKey() {
  static const std::map<char32_t, char32_t> m = {
      {U'ㄱ', U'r'}, {U'ㄲ', U'R'}, {U'ㄴ', U's'}, {U'ㄷ', U'e'}, {U'ㄸ', U'E'}, {U'ㄹ', U'f'}, {U'ㅁ', U'a'},
      {U'ㅂ', U'q'}, {U'ㅃ', U'Q'}, {U'ㅅ', U't'}, {U'ㅆ', U'T'}, {U'ㅇ', U'd'}, {U'ㅈ', U'w'}, {U'ㅉ', U'W'},
      {U'ㅊ', U'c'}, {U'ㅋ', U'z'}, {U'ㅌ', U'x'}, {U'ㅍ', U'v'}, {U'ㅎ', U'g'}, {U'ㅏ', U'k'}, {U'ㅐ', U'o'},
      {U'ㅑ', U'i'}, {U'ㅒ', U'O'}, {U'ㅓ', U'j'}, {U'ㅔ', U'p'}, {U'ㅕ', U'u'}, {U'ㅖ', U'P'}, {U'ㅗ', U'h'},
      {U'ㅛ', U'y'}, {U'ㅜ', U'n'}, {U'ㅠ', U'b'}, {U'ㅡ', U'm'}, {U'ㅣ', U'l'}};
  return m;
}

const std::map<char32_t, char32_t>& KeyToJamo() {
  static const std::map<char32_t, char32_t> m = [] {
    std::map<char32_t, char32_t> r;
    for (const auto& [j, k] : JamoToKey()) r[k] = j;
    return r;
  }();
  return m;
}

// 2 つのキーで打つ母音と終声: 合わせた字 → 前と後ろ
const std::map<char32_t, std::u32string>& Vowel2() {
  static const std::map<char32_t, std::u32string> m = {{U'ㅘ', U"ㅗㅏ"}, {U'ㅙ', U"ㅗㅐ"}, {U'ㅚ', U"ㅗㅣ"},
                                                       {U'ㅝ', U"ㅜㅓ"}, {U'ㅞ', U"ㅜㅔ"}, {U'ㅟ', U"ㅜㅣ"},
                                                       {U'ㅢ', U"ㅡㅣ"}};
  return m;
}
const std::map<char32_t, std::u32string>& Final2() {
  static const std::map<char32_t, std::u32string> m = {
      {U'ㄳ', U"ㄱㅅ"}, {U'ㄵ', U"ㄴㅈ"}, {U'ㄶ', U"ㄴㅎ"}, {U'ㄺ', U"ㄹㄱ"}, {U'ㄻ', U"ㄹㅁ"}, {U'ㄼ', U"ㄹㅂ"},
      {U'ㄽ', U"ㄹㅅ"}, {U'ㄾ', U"ㄹㅌ"}, {U'ㄿ', U"ㄹㅍ"}, {U'ㅀ', U"ㄹㅎ"}, {U'ㅄ', U"ㅂㅅ"}};
  return m;
}

char32_t Join(const std::map<char32_t, std::u32string>& table, char32_t a, char32_t b) {
  for (const auto& [k, v] : table) {
    if (v[0] == a && v[1] == b) return k;
  }
  return 0;
}

bool IsVowel(char32_t j) { return kVowels.find(j) != std::u32string::npos; }
bool IsInitial(char32_t j) { return kInitials.find(j) != std::u32string::npos; }
bool IsFinal(char32_t j) { return j && kFinals.find(j) != std::u32string::npos; }

char32_t Syllable(char32_t l, char32_t v, char32_t f) {
  const size_t fi = f ? kFinals.find(f) : 0;
  return 0xAC00 + static_cast<char32_t>(kInitials.find(l) * 588 + kVowels.find(v) * 28 + fi);
}

}  // namespace

bool IsHangulSyllable(char32_t ch) { return ch >= U'가' && ch <= U'힣'; }

std::u32string ToKeys(const std::u32string& text) {
  std::u32string jamo;
  for (char32_t ch : text) {
    if (IsHangulSyllable(ch)) {
      const char32_t i = ch - 0xAC00;
      jamo += kInitials[i / 588];
      const char32_t v = kVowels[(i % 588) / 28];
      const auto v2 = Vowel2().find(v);
      jamo += v2 != Vowel2().end() ? v2->second : std::u32string(1, v);
      const char32_t f = kFinals[i % 28];
      if (f) {
        const auto f2 = Final2().find(f);
        jamo += f2 != Final2().end() ? f2->second : std::u32string(1, f);
      }
    } else {
      jamo += ch;
    }
  }
  std::u32string out;
  for (char32_t j : jamo) {
    const auto k = JamoToKey().find(j);
    out += k != JamoToKey().end() ? k->second : j;
  }
  return out;
}

std::u32string Compose(const std::u32string& keys) {
  std::u32string out;
  char32_t l = 0, v = 0, f = 0;  // 組み立て中の初声・中声・終声
  auto flush = [&] {
    if (l && v) {
      out += Syllable(l, v, f);
    } else {
      for (char32_t x : {l, v, f}) {
        if (x) out += x;
      }
    }
    l = v = f = 0;
  };
  for (char32_t k : keys) {
    const auto it = KeyToJamo().find(k);
    const char32_t j = it != KeyToJamo().end() ? it->second : k;
    if (IsVowel(j)) {
      char32_t joined = (v && !f) ? Join(Vowel2(), v, j) : 0;
      if (l && !v) {
        v = j;
      } else if (joined) {
        v = joined;
      } else if (f) {
        // 終声を次の字の初声に移す（겹받침なら後ろの字母だけ移す）
        char32_t move;
        const auto f2 = Final2().find(f);
        if (f2 != Final2().end()) {
          f = f2->second[0];
          move = f2->second[1];
        } else {
          move = f;
          f = 0;
        }
        flush();
        l = move;
        v = j;
      } else {
        flush();
        out += j;
      }
    } else if (IsInitial(j)) {
      const char32_t joined = f ? Join(Final2(), f, j) : 0;
      if (l && v && !f && IsFinal(j)) {
        f = j;
      } else if (joined) {
        f = joined;
      } else {
        flush();
        l = j;
      }
    } else {
      flush();
      out += j;
    }
  }
  flush();
  return out;
}

}  // namespace centaur
