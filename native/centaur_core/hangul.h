// ハングルと 2 ボル式（두벌식）のキーの行き来（tools/ko_ime/hangul.py と同じ計算）。
//   ToKeys(U"안녕") → U"dkssud"、Compose(U"dkssud") → U"안녕"
// 大文字は Shift（ㄲ ㄸ ㅃ ㅆ ㅉ ㅒ ㅖ）。母音が続くと前の字の終声を次の字の初声に移す。
#ifndef CENTAUR_CORE_HANGUL_H_
#define CENTAUR_CORE_HANGUL_H_

#include <string>

namespace centaur {

bool IsHangulSyllable(char32_t ch);
std::u32string ToKeys(const std::u32string& text);
std::u32string Compose(const std::u32string& keys);

}  // namespace centaur

#endif  // CENTAUR_CORE_HANGUL_H_
