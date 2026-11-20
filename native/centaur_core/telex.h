// ベトナム語の Telex の組み立て（tools/vi_ime/telex.py と同じ計算）。
//   TelexCompose(U"tieengs vieetj") → U"tiếng việt"
// aa→â aw→ă ee→ê oo→ô ow→ơ uw→ư dd→đ、声調は s f r x j（z で外す）。声調の置き場は新しい書き方。
#ifndef CENTAUR_CORE_TELEX_H_
#define CENTAUR_CORE_TELEX_H_

#include <string>

namespace centaur {

std::u32string TelexCompose(const std::u32string& keys);

}  // namespace centaur

#endif  // CENTAUR_CORE_TELEX_H_
