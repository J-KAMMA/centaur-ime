// DLL の入り口: COM の部品の工場と、入力方式としての登録・取り消し。
#include <windows.h>
#include <msctf.h>
#include <olectl.h>

#include <atomic>
#include <string>

#include "guids.h"
#include "text_service.h"  // 韓国語のテキストサービス

HINSTANCE g_instance = nullptr;
std::atomic<long> g_dll_ref{0};

namespace {

class ClassFactory : public IClassFactory {
 public:
  STDMETHODIMP QueryInterface(REFIID riid, void** out) override {
    if (riid == IID_IUnknown || riid == IID_IClassFactory) {
      *out = static_cast<IClassFactory*>(this);
      AddRef();
      return S_OK;
    }
    *out = nullptr;
    return E_NOINTERFACE;
  }
  STDMETHODIMP_(ULONG) AddRef() override {
    ++g_dll_ref;
    return 2;
  }
  STDMETHODIMP_(ULONG) Release() override {
    --g_dll_ref;
    return 1;
  }
  STDMETHODIMP CreateInstance(IUnknown* outer, REFIID riid, void** out) override {
    if (outer) return CLASS_E_NOAGGREGATION;
    auto* ts = new (std::nothrow) centaur_tip::TextService();
    if (!ts) return E_OUTOFMEMORY;
    const HRESULT hr = ts->QueryInterface(riid, out);
    ts->Release();
    return hr;
  }
  STDMETHODIMP LockServer(BOOL lock) override {
    lock ? ++g_dll_ref : --g_dll_ref;
    return S_OK;
  }
};

ClassFactory g_factory;

std::wstring GuidString(const GUID& g) {
  wchar_t buf[64];
  StringFromGUID2(g, buf, 64);
  return buf;
}

bool SetKey(HKEY root, const std::wstring& path, const wchar_t* name, const std::wstring& value) {
  HKEY key;
  if (RegCreateKeyExW(root, path.c_str(), 0, nullptr, 0, KEY_WRITE, nullptr, &key, nullptr) != ERROR_SUCCESS) {
    return false;
  }
  const LSTATUS s = RegSetValueExW(key, name, 0, REG_SZ, reinterpret_cast<const BYTE*>(value.c_str()),
                                   static_cast<DWORD>((value.size() + 1) * sizeof(wchar_t)));
  RegCloseKey(key);
  return s == ERROR_SUCCESS;
}

// 入力方式の種類（キーボード、タスクバーの入力の表示、Windows ストアのアプリでも使う）
const GUID* const kCategories[] = {&GUID_TFCAT_TIP_KEYBOARD, &GUID_TFCAT_TIPCAP_SYSTRAYSUPPORT,
                                   &GUID_TFCAT_TIPCAP_IMMERSIVESUPPORT, &GUID_TFCAT_TIPCAP_UIELEMENTENABLED};

}  // namespace

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID) {
  if (reason == DLL_PROCESS_ATTACH) {
    g_instance = instance;
    DisableThreadLibraryCalls(instance);
  }
  return TRUE;
}

STDAPI DllGetClassObject(REFCLSID clsid, REFIID riid, void** out) {
  if (clsid != kClsidTextService) return CLASS_E_CLASSNOTAVAILABLE;
  return g_factory.QueryInterface(riid, out);
}

STDAPI DllCanUnloadNow() { return g_dll_ref.load() == 0 ? S_OK : S_FALSE; }

STDAPI DllRegisterServer() {
  wchar_t path[MAX_PATH] = {};
  GetModuleFileNameW(g_instance, path, MAX_PATH);
  const std::wstring clsid = L"CLSID\\" + GuidString(kClsidTextService);
  if (!SetKey(HKEY_CLASSES_ROOT, clsid, nullptr, kDescription) ||
      !SetKey(HKEY_CLASSES_ROOT, clsid + L"\\InprocServer32", nullptr, path) ||
      !SetKey(HKEY_CLASSES_ROOT, clsid + L"\\InprocServer32", L"ThreadingModel", L"Apartment")) {
    return SELFREG_E_CLASS;
  }
  // 64 ビットの OS の上の 32 ビットの処理（WOW64）では、部品（CLSID）の登録だけにする。入力方式の登録は
  // 64 ビット版がした 1 つを両方で使う（もう一度登録しようとすると断られる。2026-11-06 の試用で 32 ビット版が失敗）。
  BOOL wow64 = FALSE;
  IsWow64Process(GetCurrentProcess(), &wow64);
  if (wow64) return S_OK;
  const HRESULT init = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
  HRESULT hr = E_FAIL;
  ITfInputProcessorProfileMgr* mgr = nullptr;
  if (SUCCEEDED(CoCreateInstance(CLSID_TF_InputProcessorProfiles, nullptr, CLSCTX_INPROC_SERVER,
                                 IID_ITfInputProcessorProfileMgr, reinterpret_cast<void**>(&mgr)))) {
    hr = mgr->RegisterProfile(kClsidTextService, kLangId, kGuidProfile, kDescription,
                              static_cast<ULONG>(wcslen(kDescription)), path, static_cast<ULONG>(wcslen(path)), 0,
                              nullptr, 0, TRUE, 0);
    mgr->Release();
  }
  ITfCategoryMgr* cat = nullptr;
  if (SUCCEEDED(hr) && SUCCEEDED(CoCreateInstance(CLSID_TF_CategoryMgr, nullptr, CLSCTX_INPROC_SERVER,
                                                   IID_ITfCategoryMgr, reinterpret_cast<void**>(&cat)))) {
    for (const GUID* c : kCategories) cat->RegisterCategory(kClsidTextService, *c, kClsidTextService);
    cat->Release();
  }
  if (SUCCEEDED(init)) CoUninitialize();
  return SUCCEEDED(hr) ? S_OK : SELFREG_E_CLASS;
}

STDAPI DllUnregisterServer() {
  BOOL wow64 = FALSE;
  IsWow64Process(GetCurrentProcess(), &wow64);
  if (wow64) {
    RegDeleteTreeW(HKEY_CLASSES_ROOT, (L"CLSID\\" + GuidString(kClsidTextService)).c_str());
    return S_OK;
  }
  const HRESULT init = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
  ITfCategoryMgr* cat = nullptr;
  if (SUCCEEDED(CoCreateInstance(CLSID_TF_CategoryMgr, nullptr, CLSCTX_INPROC_SERVER, IID_ITfCategoryMgr,
                                 reinterpret_cast<void**>(&cat)))) {
    for (const GUID* c : kCategories) cat->UnregisterCategory(kClsidTextService, *c, kClsidTextService);
    cat->Release();
  }
  ITfInputProcessorProfileMgr* mgr = nullptr;
  if (SUCCEEDED(CoCreateInstance(CLSID_TF_InputProcessorProfiles, nullptr, CLSCTX_INPROC_SERVER,
                                 IID_ITfInputProcessorProfileMgr, reinterpret_cast<void**>(&mgr)))) {
    mgr->UnregisterProfile(kClsidTextService, kLangId, kGuidProfile, 0);
    mgr->Release();
  }
  if (SUCCEEDED(init)) CoUninitialize();
  RegDeleteTreeW(HKEY_CLASSES_ROOT, (L"CLSID\\" + GuidString(kClsidTextService)).c_str());
  return S_OK;
}
