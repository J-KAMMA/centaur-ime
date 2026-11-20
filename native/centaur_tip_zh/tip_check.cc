// 入力方式として登録されているかを確かめる（GitHub の流れで、登録の後と取り消しの後に使う）。
//   tip_check present  → 登録されていれば 0
//   tip_check absent   → 登録されていなければ 0
//   tip_check register <dll> / unregister <dll> → DLL を読み込んで登録・取り消しを呼び、戻り値を出す（失敗の理由を見る）
#include <msctf.h>
#include <windows.h>

#include <cstdio>
#include <cwchar>

#include "guids.h"

int wmain(int argc, wchar_t** argv) {
  if (argc > 2 && (wcscmp(argv[1], L"register") == 0 || wcscmp(argv[1], L"unregister") == 0)) {
    const bool reg = wcscmp(argv[1], L"register") == 0;
    HMODULE dll = LoadLibraryW(argv[2]);
    if (!dll) {
      std::printf("LoadLibrary failed: %lu\n", GetLastError());
      return 1;
    }
    using Fn = HRESULT(STDAPICALLTYPE*)();
    auto fn = reinterpret_cast<Fn>(GetProcAddress(dll, reg ? "DllRegisterServer" : "DllUnregisterServer"));
    if (!fn) {
      std::printf("GetProcAddress failed: %lu\n", GetLastError());
      return 1;
    }
    const HRESULT hr = fn();
    std::printf("%s: 0x%08lx\n", reg ? "DllRegisterServer" : "DllUnregisterServer", static_cast<unsigned long>(hr));
    FreeLibrary(dll);
    return SUCCEEDED(hr) ? 0 : 1;
  }
  const bool want = argc > 1 && wcscmp(argv[1], L"present") == 0;
  CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
  bool found = false;
  ITfInputProcessorProfileMgr* mgr = nullptr;
  if (SUCCEEDED(CoCreateInstance(CLSID_TF_InputProcessorProfiles, nullptr, CLSCTX_INPROC_SERVER,
                                 IID_ITfInputProcessorProfileMgr, reinterpret_cast<void**>(&mgr)))) {
    IEnumTfInputProcessorProfiles* e = nullptr;
    if (SUCCEEDED(mgr->EnumProfiles(kLangId, &e))) {
      TF_INPUTPROCESSORPROFILE p;
      ULONG n = 0;
      while (e->Next(1, &p, &n) == S_OK && n == 1) {
        if (p.clsid == kClsidTextService && p.guidProfile == kGuidProfile) found = true;
      }
      e->Release();
    }
    mgr->Release();
  }
  CoUninitialize();
  // 一覧の取り方は機械の言語の設定に左右されるので、入力方式の登録の場所（レジストリ）も直接見る
  wchar_t clsid[64], profile[64];
  StringFromGUID2(kClsidTextService, clsid, 64);
  StringFromGUID2(kGuidProfile, profile, 64);
  wchar_t path[256];
  swprintf(path, 256, L"SOFTWARE\\Microsoft\\CTF\\TIP\\%ls\\LanguageProfile\\0x%08x\\%ls", clsid,
           static_cast<unsigned>(kLangId), profile);
  HKEY key = nullptr;
  const bool in_registry =
      RegOpenKeyExW(HKEY_LOCAL_MACHINE, path, 0, KEY_READ | KEY_WOW64_64KEY, &key) == ERROR_SUCCESS;
  if (key) RegCloseKey(key);
  std::printf("Centaur IME Chinese: profile list %s, registry %s\n", found ? "yes" : "no", in_registry ? "yes" : "no");
  return in_registry == want ? 0 : 1;
}
