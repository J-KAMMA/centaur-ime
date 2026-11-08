// カーソルの前の文字から今の語と前の語を切り出す所の試験。
#include <windows.h>

#include <atomic>
#include <cstdio>

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
  using centaur_tip::ParseBeforeCaret;
  auto c = ParseBeforeCaret(L"see you at the mee");
  CHECK(c.valid && c.word == U"mee" && c.prev == U"the");
  c = ParseBeforeCaret(L"Hello. Thi");
  CHECK(c.valid && c.word == U"Thi" && c.prev == U"<s>");
  c = ParseBeforeCaret(L"I don");
  CHECK(c.valid && c.word == U"don" && c.prev == U"i");
  c = ParseBeforeCaret(L"the ");  // 語の外
  CHECK(!c.valid);
  c = ParseBeforeCaret(L"");
  CHECK(!c.valid);
  c = ParseBeforeCaret(L"wor");  // 文書の頭
  CHECK(c.valid && c.word == U"wor" && c.prev == U"<s>");
  c = ParseBeforeCaret(L"THE MEE");
  CHECK(c.valid && c.word == U"MEE" && c.prev == U"the");
  c = ParseBeforeCaret(L"line one\nnex");
  CHECK(c.valid && c.prev == U"<s>");
  c = ParseBeforeCaret(L"日本語 the mee");
  CHECK(c.valid && c.word == U"mee" && c.prev == U"the");
  c = ParseBeforeCaret(L"日本語mee");  // 日本語の後ろ: 前の語は無い
  CHECK(c.valid && c.word == U"mee" && c.prev == U"<s>");
  std::wstring full(64, L'a');  // 64 字いっぱいが 1 語: 頭が見えない
  c = ParseBeforeCaret(full);
  CHECK(!c.valid);
  std::wstring long_prev = std::wstring(60, L'b') + L" mee";  // 前の語の頭が見えない
  c = ParseBeforeCaret(long_prev);
  CHECK(c.valid && c.prev == U"<s>");
  std::printf("%s (%d)\n", failures ? "NG" : "OK", failures);
  return failures ? 1 : 0;
}
