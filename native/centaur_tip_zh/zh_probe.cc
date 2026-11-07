// Rime を窓なしで呼んで、拼音を打ったときの確定した文字が期待どおりかを見る（GitHub の流れで使う）。
//   zh_probe <rime.dll> <配る辞書> <利用者の置き場>
#include <windows.h>

#include <cstdio>
#include <string>
#include <vector>

#include "rime_engine.h"

namespace {

std::string Utf8(const std::wstring& w) {
  if (w.empty()) return {};
  const int n = WideCharToMultiByte(CP_UTF8, 0, w.data(), static_cast<int>(w.size()), nullptr, 0, nullptr, nullptr);
  std::string s(n, '\0');
  WideCharToMultiByte(CP_UTF8, 0, w.data(), static_cast<int>(w.size()), s.data(), n, nullptr, nullptr);
  return s;
}

}  // namespace

int wmain(int argc, wchar_t** argv) {
  SetConsoleOutputCP(CP_UTF8);
  if (argc != 4) {
    std::printf("usage: zh_probe rime.dll shared user\n");
    return 2;
  }
  centaur_zh::RimeEngine e;
  const DWORD t0 = GetTickCount();
  if (!e.Start(argv[1], argv[2], argv[3])) {
    std::printf("Rime を始められない\n");
    return 2;
  }
  std::printf("始めるのにかかった時間 %lu ミリ秒\n", GetTickCount() - t0);
  struct Case {
    const char* keys;  // 打つ英字と、最後に空白（一番の候補で確定）
    const wchar_t* want;
  };
  const std::vector<Case> cases = {
      {"nihao ", L"你好"},       {"zhongguo ", L"中国"},  {"women ", L"我们"},
      {"xiexie ", L"谢谢"},      {"beijing ", L"北京"},   {"jintiantianqihenhao ", L"今天天气很好"},
      {"wohenxihuanni ", L"我很喜欢你"},
  };
  int bad = 0;
  for (const Case& c : cases) {
    std::wstring got;
    std::vector<std::wstring> first;
    for (const char* k = c.keys; *k; ++k) {
      e.Key(static_cast<unsigned char>(*k));
      const centaur_zh::State st = e.Read();
      got += st.commit;
      if (*k != ' ') first = st.candidates;
    }
    const bool ok = got == c.want;
    bad += !ok;
    std::string cands;
    for (size_t i = 0; i < first.size() && i < 5; ++i) cands += (i ? " " : "") + Utf8(first[i]);
    std::printf("%s %s → 「%s」（期待「%s」） 候補: %s\n", ok ? "合" : "違", c.keys, Utf8(got).c_str(),
                Utf8(c.want).c_str(), cands.c_str());
    e.Clear();
  }
  // 数字で 2 番目の候補を選ぶ
  for (const char* k = "shi"; *k; ++k) e.Key(*k);
  const auto before = e.Read();
  e.Key('2');
  const auto after = e.Read();
  const bool second = before.candidates.size() >= 2 && after.commit == before.candidates[1];
  bad += !second;
  std::printf("%s shi 2 → 「%s」（2 番目の候補「%s」）\n", second ? "合" : "違", Utf8(after.commit).c_str(),
              before.candidates.size() >= 2 ? Utf8(before.candidates[1]).c_str() : "");
  std::printf("%zu 例のうち合った %zu\n", cases.size() + 1, cases.size() + 1 - bad);
  return bad ? 1 : 0;
}
