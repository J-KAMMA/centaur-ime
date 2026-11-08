#include "text_service.h"

#include <inputscope.h>
#include <shlobj.h>

#include <atomic>
#include <filesystem>
#include <functional>
#include <thread>

#include "../centaur_core/word_tracker.h"

extern std::atomic<long> g_dll_ref;

namespace centaur_tip {
namespace {

// 入力の種類（パスワード欄など）を持つ性質の識別子。SDK のライブラリに実体が無いことがあるので値を書く
// （inputscope.idl の GUID_PROP_INPUTSCOPE と同じ値）。
const GUID kGuidPropInputScope = {0x1713dd5a, 0x68e7, 0x4a5b, {0x9a, 0xf6, 0x59, 0x2a, 0x59, 0x5c, 0x77, 0x8d}};

// ---- 表（1 つの処理の中で 1 度だけ、別の糸で読む） ----
std::mutex g_model_mutex;
std::shared_ptr<const centaur::Model> g_model;
std::once_flag g_load_once;

std::filesystem::path TablePath() {
  wchar_t* local = nullptr;
  std::filesystem::path p;
  if (SUCCEEDED(SHGetKnownFolderPath(FOLDERID_LocalAppData, 0, nullptr, &local))) {
    p = std::filesystem::path(local) / L"CentaurIME" / L"english" / L"table.bin";
  }
  CoTaskMemFree(local);
  return p;
}

void StartLoad() {
  std::call_once(g_load_once, [] {
    ++g_dll_ref;  // 読み終わるまで DLL を外させない
    std::thread([] {
      auto m = std::make_shared<centaur::Model>();
      m->word_penalty = 3.0;  // tools/en_ime/measure.py で選んだ重み
      m->oov_char = 2.0;
      m->typo_weight = 8.0;
      const auto path = TablePath();
      if (!path.empty() && m->Load(path)) {
        // ブランド名の正式な書き方（無くても動く）
        m->LoadCasing(path.parent_path() / L"casing.tsv");
        std::lock_guard<std::mutex> lock(g_model_mutex);
        g_model = std::move(m);
      }
      --g_dll_ref;
    }).detach();
  });
}

// ---- 素通しにするアプリ（実行ファイルの名前だけで決める） ----
bool AppExcluded() {
  wchar_t path[MAX_PATH] = {};
  GetModuleFileNameW(nullptr, path, MAX_PATH);
  std::wstring name = std::filesystem::path(path).filename().wstring();
  for (auto& ch : name) ch = static_cast<wchar_t>(towlower(ch));
  static const wchar_t* const kExcluded[] = {
      L"windowsterminal.exe", L"conhost.exe", L"cmd.exe",     L"powershell.exe", L"pwsh.exe",
      L"openconsole.exe",     L"mintty.exe",  L"putty.exe",   L"mstsc.exe",      L"wezterm-gui.exe",
      L"alacritty.exe",       L"code.exe",    L"devenv.exe",  L"logonui.exe",    L"consent.exe"};
  for (const wchar_t* e : kExcluded) {
    if (name == e) return true;
  }
  return false;
}

// ---- 文字の変換 ----
std::u32string ToU32(const std::wstring& s) {
  std::u32string out;
  for (size_t i = 0; i < s.size(); ++i) {
    char32_t c = s[i];
    if (c >= 0xD800 && c <= 0xDBFF && i + 1 < s.size()) {
      c = 0x10000 + ((c - 0xD800) << 10) + (s[i + 1] - 0xDC00);
      ++i;
    }
    out.push_back(c);
  }
  return out;
}

std::wstring ToW(const std::u32string& s) {
  std::wstring out;
  for (char32_t c : s) {
    if (c >= 0x10000) {
      c -= 0x10000;
      out.push_back(static_cast<wchar_t>(0xD800 + (c >> 10)));
      out.push_back(static_cast<wchar_t>(0xDC00 + (c & 0x3ff)));
    } else {
      out.push_back(static_cast<wchar_t>(c));
    }
  }
  return out;
}

bool IsWordChar(char32_t c) { return (c >= U'a' && c <= U'z') || (c >= U'A' && c <= U'Z') || c == U'\''; }

// ---- 編集の決まりごと（関数を渡すだけの編集セッション） ----
class EditSession : public ITfEditSession {
 public:
  explicit EditSession(std::function<HRESULT(TfEditCookie)> f) : f_(std::move(f)) {}
  STDMETHODIMP QueryInterface(REFIID riid, void** out) override {
    if (riid == IID_IUnknown || riid == IID_ITfEditSession) {
      *out = static_cast<ITfEditSession*>(this);
      AddRef();
      return S_OK;
    }
    *out = nullptr;
    return E_NOINTERFACE;
  }
  STDMETHODIMP_(ULONG) AddRef() override { return InterlockedIncrement(&ref_); }
  STDMETHODIMP_(ULONG) Release() override {
    const LONG r = InterlockedDecrement(&ref_);
    if (!r) delete this;
    return r;
  }
  STDMETHODIMP DoEditSession(TfEditCookie ec) override { return f_(ec); }

 private:
  LONG ref_ = 1;
  std::function<HRESULT(TfEditCookie)> f_;
};

// カーソルの前の最大 64 字を読む。選択が空でない・読めないときは false。
bool ReadBeforeCaret(ITfContext* ctx, TfEditCookie ec, std::wstring* text, ITfRange** caret) {
  TF_SELECTION sel = {};
  ULONG n = 0;
  if (FAILED(ctx->GetSelection(ec, TF_DEFAULT_SELECTION, 1, &sel, &n)) || n != 1 || !sel.range) return false;
  BOOL empty = FALSE;
  sel.range->IsEmpty(ec, &empty);
  bool ok = false;
  ITfRange* r = nullptr;
  if (empty && SUCCEEDED(sel.range->Clone(&r))) {
    LONG shifted = 0;
    r->Collapse(ec, TF_ANCHOR_START);
    r->ShiftStart(ec, -64, &shifted, nullptr);
    wchar_t buf[65] = {};
    ULONG got = 0;
    if (SUCCEEDED(r->GetText(ec, 0, buf, 64, &got))) {
      text->assign(buf, got);
      ok = true;
    }
    r->Release();
  }
  if (ok && caret) {
    *caret = sel.range;
  } else {
    sel.range->Release();
  }
  return ok;
}

}  // namespace

Context ParseBeforeCaret(const std::wstring& wtext) {
  const std::u32string t = ToU32(wtext);
  Context c;
  size_t i = t.size();
  while (i > 0 && IsWordChar(t[i - 1])) --i;
  c.word = t.substr(i);
  // 64 字いっぱいが 1 語なら、語の頭が見えていないので使わない
  if (c.word.empty() || (i == 0 && t.size() >= 64)) return c;
  c.prev = U"<s>";
  size_t j = i;
  while (j > 0 && !IsWordChar(t[j - 1])) {
    const char32_t ch = t[j - 1];
    if (ch == U'.' || ch == U'!' || ch == U'?' || ch == U'\n' || ch == U'\r') {
      c.valid = true;
      return c;  // 文の頭
    }
    --j;
  }
  size_t k = j;
  while (k > 0 && IsWordChar(t[k - 1])) --k;
  if (k == 0 && j > 0 && t.size() >= 64) {
    c.valid = true;  // 前の語の頭が見えていない: 前の語は分からないことにする
    return c;
  }
  if (j > k) {
    std::u32string p = t.substr(k, j - k);
    for (auto& ch : p) {
      if (ch >= U'A' && ch <= U'Z') ch = ch - U'A' + U'a';
    }
    c.prev = p;
  }
  c.valid = true;
  return c;
}

TextService::TextService() { ++g_dll_ref; }
TextService::~TextService() { --g_dll_ref; }

STDMETHODIMP TextService::QueryInterface(REFIID riid, void** out) {
  if (!out) return E_INVALIDARG;
  *out = nullptr;
  if (riid == IID_IUnknown || riid == IID_ITfTextInputProcessor || riid == IID_ITfTextInputProcessorEx) {
    *out = static_cast<ITfTextInputProcessorEx*>(this);
  } else if (riid == IID_ITfKeyEventSink) {
    *out = static_cast<ITfKeyEventSink*>(this);
  } else if (riid == IID_ITfThreadMgrEventSink) {
    *out = static_cast<ITfThreadMgrEventSink*>(this);
  } else if (riid == IID_ITfTextEditSink) {
    *out = static_cast<ITfTextEditSink*>(this);
  }
  if (!*out) return E_NOINTERFACE;
  AddRef();
  return S_OK;
}

STDMETHODIMP_(ULONG) TextService::AddRef() { return InterlockedIncrement(&ref_); }
STDMETHODIMP_(ULONG) TextService::Release() {
  const LONG r = InterlockedDecrement(&ref_);
  if (!r) delete this;
  return r;
}

STDMETHODIMP TextService::Activate(ITfThreadMgr* tm, TfClientId id) { return ActivateEx(tm, id, 0); }

STDMETHODIMP TextService::ActivateEx(ITfThreadMgr* tm, TfClientId id, DWORD) {
  thread_mgr_ = tm;
  thread_mgr_->AddRef();
  client_id_ = id;
  app_allowed_ = !AppExcluded();
  ITfSource* source = nullptr;
  if (SUCCEEDED(thread_mgr_->QueryInterface(IID_ITfSource, reinterpret_cast<void**>(&source)))) {
    source->AdviseSink(IID_ITfThreadMgrEventSink, static_cast<ITfThreadMgrEventSink*>(this), &thread_mgr_cookie_);
    source->Release();
  }
  ITfKeystrokeMgr* keys = nullptr;
  if (SUCCEEDED(thread_mgr_->QueryInterface(IID_ITfKeystrokeMgr, reinterpret_cast<void**>(&keys)))) {
    keys->AdviseKeyEventSink(client_id_, static_cast<ITfKeyEventSink*>(this), TRUE);
    keys->Release();
  }
  ITfDocumentMgr* focus = nullptr;
  if (SUCCEEDED(thread_mgr_->GetFocus(&focus)) && focus) {
    WatchDocument(focus);
    focus->Release();
  }
  if (app_allowed_) StartLoad();
  return S_OK;
}

STDMETHODIMP TextService::Deactivate() {
  Clear();
  WatchDocument(nullptr);
  if (thread_mgr_) {
    ITfKeystrokeMgr* keys = nullptr;
    if (SUCCEEDED(thread_mgr_->QueryInterface(IID_ITfKeystrokeMgr, reinterpret_cast<void**>(&keys)))) {
      keys->UnadviseKeyEventSink(client_id_);
      keys->Release();
    }
    ITfSource* source = nullptr;
    if (thread_mgr_cookie_ != TF_INVALID_COOKIE &&
        SUCCEEDED(thread_mgr_->QueryInterface(IID_ITfSource, reinterpret_cast<void**>(&source)))) {
      source->UnadviseSink(thread_mgr_cookie_);
      source->Release();
    }
    thread_mgr_cookie_ = TF_INVALID_COOKIE;
    thread_mgr_->Release();
    thread_mgr_ = nullptr;
  }
  client_id_ = TF_CLIENTID_NULL;
  return S_OK;
}

void TextService::WatchDocument(ITfDocumentMgr* dim) {
  if (watched_) {
    ITfSource* source = nullptr;
    if (text_edit_cookie_ != TF_INVALID_COOKIE &&
        SUCCEEDED(watched_->QueryInterface(IID_ITfSource, reinterpret_cast<void**>(&source)))) {
      source->UnadviseSink(text_edit_cookie_);
      source->Release();
    }
    text_edit_cookie_ = TF_INVALID_COOKIE;
    watched_->Release();
    watched_ = nullptr;
  }
  if (!dim) return;
  ITfContext* ctx = nullptr;
  if (FAILED(dim->GetTop(&ctx)) || !ctx) return;
  ITfSource* source = nullptr;
  if (SUCCEEDED(ctx->QueryInterface(IID_ITfSource, reinterpret_cast<void**>(&source)))) {
    if (SUCCEEDED(source->AdviseSink(IID_ITfTextEditSink, static_cast<ITfTextEditSink*>(this), &text_edit_cookie_))) {
      watched_ = ctx;
      ctx->AddRef();
    }
    source->Release();
  }
  ctx->Release();
}

void TextService::Clear() {
  word_.clear();
  insert_.clear();
  replace_.clear();
  popup_.Hide();
}

std::shared_ptr<const centaur::Model> TextService::model() const {
  std::lock_guard<std::mutex> lock(g_model_mutex);
  return g_model;
}

bool TextService::Allowed(ITfContext* ctx, TfEditCookie ec) {
  if (!app_allowed_) return false;
  TF_STATUS status = {};
  if (SUCCEEDED(ctx->GetStatus(&status)) && (status.dwDynamicFlags & TF_SD_READONLY)) return false;
  // パスワード欄などの入力の種類
  bool ok = true;
  ITfReadOnlyProperty* prop = nullptr;
  if (SUCCEEDED(ctx->GetAppProperty(kGuidPropInputScope, &prop)) && prop) {
    TF_SELECTION sel = {};
    ULONG n = 0;
    if (SUCCEEDED(ctx->GetSelection(ec, TF_DEFAULT_SELECTION, 1, &sel, &n)) && n == 1 && sel.range) {
      VARIANT v;
      VariantInit(&v);
      if (SUCCEEDED(prop->GetValue(ec, sel.range, &v)) && v.vt == VT_UNKNOWN && v.punkVal) {
        ITfInputScope* scope = nullptr;
        if (SUCCEEDED(v.punkVal->QueryInterface(__uuidof(ITfInputScope), reinterpret_cast<void**>(&scope)))) {
          InputScope* scopes = nullptr;
          UINT count = 0;
          if (SUCCEEDED(scope->GetInputScopes(&scopes, &count))) {
            for (UINT i = 0; i < count; ++i) {
              const InputScope s = scopes[i];
              if (s == IS_PASSWORD || s == IS_NUMERIC_PASSWORD || s == IS_NUMERIC_PIN ||
                  s == IS_ALPHANUMERIC_PIN || s == IS_ALPHANUMERIC_PIN_SET) {
                ok = false;
              }
            }
            CoTaskMemFree(scopes);
          }
          scope->Release();
        }
      }
      VariantClear(&v);
      sel.range->Release();
    }
    prop->Release();
  }
  return ok;
}

STDMETHODIMP TextService::OnEndEdit(ITfContext* ctx, TfEditCookie ec, ITfEditRecord*) {
  const auto m = model();
  if (!m || !Allowed(ctx, ec)) {
    Clear();
    return S_OK;
  }
  std::wstring text;
  ITfRange* caret = nullptr;
  if (!ReadBeforeCaret(ctx, ec, &text, &caret)) {
    Clear();
    return S_OK;
  }
  const Context c = ParseBeforeCaret(text);
  std::u32string completion;
  std::vector<std::u32string> corrections;
  if (c.valid) {
    centaur::WordTracker t(m.get());
    if (c.prev != U"<s>") {
      for (char32_t ch : c.prev) t.OnChar(ch);
      t.OnChar(U' ');
    }
    for (char32_t ch : c.word) t.OnChar(ch);
    completion = t.Completion();
    insert_ = t.TabInsert();
    replace_ = t.TabReplacement();
    corrections = t.Corrections();
    word_ = c.word;
  } else {
    word_.clear();
    insert_.clear();
    replace_.clear();
  }
  RECT rc = {};
  BOOL clipped = FALSE;
  ITfContextView* view = nullptr;
  bool placed = false;
  if (SUCCEEDED(ctx->GetActiveView(&view)) && view) {
    placed = SUCCEEDED(view->GetTextExt(ec, caret, &rc, &clipped)) && (rc.right || rc.bottom);
    view->Release();
  }
  caret->Release();
  if (!placed || (completion.empty() && corrections.empty())) {
    // 場所が分からないときは出さない（あてずっぽうの場所に出さない）。Tab の補完は場所が無くても使える
    popup_.Hide();
    return S_OK;
  }
  std::vector<std::wstring> corr;
  for (const auto& w : corrections) corr.push_back(ToW(w));
  popup_.Show(rc, ToW(completion), corr);
  return S_OK;
}

bool TextService::TabWanted(WPARAM key) const {
  if (key != VK_TAB || (insert_.empty() && replace_.empty())) return false;
  return GetKeyState(VK_SHIFT) >= 0 && GetKeyState(VK_CONTROL) >= 0 && GetKeyState(VK_MENU) >= 0;
}

void TextService::InsertCompletion(ITfContext* ctx) {
  const std::u32string want = word_;
  const std::wstring add = ToW(insert_);
  const std::wstring whole = ToW(replace_);
  auto* es = new EditSession([ctx, want, add, whole](TfEditCookie ec) -> HRESULT {
    std::wstring text;
    if (!ReadBeforeCaret(ctx, ec, &text, nullptr)) return S_OK;
    // 候補を作ったときと同じ語のままか確かめる（違えば何も入れない）
    if (ParseBeforeCaret(text).word != want) return S_OK;
    if (!whole.empty()) {
      // 打った語ごと入れ替える（gith → GitHub）: カーソルの前の打った語の分だけ範囲を広げて書き替える
      TF_SELECTION sel = {};
      ULONG fetched = 0;
      if (FAILED(ctx->GetSelection(ec, TF_DEFAULT_SELECTION, 1, &sel, &fetched)) || fetched != 1 || !sel.range) {
        return S_OK;
      }
      LONG moved = 0;
      const std::wstring typed = ToW(want);
      sel.range->Collapse(ec, TF_ANCHOR_END);
      if (SUCCEEDED(sel.range->ShiftStart(ec, -static_cast<LONG>(typed.size()), &moved, nullptr)) &&
          moved == -static_cast<LONG>(typed.size()) &&
          SUCCEEDED(sel.range->SetText(ec, 0, whole.c_str(), static_cast<LONG>(whole.size())))) {
        sel.range->Collapse(ec, TF_ANCHOR_END);
        sel.style.ase = TF_AE_NONE;
        sel.style.fInterimChar = FALSE;
        ctx->SetSelection(ec, 1, &sel);
      }
      sel.range->Release();
      return S_OK;
    }
    ITfInsertAtSelection* ins = nullptr;
    if (FAILED(ctx->QueryInterface(IID_ITfInsertAtSelection, reinterpret_cast<void**>(&ins)))) return S_OK;
    ITfRange* range = nullptr;
    if (SUCCEEDED(ins->InsertTextAtSelection(ec, TF_IAS_NOQUERY, add.c_str(), static_cast<LONG>(add.size()), &range)) &&
        range) {
      range->Collapse(ec, TF_ANCHOR_END);
      TF_SELECTION sel = {};
      sel.range = range;
      sel.style.ase = TF_AE_NONE;
      sel.style.fInterimChar = FALSE;
      ctx->SetSelection(ec, 1, &sel);
      range->Release();
    }
    ins->Release();
    return S_OK;
  });
  HRESULT hr = S_OK;
  ctx->RequestEditSession(client_id_, es, TF_ES_SYNC | TF_ES_READWRITE, &hr);
  es->Release();
  Clear();
}

STDMETHODIMP TextService::OnSetFocus(BOOL foreground) {
  if (!foreground) Clear();
  return S_OK;
}

STDMETHODIMP TextService::OnTestKeyDown(ITfContext*, WPARAM key, LPARAM, BOOL* eaten) {
  *eaten = TabWanted(key) || (key == VK_ESCAPE && popup_.visible());
  return S_OK;
}

STDMETHODIMP TextService::OnKeyDown(ITfContext* ctx, WPARAM key, LPARAM, BOOL* eaten) {
  *eaten = FALSE;
  if (TabWanted(key)) {
    *eaten = TRUE;
    InsertCompletion(ctx);
  } else if (key == VK_ESCAPE && popup_.visible()) {
    *eaten = TRUE;
    Clear();
  }
  return S_OK;
}

STDMETHODIMP TextService::OnTestKeyUp(ITfContext*, WPARAM, LPARAM, BOOL* eaten) {
  *eaten = FALSE;
  return S_OK;
}
STDMETHODIMP TextService::OnKeyUp(ITfContext*, WPARAM, LPARAM, BOOL* eaten) {
  *eaten = FALSE;
  return S_OK;
}
STDMETHODIMP TextService::OnPreservedKey(ITfContext*, REFGUID, BOOL* eaten) {
  *eaten = FALSE;
  return S_OK;
}

STDMETHODIMP TextService::OnInitDocumentMgr(ITfDocumentMgr*) { return S_OK; }
STDMETHODIMP TextService::OnUninitDocumentMgr(ITfDocumentMgr*) { return S_OK; }
STDMETHODIMP TextService::OnSetFocus(ITfDocumentMgr* focus, ITfDocumentMgr*) {
  Clear();
  WatchDocument(focus);
  return S_OK;
}
STDMETHODIMP TextService::OnPushContext(ITfContext*) {
  ITfDocumentMgr* focus = nullptr;
  if (thread_mgr_ && SUCCEEDED(thread_mgr_->GetFocus(&focus)) && focus) {
    WatchDocument(focus);
    focus->Release();
  }
  return S_OK;
}
STDMETHODIMP TextService::OnPopContext(ITfContext* ctx) { return OnPushContext(ctx); }

}  // namespace centaur_tip
