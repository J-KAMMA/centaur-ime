// 韓国語版を実際に打つ試験（GitHub のウィンドウズの機械で動かす。登録と表の置き場は流れの側で用意する）。
//   ko_e2e
// 自分の窓に TSF を使う文字の欄（RichEdit）を作り、この処理で Centaur IME Korean を有効にして、SendInput で
// 本物のキーを送り、欄の文字を読んで期待した文字と比べる。違った例を出し、全部合えば 0 を返す。
#include <msctf.h>
#include <richedit.h>
#include <windows.h>

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
  HWND top = CreateWindowExW(0, L"STATIC", L"Centaur IME Korean e2e", WS_OVERLAPPEDWINDOW | WS_VISIBLE, 100, 100, 600,
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

  ITfInputProcessorProfileMgr* mgr = nullptr;
  HRESULT hr = CoCreateInstance(CLSID_TF_InputProcessorProfiles, nullptr, CLSCTX_INPROC_SERVER,
                                IID_ITfInputProcessorProfileMgr, reinterpret_cast<void**>(&mgr));
  if (SUCCEEDED(hr)) {
    hr = mgr->ActivateProfile(TF_PROFILETYPE_INPUTPROCESSOR, kLangId, kClsidTextService, kGuidProfile, nullptr,
                              TF_IPPMF_FORPROCESS | TF_IPPMF_ENABLEPROFILE | TF_IPPMF_DONTCARECURRENTINPUTLANGUAGE);
  }
  std::printf("ActivateProfile: 0x%08lx\n", static_cast<unsigned long>(hr));
  if (FAILED(hr)) return 2;
  Pump(3000);  // 表は別の糸で読む

  struct Case {
    const char* keys;
    const wchar_t* want;
    const char* what;
  };
  // 期待する文字は、tools/ko_ime/hangul.py の compose と同じ組み立て（ko_test でも確かめている）
  const std::vector<Case> cases = {
      {"dkssudgktpdy", L"안녕하세요", "韓国語の語"},
      {"dkssud tptkd", L"안녕 세상", "空白で確定して次の語"},
      {"Rhcl", L"꼬치", "Shift で ㄲ"},
      {"dkssudr\b", L"안녕", "後退で 1 キー戻す"},
      {"rk\b\b", L"", "後退で全部消す"},
      {"dkssud1", L"안녕1", "数字で確定"},
      {"gks\nrmf", L"한\r글", "Enter で確定して改行"},
      {"~hello world~", L"hello world", "Shift+Space で英語にして戻す"},
      {"~dkssud\tgktpdy", L"안녕하세요", "英語のまま打った韓国語を Tab で入れ替えて韓国語に戻る"},
      {"~hello\tworld~", L"hello\tworld", "英語の語では Tab はそのまま"},
      {"iphone\t", L"iPhone", "韓国語のまま打ったブランド名を Tab で入れ替える"},
      {"tkfkd\t", L"사랑\t", "韓国語の語になるブランド名でない語では Tab はそのまま"},
  };
  int bad = 0;
  for (const Case& c : cases) {
    SetWindowTextW(g_edit, L"");
    SetFocus(g_edit);
    Pump(100);
    Type(c.keys);
    Type("~~");  // 英語・韓国語のどちらで終わっても、2 回切り替えて組み立てを確定し、元のモードに戻す
    std::wstring got = Text();
    const bool ok = got == c.want;
    if (!ok) ++bad;
    std::printf("%s %s: %s → 「%s」（期待「%s」）\n", ok ? "合" : "違", c.what, Shown(c.keys).c_str(),
                Utf8(got).c_str(), Utf8(c.want).c_str());
  }
  std::printf("%zu 例のうち合った %zu\n", cases.size(), cases.size() - bad);
  mgr->Release();
  DestroyWindow(top);
  CoUninitialize();
  return bad ? 1 : 0;
}
