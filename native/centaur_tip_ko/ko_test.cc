// 韓国語版のキーの字・カーソルの前の語・見分けの決まりの試験（ウィンドウズの部品を動かさずに試せる所）。
#include <windows.h>

#include <atomic>
#include <cstdio>
#include <filesystem>
#include <fstream>

#include "../centaur_core/hangul.h"
#include "text_service.h"

HINSTANCE g_instance = nullptr;
std::atomic<long> g_dll_ref{0};

namespace {
int failures = 0;
void Check(bool ok, const char* what, int line) {
  if (!ok) {
    std::printf("NG line %d: %s\n", line, what);
    ++failures;
  }
}
#define CHECK(x) Check((x), #x, __LINE__)
}  // namespace

int main() {
  using centaur_tip::KoreanKey;
  using centaur_tip::WordBeforeCaret;
  CHECK(KoreanKey('D', false) == U'd');
  CHECK(KoreanKey('R', true) == U'R');   // ㄲ
  CHECK(KoreanKey('A', true) == U'a');   // Shift でも ㅁ
  CHECK(KoreanKey('1', false) == 0);
  CHECK(KoreanKey(VK_SPACE, false) == 0);
  CHECK(centaur::Compose(U"dkssud") == U"안녕");
  CHECK(centaur::Compose(U"dkssudgktpdy") == U"안녕하세요");
  CHECK(centaur::Compose(U"Tkdlek") == U"싸이다");

  CHECK(WordBeforeCaret(L"I said dkssud") == U"dkssud");
  CHECK(WordBeforeCaret(L"dkssud") == U"dkssud");
  CHECK(WordBeforeCaret(L"hello ") == U"");
  CHECK(WordBeforeCaret(L"123abc") == U"abc");
  CHECK(WordBeforeCaret(std::wstring(64, L'a')) == U"");

  const auto dir = std::filesystem::temp_directory_path();
  {
    std::ofstream f(dir / "ko-detect-test.tsv", std::ios::binary);
    f << "K\t안녕\nK\t사랑\nK\t아이\nE\tdkssud\nE\thello\n";
    std::ofstream c(dir / "casing-test.tsv", std::ios::binary);
    c << "# typed\tofficial\niphone\tiPhone\ndlek\tDLEK\ntkfkd\tTKFKD\nab\tAB\ngithub\t-\n";
  }
  centaur::KoDetector d;
  CHECK(d.Load(dir / "ko-detect-test.tsv"));
  CHECK(d.LoadCasing(dir / "casing-test.tsv"));
  CHECK(d.Korean(U"tkfkd") == U"사랑");
  CHECK(d.Korean(U"dkssud").empty());   // 英語の表にある（試験のために入れた）
  CHECK(d.Korean(U"hello").empty());
  CHECK(d.Korean(U"rkskek").empty());   // 가나다 は韓国語の表に無い
  CHECK(d.Brand(U"iphone") == U"iPhone");
  CHECK(d.Brand(U"IPHONE") == U"iPhone");
  CHECK(d.Brand(U"tkfkd").empty());     // 組み立てると 사랑（韓国語の語）
  CHECK(d.Brand(U"ab").empty());        // 3 字未満は使わない
  CHECK(d.Brand(U"github").empty());    // 「-」の行は使わない
  CHECK(d.brands() == 3);

  std::printf(failures ? "%d failures\n" : "OK (%d)\n", failures);
  return failures ? 1 : 0;
}
