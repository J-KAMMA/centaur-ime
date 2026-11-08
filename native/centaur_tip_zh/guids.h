// Centaur IME Chinese の識別子（2026-11-07 に作ったもの。変えると入れ直しが必要になるので変えない）。
#ifndef CENTAUR_TIP_GUIDS_H_
#define CENTAUR_TIP_GUIDS_H_

#include <windows.h>

// テキストサービス（COM の部品）
// {5412FEA3-DEE9-4701-9963-05908DFACDCE}
inline constexpr GUID kClsidTextService = {0x5412fea3, 0xdee9, 0x4701, {0x99, 0x63, 0x05, 0x90, 0x8d, 0xfa, 0xcd, 0xce}};
// 中国語（簡体字、中国）の入力方式としての登録
// {0C0FE2DD-9BCE-4D62-B6F8-77EB885D4387}
inline constexpr GUID kGuidProfile = {0x0c0fe2dd, 0x9bce, 0x4d62, {0xb6, 0xf8, 0x77, 0xeb, 0x88, 0x5d, 0x43, 0x87}};

inline constexpr LANGID kLangId = MAKELANGID(LANG_CHINESE, SUBLANG_CHINESE_SIMPLIFIED);
inline constexpr wchar_t kDescription[] = L"Centaur IME Chinese";

#endif  // CENTAUR_TIP_GUIDS_H_
