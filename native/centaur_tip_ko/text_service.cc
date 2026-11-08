#include "text_service.h"

#include <inputscope.h>
#include <shlobj.h>

#include <atomic>
#include <filesystem>
#include <mutex>
#include <string_view>
#include <thread>

#include "../centaur_core/hangul.h"

extern std::atomic<long> g_dll_ref;

namespace centaur_tip {
namespace {

// 入力の種類（パスワード欄など）を持つ性質の識別子（inputscope.idl の GUID_PROP_INPUTSCOPE と同じ値）。
const GUID kGuidPropInputScope = {0x1713dd5a, 0x68e7, 0x4a5b, {0x9a, 0xf6, 0x59, 0x2a, 0x59, 0x5c, 0x77, 0x8d}};

// ---- 表（1 つの処理の中で 1 度だけ、別の糸で読む） ----
std::mutex g_detector_mutex;
std::shared_ptr<const centaur::KoDetector> g_detector;
std::once_flag g_load_once;

std::filesystem::path DataDir() {
  wchar_t* local = nullptr;
  std::filesystem::path p;
  if (SUCCEEDED(SHGetKnownFolderPath(FOLDERID_LocalAppData, 0, nullptr, &local))) {
    p = std::filesystem::path(local) / L"CentaurIME" / L"korean";
  }
  CoTaskMemFree(local);
  return p;
}

void StartLoad() {
  std::call_once(g_load_once, [] {
    ++g_dll_ref;  // 読み終わるまで DLL を外させない
    std::thread([] {
      auto d = std::make_shared<centaur::KoDetector>();
      const auto dir = DataDir();
      if (!dir.empty() && d->Load(dir / L"ko-detect.tsv")) {
        d->LoadCasing(dir / L"casing.tsv");  // 無くても動く
        std::lock_guard<std::mutex> lock(g_detector_mutex);
        g_detector = std::move(d);
      }
      --g_dll_ref;
    }).detach();
  });
}

// ---- 素通しにするアプリ（実行ファイルの名前だけで決める。英語版と同じ一覧） ----
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

// ---- 文字の変換（ハングルと英字だけなので、サロゲートは考えなくてよいが、念のため扱う） ----
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

bool Down(int vk) { return GetKeyState(vk) < 0; }

// ---- 関数を渡すだけの編集セッション ----
class EditSession : public ITfEditSession {
 public:
  explicit EditSession(std::function<void(TfEditCookie)> f) : f_(std::move(f)) {}
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
  STDMETHODIMP DoEditSession(TfEditCookie ec) override {
    f_(ec);
    return S_OK;
  }

 private:
  LONG ref_ = 1;
  std::function<void(TfEditCookie)> f_;
};

// 今の選択（カーソル）。呼んだ側が Release する。
ITfRange* Selection(ITfContext* ctx, TfEditCookie ec) {
  TF_SELECTION sel = {};
  ULONG n = 0;
  if (FAILED(ctx->GetSelection(ec, TF_DEFAULT_SELECTION, 1, &sel, &n)) || n != 1) return nullptr;
  return sel.range;
}

void SetCaret(ITfContext* ctx, TfEditCookie ec, ITfRange* range) {
  range->Collapse(ec, TF_ANCHOR_END);
  TF_SELECTION sel = {};
  sel.range = range;
  sel.style.ase = TF_AE_NONE;
  sel.style.fInterimChar = FALSE;
  ctx->SetSelection(ec, 1, &sel);
}

// カーソルの前の最大 64 字
bool ReadBeforeCaret(ITfContext* ctx, TfEditCookie ec, std::wstring* text) {
  ITfRange* sel = Selection(ctx, ec);
  if (!sel) return false;
  BOOL empty = FALSE;
  sel->IsEmpty(ec, &empty);
  bool ok = false;
  ITfRange* r = nullptr;
  if (empty && SUCCEEDED(sel->Clone(&r))) {
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
  sel->Release();
  return ok;
}

bool RangeRect(ITfContext* ctx, TfEditCookie ec, ITfRange* range, RECT* rc) {
  ITfContextView* view = nullptr;
  bool placed = false;
  if (SUCCEEDED(ctx->GetActiveView(&view)) && view) {
    BOOL clipped = FALSE;
    placed = SUCCEEDED(view->GetTextExt(ec, range, rc, &clipped)) && (rc->right || rc->bottom);
    view->Release();
  }
  return placed;
}

}  // namespace

char32_t KoreanKey(WPARAM vk, bool shift) {
  if (vk < 'A' || vk > 'Z') return 0;
  char32_t c = static_cast<char32_t>(U'a' + (vk - 'A'));
  // Shift で別の字になるのは ㄲ ㄸ ㅃ ㅆ ㅉ ㅒ ㅖ（r e q t w o p）だけ。ほかは Shift でも同じ字
  if (shift && std::u32string_view(U"reqtwop").find(c) != std::u32string_view::npos) c = c - U'a' + U'A';
  return c;
}

std::u32string WordBeforeCaret(const std::wstring& wtext) {
  const std::u32string t = ToU32(wtext);
  size_t i = t.size();
  const auto letter = [](char32_t c) { return (c >= U'a' && c <= U'z') || (c >= U'A' && c <= U'Z'); };
  while (i > 0 && letter(t[i - 1])) --i;
  if (i == 0 && t.size() >= 64) return {};
  return t.substr(i);
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
  } else if (riid == IID_ITfCompositionSink) {
    *out = static_cast<ITfCompositionSink*>(this);
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
  if (composition_) {
    // 組み立て中の文字はそのまま確定させる（アプリに残る）
    if (watched_) Run(watched_, [this](TfEditCookie ec) { EndComposition(ec); });
    if (composition_) {
      composition_->Release();
      composition_ = nullptr;
    }
  }
  keys_.clear();
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
  brand_.clear();
  typed_.clear();
  korean_word_.clear();
  popup_.Hide();
}

std::shared_ptr<const centaur::KoDetector> TextService::detector() const {
  std::lock_guard<std::mutex> lock(g_detector_mutex);
  return g_detector;
}

bool TextService::Allowed(ITfContext* ctx, TfEditCookie ec) {
  if (!app_allowed_) return false;
  TF_STATUS status = {};
  if (SUCCEEDED(ctx->GetStatus(&status)) && (status.dwDynamicFlags & TF_SD_READONLY)) return false;
  bool ok = true;
  ITfReadOnlyProperty* prop = nullptr;
  if (SUCCEEDED(ctx->GetAppProperty(kGuidPropInputScope, &prop)) && prop) {
    if (ITfRange* sel = Selection(ctx, ec)) {
      VARIANT v;
      VariantInit(&v);
      if (SUCCEEDED(prop->GetValue(ec, sel, &v)) && v.vt == VT_UNKNOWN && v.punkVal) {
        ITfInputScope* scope = nullptr;
        if (SUCCEEDED(v.punkVal->QueryInterface(__uuidof(ITfInputScope), reinterpret_cast<void**>(&scope)))) {
          InputScope* scopes = nullptr;
          UINT count = 0;
          if (SUCCEEDED(scope->GetInputScopes(&scopes, &count))) {
            for (UINT i = 0; i < count; ++i) {
              const InputScope s = scopes[i];
              if (s == IS_PASSWORD || s == IS_NUMERIC_PASSWORD || s == IS_NUMERIC_PIN || s == IS_ALPHANUMERIC_PIN ||
                  s == IS_ALPHANUMERIC_PIN_SET || s == IS_EMAIL_SMTPEMAILADDRESS || s == IS_URL) {
                ok = false;  // メールアドレスと URL の欄も英字のまま
              }
            }
            CoTaskMemFree(scopes);
          }
          scope->Release();
        }
      }
      VariantClear(&v);
      sel->Release();
    }
    prop->Release();
  }
  return ok;
}

void TextService::Run(ITfContext* ctx, const std::function<void(TfEditCookie)>& f) {
  auto* es = new EditSession(f);
  HRESULT hr = S_OK;
  ctx->RequestEditSession(client_id_, es, TF_ES_SYNC | TF_ES_READWRITE, &hr);
  es->Release();
}

void TextService::SetCompositionText(TfEditCookie ec, const std::wstring& text) {
  ITfRange* range = nullptr;
  if (!composition_ || FAILED(composition_->GetRange(&range)) || !range) return;
  range->SetText(ec, 0, text.c_str(), static_cast<LONG>(text.size()));
  ITfContext* ctx = nullptr;
  if (SUCCEEDED(range->GetContext(&ctx)) && ctx) {
    SetCaret(ctx, ec, range);
    ctx->Release();
  }
  range->Release();
}

void TextService::EndComposition(TfEditCookie ec) {
  if (composition_) {
    composition_->EndComposition(ec);
    composition_->Release();
    composition_ = nullptr;
  }
  keys_.clear();
  brand_.clear();
  popup_.Hide();
}

void TextService::ShowAtComposition(ITfContext* ctx, TfEditCookie ec, const std::wstring& line) {
  ITfRange* range = nullptr;
  RECT rc = {};
  if (composition_ && SUCCEEDED(composition_->GetRange(&range)) && range) {
    const bool placed = RangeRect(ctx, ec, range, &rc);
    range->Release();
    if (placed) {
      popup_.Show(rc, line, {});
      return;
    }
  }
  popup_.Hide();
}

void TextService::ShowAtCaret(ITfContext* ctx, TfEditCookie ec, const std::wstring& line) {
  RECT rc = {};
  ITfRange* sel = Selection(ctx, ec);
  const bool placed = sel && RangeRect(ctx, ec, sel, &rc);
  if (sel) sel->Release();
  if (placed) {
    popup_.Show(rc, line, {});
  } else {
    popup_.Hide();
  }
}

void TextService::AddKey(ITfContext* ctx, TfEditCookie ec, char32_t key) {
  if (!composition_) {
    if (!Allowed(ctx, ec)) {
      // パスワード欄など: 英字のまま入れる（キーは横取りしたので自分で入れる）
      ITfInsertAtSelection* ins = nullptr;
      if (SUCCEEDED(ctx->QueryInterface(IID_ITfInsertAtSelection, reinterpret_cast<void**>(&ins)))) {
        const wchar_t ch = static_cast<wchar_t>(key);
        ITfRange* r = nullptr;
        if (SUCCEEDED(ins->InsertTextAtSelection(ec, TF_IAS_NOQUERY, &ch, 1, &r)) && r) {
          SetCaret(ctx, ec, r);
          r->Release();
        }
        ins->Release();
      }
      return;
    }
    ITfInsertAtSelection* ins = nullptr;
    ITfContextComposition* cc = nullptr;
    ITfRange* range = nullptr;
    if (SUCCEEDED(ctx->QueryInterface(IID_ITfInsertAtSelection, reinterpret_cast<void**>(&ins))) &&
        SUCCEEDED(ins->InsertTextAtSelection(ec, TF_IAS_QUERYONLY, nullptr, 0, &range)) && range &&
        SUCCEEDED(ctx->QueryInterface(IID_ITfContextComposition, reinterpret_cast<void**>(&cc)))) {
      cc->StartComposition(ec, range, static_cast<ITfCompositionSink*>(this), &composition_);
    }
    if (cc) cc->Release();
    if (range) range->Release();
    if (ins) ins->Release();
    if (!composition_) return;
    keys_.clear();
  }
  keys_.push_back(key);
  SetCompositionText(ec, ToW(centaur::Compose(keys_)));
  const auto d = detector();
  brand_ = d ? d->Brand(keys_) : std::u32string();
  if (brand_.empty()) {
    popup_.Hide();
  } else {
    ShowAtComposition(ctx, ec, ToW(brand_));
  }
}

void TextService::Backspace(TfEditCookie ec) {
  if (!keys_.empty()) keys_.pop_back();
  if (keys_.empty()) {
    SetCompositionText(ec, L"");
    EndComposition(ec);
    return;
  }
  SetCompositionText(ec, ToW(centaur::Compose(keys_)));
  const auto d = detector();
  brand_ = d ? d->Brand(keys_) : std::u32string();
  if (brand_.empty()) popup_.Hide();
}

void TextService::ReplaceTypedWord(ITfContext* ctx, TfEditCookie ec) {
  std::wstring text;
  if (!ReadBeforeCaret(ctx, ec, &text) || WordBeforeCaret(text) != typed_) return;  // 候補を作ったときと違う
  ITfRange* sel = Selection(ctx, ec);
  if (!sel) return;
  const std::wstring typed = ToW(typed_), ko = ToW(korean_word_);
  LONG moved = 0;
  sel->Collapse(ec, TF_ANCHOR_END);
  if (SUCCEEDED(sel->ShiftStart(ec, -static_cast<LONG>(typed.size()), &moved, nullptr)) &&
      moved == -static_cast<LONG>(typed.size()) &&
      SUCCEEDED(sel->SetText(ec, 0, ko.c_str(), static_cast<LONG>(ko.size())))) {
    SetCaret(ctx, ec, sel);
  }
  sel->Release();
}

STDMETHODIMP TextService::OnCompositionTerminated(TfEditCookie, ITfComposition* composition) {
  // アプリが組み立てを終わらせた（クリックなど）。文字はアプリに残る
  if (composition_ && composition == composition_) {
    composition_->Release();
    composition_ = nullptr;
  }
  keys_.clear();
  Clear();
  return S_OK;
}

STDMETHODIMP TextService::OnEndEdit(ITfContext* ctx, TfEditCookie ec, ITfEditRecord*) {
  if (composition_) return S_OK;  // 自分の組み立ての編集（窓は AddKey が出す）
  if (korean_) {
    popup_.Hide();  // 切り替えの表示（가/A）は次の編集で消す
    return S_OK;
  }
  // 英語モード: カーソルの前の語が、英語モードのまま打った韓国語か
  const auto d = detector();
  std::wstring text;
  if (!d || !Allowed(ctx, ec) || !ReadBeforeCaret(ctx, ec, &text)) {
    Clear();
    return S_OK;
  }
  typed_ = WordBeforeCaret(text);
  korean_word_ = typed_.size() >= 2 ? d->Korean(typed_) : std::u32string();
  if (korean_word_.empty()) {
    Clear();
    return S_OK;
  }
  ShowAtCaret(ctx, ec, ToW(korean_word_));
  return S_OK;
}

TextService::Action TextService::Decide(WPARAM key) const {
  const bool ctrl = Down(VK_CONTROL), alt = Down(VK_MENU), shift = Down(VK_SHIFT);
  if (key == VK_HANGUL || (key == VK_SPACE && shift && !ctrl && !alt)) return Action::kToggle;
  if (key == VK_SHIFT || key == VK_CONTROL || key == VK_MENU || key == VK_LSHIFT || key == VK_RSHIFT ||
      key == VK_CAPITAL) {
    return Action::kPass;  // 修飾キーだけでは何もしない
  }
  if (key == VK_TAB && !ctrl && !alt && !shift && (!brand_.empty() || !korean_word_.empty())) return Action::kTab;
  if (key == VK_ESCAPE && popup_.visible()) return Action::kEscape;
  if (!app_allowed_) return Action::kPass;
  if (korean_ && !ctrl && !alt && KoreanKey(key, shift)) return Action::kLetter;
  if (composition_ && key == VK_BACK && !ctrl && !alt) return Action::kBack;
  return composition_ ? Action::kCommitThenPass : Action::kPass;
}

STDMETHODIMP TextService::OnSetFocus(BOOL foreground) {
  if (!foreground) Clear();
  return S_OK;
}

STDMETHODIMP TextService::OnTestKeyDown(ITfContext*, WPARAM key, LPARAM, BOOL* eaten) {
  // 組み立てを確定してから渡すキーも、ここでは食べると答えて OnKeyDown を呼ばせる（そこで確定し、キーはアプリへ）
  *eaten = Decide(key) != Action::kPass;
  return S_OK;
}

STDMETHODIMP TextService::OnKeyDown(ITfContext* ctx, WPARAM key, LPARAM, BOOL* eaten) {
  const Action a = Decide(key);
  *eaten = TRUE;
  switch (a) {
    case Action::kPass:
      *eaten = FALSE;
      break;
    case Action::kCommitThenPass:
      Run(ctx, [this](TfEditCookie ec) { EndComposition(ec); });
      *eaten = FALSE;  // キーはそのままアプリへ（空白、Enter、記号、矢印など）
      break;
    case Action::kToggle:
      Run(ctx, [this, ctx](TfEditCookie ec) {
        EndComposition(ec);
        korean_ = !korean_;
        Clear();
        ShowAtCaret(ctx, ec, korean_ ? L"가  한국어" : L"A  English");
      });
      break;
    case Action::kLetter: {
      const char32_t c = KoreanKey(key, Down(VK_SHIFT));
      Run(ctx, [this, ctx, c](TfEditCookie ec) { AddKey(ctx, ec, c); });
      break;
    }
    case Action::kBack:
      Run(ctx, [this](TfEditCookie ec) { Backspace(ec); });
      break;
    case Action::kTab:
      if (!brand_.empty()) {
        const std::wstring b = ToW(brand_);
        Run(ctx, [this, b](TfEditCookie ec) {
          SetCompositionText(ec, b);
          EndComposition(ec);
        });
      } else {
        Run(ctx, [this, ctx](TfEditCookie ec) { ReplaceTypedWord(ctx, ec); });
        korean_ = true;  // 打ちたかったのは韓国語なので、韓国語モードに戻す
      }
      Clear();
      break;
    case Action::kEscape:
      Clear();
      break;
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
