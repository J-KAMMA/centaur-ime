// Centaur IME English の識別子（2026-11-06 に作ったもの。変えると入れ直しが必要になるので変えない）。
#ifndef CENTAUR_TIP_GUIDS_H_
#define CENTAUR_TIP_GUIDS_H_

#include <windows.h>

// テキストサービス（COM の部品）
// {62395CC9-5B51-45D1-871D-D6B958F8E1C8}
inline constexpr GUID kClsidTextService = {0x62395cc9, 0x5b51, 0x45d1, {0x87, 0x1d, 0xd6, 0xb9, 0x58, 0xf8, 0xe1, 0xc8}};
// 英語（米国）の入力方式としての登録
// {BAB4A370-2B36-4E01-BE9F-F44DE0F2EAD2}
inline constexpr GUID kGuidProfile = {0xbab4a370, 0x2b36, 0x4e01, {0xbe, 0x9f, 0xf4, 0x4d, 0xe0, 0xf2, 0xea, 0xd2}};

inline constexpr LANGID kLangId = MAKELANGID(LANG_ENGLISH, SUBLANG_ENGLISH_US);
inline constexpr wchar_t kDescription[] = L"Centaur IME English";

#endif  // CENTAUR_TIP_GUIDS_H_
