// Rime（librime、BSD-3-Clause）を呼ぶ部分。rime.dll は実行時に読み込む（無ければ何もしない）。
// 1 つのセッションにキーを渡し、確定した文字・組み立て中の文字（拼音）・候補をもらう。
// キーの値は Rime の決まり（X11 の keysym。英字・数字・記号は ASCII、後退は 0xff08 など）。
#ifndef CENTAUR_TIP_ZH_RIME_ENGINE_H_
#define CENTAUR_TIP_ZH_RIME_ENGINE_H_

#include <windows.h>

#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

namespace centaur_zh {

// Rime のキーの値
inline constexpr int kKeyBackSpace = 0xff08;
inline constexpr int kKeyTab = 0xff09;
inline constexpr int kKeyReturn = 0xff0d;
inline constexpr int kKeyEscape = 0xff1b;
inline constexpr int kKeyLeft = 0xff51;
inline constexpr int kKeyUp = 0xff52;
inline constexpr int kKeyRight = 0xff53;
inline constexpr int kKeyDown = 0xff54;
inline constexpr int kKeyPageUp = 0xff55;
inline constexpr int kKeyPageDown = 0xff56;
inline constexpr int kKeyHome = 0xff50;
inline constexpr int kKeyEnd = 0xff57;
inline constexpr int kKeyDelete = 0xffff;

struct State {
  std::wstring commit;                  // 確定した文字（無ければ空）
  std::wstring preedit;                 // 組み立て中の文字（拼音。無ければ空）
  std::vector<std::wstring> candidates;  // 今のページの候補
  int highlighted = 0;                  // 選んでいる候補
  int page = 0;                         // ページ（0 から）
  bool last_page = true;
};

class RimeEngine {
 public:
  RimeEngine() = default;
  ~RimeEngine();
  RimeEngine(const RimeEngine&) = delete;
  RimeEngine& operator=(const RimeEngine&) = delete;

  // dll: rime.dll、shared: 配る辞書（組み立て済みの build を含む）、user: 利用者の置き場（無ければ作る）。
  // 初めての時は利用者の置き場に設定を組み立てる（数秒かかることがある）。
  bool Start(const std::filesystem::path& dll, const std::filesystem::path& shared, const std::filesystem::path& user);
  bool ready() const { return session_ != 0; }

  // キーを渡す。Rime が使ったら true（使わなかったキーはアプリへ渡す）。
  bool Key(int keycode, int mask = 0);
  State Read();      // 確定した文字・組み立て中の文字・候補（確定した文字は読むと消える）
  std::wstring Input();  // 打ったままの英字
  void Clear();      // 組み立て中の文字を捨てる
  bool Select(int index_on_page);  // 今のページの候補を選ぶ

 private:
  HMODULE dll_ = nullptr;
  const void* api_ = nullptr;  // RimeApi*
  uintptr_t session_ = 0;  // RimeSessionId
};

}  // namespace centaur_zh

#endif  // CENTAUR_TIP_ZH_RIME_ENGINE_H_
