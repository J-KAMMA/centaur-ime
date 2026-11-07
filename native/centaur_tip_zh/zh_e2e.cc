// 中国語版を実際に打つ試験（GitHub のウィンドウズの機械で動かす。登録と辞書の置き場は流れの側で用意する）。
//   zh_e2e
// 自分の窓に TSF を使う文字の欄（RichEdit）を作り、この処理で Centaur IME Chinese を有効にして、SendInput で
// 本物のキーを送り、欄の文字を読んで期待した文字と比べる。違った例を出し、全部合えば 0 を返す。
#include <msctf.h>
#include <richedit.h>
#include <windows.h>

#include <algorithm>
#include <cstdio>
#include <string>
#include <vector>

#include "guids.h"

namespace {

HWND g_edit = nullptr;

void Pump(int ms) {
  const DWORD end = GetTickCount() + ms;
  MSG msg;
  while (static_cast<int>(end - GetTickCount()) > 0) {
    while (PeekMessageW(&msg, nullptr, 0, 0, PM_REMOVE)) {
      TranslateMessage(&msg);
      DispatchMessageW(&msg);
    }
    Sleep(5);
  }
}

void Key(WORD vk, bool up) {
  INPUT in = {};
  in.type = INPUT_KEYBOARD;
  in.ki.wVk = vk;
  in.ki.wScan = static_cast<WORD>(MapVirtualKeyW(vk, MAPVK_VK_TO_VSC));
  in.ki.dwFlags = up ? KEYEVENTF_KEYUP : 0;
  SendInput(1, &in, sizeof(in));
  Pump(15);
}

void Tap(WORD vk, bool shift = false) {
  if (shift) Key(VK_SHIFT, false);
  Key(vk, false);
  Key(vk, true);
  if (shift) Key(VK_SHIFT, true);
}

// 打つ並び: 英字（大文字は Shift）、' ' 空白、'1' など数字、'\b' 後退、'\t' Tab、'~' Shift+Space（切り替え）
void Type(const std::string& s) {
  for (char c : s) {
    if (c >= 'a' && c <= 'z') {
      Tap(static_cast<WORD>('A' + (c - 'a')));
    } else if (c >= 'A' && c <= 'Z') {
      Tap(static_cast<WORD>(c), true);
    } else if (c >= '0' && c <= '9') {
      Tap(static_cast<WORD>(c));
    } else if (c == ' ') {
      Tap(VK_SPACE);
    } else if (c == '\b') {
      Tap(VK_BACK);
    } else if (c == '\t') {
      Tap(VK_TAB);
    } else if (c == '~') {
      Tap(VK_SPACE, true);
    } else if (c == '^') {
      Tap(VK_SHIFT);  // Shift だけを押して離す
    } else if (c == '\x1b') {
      Tap(VK_ESCAPE);
    } else if (c == ',') {
      Tap(VK_OEM_COMMA);
    } else if (c == '.') {
      Tap(VK_OEM_PERIOD);
    } else if (c == '=') {
      Tap(VK_OEM_PLUS);
    } else if (c == '\n') {
      Tap(VK_RETURN);
    }
  }
  Pump(200);
}

std::wstring Text() {
  const int n = GetWindowTextLengthW(g_edit);
  std::wstring s(n + 1, L'\0');
  GetWindowTextW(g_edit, s.data(), n + 1);
  s.resize(n);
  return s;
}

std::string Utf8(const std::wstring& w) {
  if (w.empty()) return {};
  const int n = WideCharToMultiByte(CP_UTF8, 0, w.data(), static_cast<int>(w.size()), nullptr, 0, nullptr, nullptr);
  std::string s(n, '\0');
  WideCharToMultiByte(CP_UTF8, 0, w.data(), static_cast<int>(w.size()), s.data(), n, nullptr, nullptr);
  return s;
}

std::string Shown(const std::string& keys) {
  std::string s;
  for (char c : keys) {
    if (c == '\b') s += "<BS>";
    else if (c == '\t') s += "<Tab>";
    else if (c == '~') s += "<Shift+Space>";
    else if (c == '^') s += "<Shift>";
    else if (c == '\x1b') s += "<Esc>";
    else if (c == '\n') s += "<Enter>";
    else s += c;
  }
  return s;
}

}  // namespace

int main() {
  SetConsoleOutputCP(CP_UTF8);
  CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
  LoadLibraryW(L"msftedit.dll");
  HWND top = CreateWindowExW(0, L"STATIC", L"Centaur IME Chinese e2e", WS_OVERLAPPEDWINDOW | WS_VISIBLE, 100, 100, 600,
                             200, nullptr, nullptr, GetModuleHandleW(nullptr), nullptr);
  g_edit = CreateWindowExW(0, MSFTEDIT_CLASS, L"", WS_CHILD | WS_VISIBLE | ES_MULTILINE, 10, 10, 560, 140, top, nullptr,
                           GetModuleHandleW(nullptr), nullptr);
  if (!top || !g_edit) {
    std::printf("窓を作れない\n");
    return 2;
  }
  SendMessageW(g_edit, EM_SETEDITSTYLE, SES_USECTF, SES_USECTF);  // RichEdit に TSF を使わせる
  SetForegroundWindow(top);
  SetFocus(g_edit);
  Pump(500);

  wchar_t trace[MAX_PATH];
  GetTempPathW(MAX_PATH, trace);
  wcscat_s(trace, L"centaur-zh-trace.txt");
  DeleteFileW(trace);
  SetEnvironmentVariableW(L"CENTAUR_ZH_TRACE", trace);
  ITfInputProcessorProfileMgr* mgr = nullptr;
  HRESULT hr = CoCreateInstance(CLSID_TF_InputProcessorProfiles, nullptr, CLSCTX_INPROC_SERVER,
                                IID_ITfInputProcessorProfileMgr, reinterpret_cast<void**>(&mgr));
  if (SUCCEEDED(hr)) {
    hr = mgr->ActivateProfile(TF_PROFILETYPE_INPUTPROCESSOR, kLangId, kClsidTextService, kGuidProfile, nullptr,
                              TF_IPPMF_FORPROCESS | TF_IPPMF_ENABLEPROFILE | TF_IPPMF_DONTCARECURRENTINPUTLANGUAGE);
  }
  std::printf("ActivateProfile: 0x%08lx\n", static_cast<unsigned long>(hr));
  if (FAILED(hr)) return 2;
  Pump(8000);  // Rime は別の糸で始める（初めては利用者の置き場の設定を組み立てる）

  struct Case {
    const char* keys;
    const wchar_t* want;
    const char* what;
  };
  // 期待する文字は、tools/ko_ime/hangul.py の compose と同じ組み立て（ko_test でも確かめている）
  const std::vector<Case> cases = {
      {"nihao ", L"你好", "空白で一番の候補"},
      {"zhongguo ", L"中国", "語"},
      {"jintiantianqihenhao ", L"今天天气很好", "文"},
      {"shi2", L"时", "数字で 2 番目の候補"},
      {"nihaoo\b ", L"你好", "後退で 1 字戻す"},
      {"nihao\x1b", L"", "Esc で取り消す"},
      {"nihao\n", L"nihao", "Enter で打った英字のまま"},
      {"nihao,", L"你好，", "記号で一番の候補を確定し、記号は全角"},
      {"wo.", L"我。", "句点で一番の候補を確定（ページ送りにしない）"},
      {"123", L"123", "組み立てていないときの数字はそのまま"},
      {"~hello world~", L"hello world", "Shift+Space で英語にして戻す"},
      {"^hello^", L"hello", "Shift だけで英語にして戻す"},
      {"nihao~~", L"nihao", "組み立て中に切り替えると打った英字のまま"},
      {"woyongiphone ", L"我用iPhone", "英単語まじり: 英単語を正式な書き方で残す"},
      {"nihaogithub ", L"你好GitHub", "英単語まじり: 後ろの英単語"},
      {"iphonehenhao ", L"iPhone很好", "英単語まじり: 前の英単語"},
      {"women ", L"我们", "拼音として読める語（women）は英語にしない"},
  };
  int bad = 0;
  for (const Case& c : cases) {
    SetWindowTextW(g_edit, L"");
    SetFocus(g_edit);
    Pump(100);
    Type(c.keys);
    std::wstring got = Text();
    // RichEdit は改行を \r\n で返すことがある（期待は \r だけで書く）
    got.erase(std::remove(got.begin(), got.end(), L'\n'), got.end());
    const bool ok = got == c.want;
    if (!ok) ++bad;
    std::printf("%s %s: %s → 「%s」（期待「%s」）\n", ok ? "合" : "違", c.what, Shown(c.keys).c_str(),
                Utf8(got).c_str(), Utf8(c.want).c_str());
  }
  std::printf("%zu 例のうち合った %zu\n", cases.size(), cases.size() - bad);
  // IME が受け取ったキーの記録（Shift の例の原因を見る）
  if (FILE* f = _wfopen(trace, L"rb")) {
    char line[128];
    int n = 0;
    std::printf("受け取ったキー（終わりの 60）:\n");
    std::vector<std::string> lines;
    while (fgets(line, sizeof(line), f)) lines.emplace_back(line);
    fclose(f);
    for (size_t i = lines.size() > 60 ? lines.size() - 60 : 0; i < lines.size(); ++i, ++n) std::printf("  %s", lines[i].c_str());
  }
  mgr->Release();
  DestroyWindow(top);
  CoUninitialize();
  return bad ? 1 : 0;
}
