// Centaur IME Korean の識別子（2026-11-07 に作ったもの。変えると入れ直しが必要になるので変えない）。
// tip_check.cc（../centaur_tip）もこの見出しで組み立てる。
#ifndef CENTAUR_TIP_GUIDS_H_
#define CENTAUR_TIP_GUIDS_H_

#include <windows.h>

// テキストサービス（COM の部品）
// {A4F2E606-C933-43B3-850D-A3DF3ECF6FAD}
inline constexpr GUID kClsidTextService = {0xa4f2e606, 0xc933, 0x43b3, {0x85, 0x0d, 0xa3, 0xdf, 0x3e, 0xcf, 0x6f, 0xad}};
// 韓国語の入力方式としての登録
// {D5CECB97-1B85-4965-A7E9-2F050FF1C1AC}
inline constexpr GUID kGuidProfile = {0xd5cecb97, 0x1b85, 0x4965, {0xa7, 0xe9, 0x2f, 0x05, 0x0f, 0xf1, 0xc1, 0xac}};

inline constexpr LANGID kLangId = MAKELANGID(LANG_KOREAN, SUBLANG_KOREAN);
inline constexpr wchar_t kDescription[] = L"Centaur IME Korean";

#endif  // CENTAUR_TIP_GUIDS_H_
