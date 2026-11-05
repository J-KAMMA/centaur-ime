// 入力方式として登録されているかを確かめる（GitHub の流れで、登録の後と取り消しの後に使う）。
//   tip_check present  → 登録されていれば 0
//   tip_check absent   → 登録されていなければ 0
#include <msctf.h>
#include <windows.h>

#include <cstdio>
#include <cwchar>

#include "guids.h"

int wmain(int argc, wchar_t** argv) {
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
  std::printf("Centaur IME English: %s\n", found ? "registered" : "not registered");
  return found == want ? 0 : 1;
}
