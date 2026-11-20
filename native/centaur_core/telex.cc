#include "telex.h"

#include <vector>

namespace centaur {
namespace {

const std::u32string kBases = U"aăâeêioôơuưy";
const char32_t* const kToned[] = {U"aáàảãạ", U"ăắằẳẵặ", U"âấầẩẫậ", U"eéèẻẽẹ", U"êếềểễệ", U"iíìỉĩị",
                                  U"oóòỏõọ", U"ôốồổỗộ", U"ơớờởỡợ", U"uúùủũụ", U"ưứừửữự", U"yýỳỷỹỵ"};
const std::u32string kToneKeys = U"sfrxj";
const std::u32string kModified = U"ăâêôơư";

bool IsBase(char32_t c) { return kBases.find(c) != std::u32string::npos; }
bool IsHornable(char32_t c) { return c == U'a' || c == U'o' || c == U'u'; }
char32_t Horn(char32_t c) { return c == U'a' ? U'ă' : c == U'o' ? U'ơ' : U'ư'; }
char32_t Double(char32_t c) {
  switch (c) {
    case U'a':
      return U'â';
    case U'e':
      return U'ê';
    case U'o':
      return U'ô';
    case U'd':
      return U'đ';
    default:
      return 0;
  }
}
char32_t Lower(char32_t c) {
  if (c >= U'A' && c <= U'Z') return c - U'A' + U'a';
  return c;
}
char32_t Upper(char32_t c) {
  if (c >= U'a' && c <= U'z') return c - U'a' + U'A';
  // 記号つきの字は Unicode では大文字が 1 つ前（ă Ă、đ Đ、ư Ư、ơ Ơ と、ạ Ạ などの並び）にある
  switch (c) {
    case U'ă':
      return U'Ă';
    case U'â':
      return U'Â';
    case U'ê':
      return U'Ê';
    case U'ô':
      return U'Ô';
    case U'ơ':
      return U'Ơ';
    case U'ư':
      return U'Ư';
    case U'đ':
      return U'Đ';
    default:
      break;
  }
  if (c >= 0xC0 && c <= 0xFE && c != 0xF7) return c - 0x20;  // à á â ã è é ê ì í ò ó ô õ ù ú ý
  if ((c >= 0x1EA0 && c <= 0x1EF9) || (c >= 0x0100 && c <= 0x017F) || c == 0x01A1 || c == 0x01B0) {
    return (c & 1) ? c - 1 : c;
  }
  if (c == 0x0129 || c == 0x0169) return c - 1;  // ĩ ũ
  return c;
}

int TonePosition(const std::u32string& letters) {
  std::vector<int> v;
  for (size_t i = 0; i < letters.size(); ++i) {
    if (IsBase(letters[i])) v.push_back(static_cast<int>(i));
  }
  if (v.empty()) return -1;
  auto drop1 = [&] {
    if (v.size() > 1 && v[0] == 1) v.erase(v.begin());  // 位置 1 は v の先頭にしか来ない
  };
  if (letters.compare(0, 2, U"qu") == 0) drop1();
  if (letters.compare(0, 2, U"gi") == 0) drop1();
  std::vector<int> nucleus = {v[0]};
  for (size_t k = 1; k < v.size() && v[k] == nucleus.back() + 1; ++k) nucleus.push_back(v[k]);
  std::vector<int> mod;
  for (int i : nucleus) {
    if (kModified.find(letters[i]) != std::u32string::npos) mod.push_back(i);
  }
  if (!mod.empty()) {
    for (int i : mod) {
      if (letters[i] == U'ơ') return i;
    }
    return mod.back();
  }
  if (nucleus.size() == 1) return nucleus[0];
  if (static_cast<size_t>(nucleus.back() + 1) < letters.size()) return nucleus.back();
  if (nucleus.size() == 3) return nucleus[1];
  const char32_t a = letters[nucleus[0]], b = letters[nucleus[1]];
  const bool second = (a == U'o' && (b == U'a' || b == U'e')) || (a == U'u' && b == U'y');
  return second ? nucleus[1] : nucleus[0];
}

std::u32string ComposeWord(const std::u32string& keys) {
  std::u32string letters;
  std::vector<bool> upper;
  int tone = 0;
  for (char32_t k : keys) {
    const char32_t lk = Lower(k);
    const size_t tk = kToneKeys.find(lk);
    if (tk != std::u32string::npos || lk == U'z') {
      const int t = tk != std::u32string::npos ? static_cast<int>(tk) + 1 : 0;
      const bool has_vowel = TonePosition(letters) >= 0;
      if (has_vowel && lk != U'z' && tone != t) {
        tone = t;
        continue;
      }
      if (has_vowel && lk == U'z' && tone) {
        tone = 0;
        continue;
      }
      if (has_vowel && tone == t && lk != U'z') tone = 0;  // 同じ声調を 2 度: 外してその字を入れる
      letters += lk;
      upper.push_back(k != lk);
      continue;
    }
    const char32_t d = Double(lk);
    if (d && !letters.empty() && letters.back() == lk) {
      letters.back() = d;
      continue;
    }
    if (lk == U'w') {
      int hit = -1;
      for (int i = static_cast<int>(letters.size()) - 1; i >= 0; --i) {
        if (IsHornable(letters[i])) {
          if (letters[i] == U'o' && i > 0 && letters[i - 1] == U'u') letters[i - 1] = U'ư';
          letters[i] = Horn(letters[i]);
          hit = i;
          break;
        }
        if (IsBase(letters[i])) break;
      }
      if (hit >= 0) continue;
      letters += U'w';
      upper.push_back(k != lk);
      continue;
    }
    letters += lk;
    upper.push_back(k != lk);
  }
  std::u32string out = letters;
  if (tone) {
    const int p = TonePosition(letters);
    if (p >= 0) out[p] = kToned[kBases.find(letters[p])][tone];
  }
  for (size_t i = 0; i < out.size(); ++i) {
    if (upper[i]) out[i] = Upper(out[i]);
  }
  return out;
}

bool IsAsciiAlpha(char32_t c) { return (c >= U'a' && c <= U'z') || (c >= U'A' && c <= U'Z'); }

}  // namespace

std::u32string TelexCompose(const std::u32string& keys) {
  std::u32string out, word;
  for (char32_t k : keys) {
    if (IsAsciiAlpha(k)) {
      word += k;
    } else {
      if (!word.empty()) out += ComposeWord(word);
      word.clear();
      out += k;
    }
  }
  if (!word.empty()) out += ComposeWord(word);
  return out;
}

}  // namespace centaur
