#include "text_service.h"

#include <inputscope.h>
#include <shlobj.h>

#include <atomic>
#include <filesystem>
#include <mutex>
#include <thread>

#include "../centaur_core/zh_mixed.h"

extern HINSTANCE g_instance;
extern std::atomic<long> g_dll_ref;

namespace centaur_tip {
namespace {

// 入力の種類（パスワード欄など）を持つ性質の識別子（inputscope.idl の GUID_PROP_INPUTSCOPE と同じ値）。
const GUID kGuidPropInputScope = {0x1713dd5a, 0x68e7, 0x4a5b, {0x9a, 0xf6, 0x59, 0x2a, 0x59, 0x5c, 0x77, 0x8d}};

// ---- Rime（1 つの処理の中で 1 つ。別の糸で始め、始まるまではキーをそのまま渡す） ----
std::mutex g_engine_mutex;
std::unique_ptr<centaur_zh::RimeEngine> g_engine;  // 始まったら入る（以後は差し替えない）
std::unique_ptr<centaur_zh::RimeEngine> g_helper;  // 英単語まじりの文の拼音の部分を変換する別のセッション
std::unique_ptr<centaur::ZhMixed> g_mixed;          // 英単語まじりの決まり（表が無ければ入らない）
std::once_flag g_load_once;

std::filesystem::path ModuleDir() {
  wchar_t path[MAX_PATH] = {};
  GetModuleFileNameW(g_instance, path, MAX_PATH);
  return std::filesystem::path(path).parent_path();
}

std::filesystem::path UserDir() {
  wchar_t* local = nullptr;
  std::filesystem::path p;
  if (SUCCEEDED(SHGetKnownFolderPath(FOLDERID_LocalAppData, 0, nullptr, &local))) {
    p = std::filesystem::path(local) / L"CentaurIME" / L"chinese" / L"rime";
  }
  CoTaskMemFree(local);
  return p;
}

void StartLoad() {
  std::call_once(g_load_once, [] {
    ++g_dll_ref;  // 始まるまで DLL を外させない
    std::thread([] {
      // 入れる場所: <DLL の場所>\x64\rime.dll（32 ビットは x86）、<DLL の場所>\data（辞書）
      const auto dir = ModuleDir();
      const auto dll = dir / (sizeof(void*) == 8 ? L"x64" : L"x86") / L"rime.dll";
      auto e = std::make_unique<centaur_zh::RimeEngine>();
      const auto user = UserDir();
      if (!user.empty() && e->Start(dll, dir / L"data", user)) {
        auto helper = std::make_unique<centaur_zh::RimeEngine>();
        auto mixed = std::make_unique<centaur::ZhMixed>();
        const bool mixed_ok = mixed->Load(dir / L"data" / L"zh-mixed.tsv");
        if (mixed_ok) mixed->LoadCasing(dir / L"data" / L"casing.tsv");
        const bool helper_ok = mixed_ok && helper->Start(dll, dir / L"data", user);
        std::lock_guard<std::mutex> lock(g_engine_mutex);
        g_engine = std::move(e);
        if (helper_ok) {
          g_helper = std::move(helper);
          g_mixed = std::move(mixed);
        }
      }
      --g_dll_ref;
    }).detach();
  });
}

centaur_zh::RimeEngine* Engine() {
  std::lock_guard<std::mutex> lock(g_engine_mutex);
  return g_engine.get();
}

// 英単語まじりの文: 拼音の部分を別のセッションで一番の候補に変換し（長い所は空白を繰り返して全部）、英単語は
// 正式な書き方で残す。英単語が無ければ空。
std::wstring MixedText(const std::string& raw) {
  centaur_zh::RimeEngine* h = nullptr;
  const centaur::ZhMixed* m = nullptr;
  {
    std::lock_guard<std::mutex> lock(g_engine_mutex);
    h = g_helper.get();
    m = g_mixed.get();
  }
  if (!h || !m) return {};
  const auto parts = m->Split(raw);
  bool english = false;
  for (const auto& p : parts) english = english || p.second;
  if (!english) return {};
  std::wstring out;
  for (const auto& [w, eng] : parts) {
    if (eng) {
      const std::string shown = m->Shown(w);  // UTF-8（Pokémon のように英字でない字もある）
      const int len = MultiByteToWideChar(CP_UTF8, 0, shown.data(), static_cast<int>(shown.size()), nullptr, 0);
      std::wstring ws(len, L'\0');
      MultiByteToWideChar(CP_UTF8, 0, shown.data(), static_cast<int>(shown.size()), ws.data(), len);
      out += ws;
      continue;
    }
    h->Clear();
    h->Read();
    for (char c : w) h->Key(static_cast<unsigned char>(c));
    for (int i = 0; i < 32; ++i) {
      const centaur_zh::State st = h->Read();
      out += st.commit;
      if (st.preedit.empty()) break;
      h->Key(' ');
    }
    h->Clear();
  }
  return out;
}

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

bool Down(int vk) { return GetKeyState(vk) < 0; }

void Trace(const char* what, WPARAM key) {
  wchar_t path[MAX_PATH];
  if (!GetEnvironmentVariableW(L"CENTAUR_ZH_TRACE", path, MAX_PATH)) return;
  if (FILE* f = _wfopen(path, L"ab")) {
    fprintf(f, "%s %02x\n", what, static_cast<unsigned>(key));
    fclose(f);
  }
}

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

int RimeKeyFor(WPARAM vk, UINT scan, const BYTE state[256]) {
  switch (vk) {
    case VK_BACK: return centaur_zh::kKeyBackSpace;
    case VK_RETURN: return centaur_zh::kKeyReturn;
    case VK_ESCAPE: return centaur_zh::kKeyEscape;
    case VK_LEFT: return centaur_zh::kKeyLeft;
    case VK_RIGHT: return centaur_zh::kKeyRight;
    case VK_UP: return centaur_zh::kKeyUp;
    case VK_DOWN: return centaur_zh::kKeyDown;
    case VK_PRIOR: return centaur_zh::kKeyPageUp;
    case VK_NEXT: return centaur_zh::kKeyPageDown;
    case VK_HOME: return centaur_zh::kKeyHome;
    case VK_END: return centaur_zh::kKeyEnd;
    case VK_DELETE: return centaur_zh::kKeyDelete;
    case VK_SPACE: return ' ';
    default: break;
  }
  // 英字・数字・記号は、今のキーボードの配列で打った字（ASCII だけ）
  BYTE st[256];
  memcpy(st, state, sizeof(st));
  st[VK_CONTROL] = st[VK_LCONTROL] = st[VK_RCONTROL] = 0;  // Ctrl を押していても字を取る
  st[VK_MENU] = st[VK_LMENU] = st[VK_RMENU] = 0;
  wchar_t buf[4] = {};
  const int n = ToUnicode(static_cast<UINT>(vk), scan, st, buf, 4, 0x4 /* キーボードの状態を変えない */);
  if (n == 1 && buf[0] > 0x20 && buf[0] < 0x7f) return buf[0];
  return 0;
}

std::wstring CandidateLine(const centaur_zh::State& st) {
  std::wstring line;
  for (size_t i = 0; i < st.candidates.size(); ++i) {
    if (i) line += L"  ";
    line += std::to_wstring(i + 1) + L"." + st.candidates[i];
  }
  if (!st.candidates.empty()) {
    if (st.page > 0) line = L"◀ " + line;
    if (!st.last_page) line += L" ▶";
  }
  return line;
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
  if (app_allowed_) StartLoad();
  Trace("activate", 0);
  return S_OK;
}

STDMETHODIMP TextService::Deactivate() {
  if (auto* e = Engine()) e->Clear();
  if (composition_) {
    composition_->Release();
    composition_ = nullptr;
  }
  popup_.Hide();
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
                ok = false;
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

void TextService::Insert(ITfContext* ctx, TfEditCookie ec, const std::wstring& text) {
  ITfInsertAtSelection* ins = nullptr;
  if (FAILED(ctx->QueryInterface(IID_ITfInsertAtSelection, reinterpret_cast<void**>(&ins)))) return;
  ITfRange* r = nullptr;
  if (SUCCEEDED(ins->InsertTextAtSelection(ec, TF_IAS_NOQUERY, text.c_str(), static_cast<LONG>(text.size()), &r)) &&
      r) {
    SetCaret(ctx, ec, r);
    r->Release();
  }
  ins->Release();
}

void TextService::SetCompositionText(ITfContext* ctx, TfEditCookie ec, const std::wstring& text) {
  if (!composition_) {
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
  }
  ITfRange* range = nullptr;
  if (FAILED(composition_->GetRange(&range)) || !range) return;
  range->SetText(ec, 0, text.c_str(), static_cast<LONG>(text.size()));
  SetCaret(ctx, ec, range);
  range->Release();
}

void TextService::EndComposition(TfEditCookie ec) {
  mixed_.clear();
  if (composition_) {
    composition_->EndComposition(ec);
    composition_->Release();
    composition_ = nullptr;
  }
  popup_.Hide();
}

void TextService::Sync(ITfContext* ctx, TfEditCookie ec) {
  auto* e = Engine();
  if (!e) return;
  const centaur_zh::State st = e->Read();
  if (!st.commit.empty()) {
    if (composition_) {
      SetCompositionText(ctx, ec, st.commit);
      EndComposition(ec);
    } else {
      Insert(ctx, ec, st.commit);
    }
  }
  if (st.preedit.empty()) {
    if (composition_) {
      SetCompositionText(ctx, ec, L"");
      EndComposition(ec);
    }
    popup_.Hide();
    return;
  }
  SetCompositionText(ctx, ec, st.preedit);
  RECT rc = {};
  ITfRange* range = nullptr;
  bool placed = false;
  if (composition_ && SUCCEEDED(composition_->GetRange(&range)) && range) {
    placed = RangeRect(ctx, ec, range, &rc);
    range->Release();
  }
  // 英単語まじり（打った英字は ASCII だけ）
  const std::wstring raw_w = e->Input();
  mixed_ = MixedText(std::string(raw_w.begin(), raw_w.end()));
  std::vector<std::wstring> lines;
  if (!mixed_.empty()) lines.push_back(L"空格  " + mixed_);
  const std::wstring line = CandidateLine(st);
  if (!line.empty()) lines.push_back(line);
  if (placed && !lines.empty()) {
    popup_.ShowLines(rc, lines);
  } else {
    popup_.Hide();
  }
}

void TextService::CommitRaw(ITfContext* ctx, TfEditCookie ec) {
  auto* e = Engine();
  if (!composition_ || !e) return;
  const std::wstring raw = e->Input();
  e->Clear();
  SetCompositionText(ctx, ec, raw);
  EndComposition(ec);
}

STDMETHODIMP TextService::OnCompositionTerminated(TfEditCookie, ITfComposition* composition) {
  // アプリが組み立てを終わらせた（クリックなど）。文字はアプリに残るので、Rime の側を捨てる
  if (composition_ && composition == composition_) {
    composition_->Release();
    composition_ = nullptr;
  }
  if (auto* e = Engine()) e->Clear();
  popup_.Hide();
  return S_OK;
}

TextService::Action TextService::Decide(WPARAM key, LPARAM lparam, int* rime_key) const {
  const bool ctrl = Down(VK_CONTROL), alt = Down(VK_MENU), shift = Down(VK_SHIFT);
  if (key == VK_SPACE && shift && !ctrl && !alt) return Action::kToggle;
  if (!chinese_ || !app_allowed_ || ctrl || alt || !Engine()) return Action::kPass;
  BYTE state[256];
  if (!GetKeyboardState(state)) return Action::kPass;
  const int k = RimeKeyFor(key, (lparam >> 16) & 0xff, state);
  if (!k) return Action::kPass;
  if (!composition_) {
    // 組み立てていないとき: 英字は組み立てを始め、記号は全角にする（，。）。数字・空白・特別なキーはそのまま
    const bool letter = (k >= 'a' && k <= 'z');
    const bool punct = k > 0x20 && k < 0x7f && !(k >= '0' && k <= '9') && !(k >= 'A' && k <= 'Z') && !letter;
    if (!letter && !punct) return Action::kPass;
  }
  *rime_key = k;
  return Action::kRime;
}

STDMETHODIMP TextService::OnSetFocus(BOOL) { return S_OK; }

STDMETHODIMP TextService::OnTestKeyDown(ITfContext*, WPARAM key, LPARAM lparam, BOOL* eaten) {
  // 「Shift だけ」かを覚える。アプリによって OnTestKeyDown と OnKeyDown の片方だけ・両方が呼ばれるので、両方で同じにする
  Trace("test-down", key);
  shift_alone_ = key == VK_SHIFT;
  int k = 0;
  *eaten = Decide(key, lparam, &k) != Action::kPass;
  return S_OK;
}

STDMETHODIMP TextService::OnKeyDown(ITfContext* ctx, WPARAM key, LPARAM lparam, BOOL* eaten) {
  Trace("down", key);
  shift_alone_ = key == VK_SHIFT;
  if (key == VK_SHIFT) {
    *eaten = FALSE;
    return S_OK;
  }
  int k = 0;
  const Action a = Decide(key, lparam, &k);
  *eaten = a != Action::kPass;
  if (a == Action::kToggle) {
    Run(ctx, [this, ctx](TfEditCookie ec) { CommitRaw(ctx, ec); });
    chinese_ = !chinese_;
  } else if (a == Action::kRime) {
    Run(ctx, [this, ctx, k](TfEditCookie ec) {
      if (!composition_ && !Allowed(ctx, ec)) {
        // パスワード欄など: 打った字のまま入れる（キーは横取りしたので自分で入れる）
        Insert(ctx, ec, std::wstring(1, static_cast<wchar_t>(k)));
        return;
      }
      auto* e = Engine();
      if (k == ' ' && composition_ && !mixed_.empty()) {
        // 英単語まじりの文を確定する
        const std::wstring text = mixed_;
        e->Clear();
        SetCompositionText(ctx, ec, text);
        EndComposition(ec);
        return;
      }
      if (!e->Key(k)) {
        // Rime が使わなかった字（組み立て中でない数字など）はそのまま入れる
        Sync(ctx, ec);
        if (k > 0x20 && k < 0x7f) Insert(ctx, ec, std::wstring(1, static_cast<wchar_t>(k)));
        return;
      }
      Sync(ctx, ec);
    });
  }
  return S_OK;
}

STDMETHODIMP TextService::OnTestKeyUp(ITfContext* ctx, WPARAM key, LPARAM, BOOL* eaten) {
  *eaten = FALSE;  // 離したキーはアプリへ渡す
  Trace(shift_alone_ ? "test-up alone" : "test-up", key);
  // RichEdit などは OnTestKeyUp を呼ばずに OnKeyUp だけを呼ぶ。どちらが先でも切り替えは 1 回（shift_alone_ で見る）
  // Shift だけを押して離したら切り替える。組み立て中の英字は、あとの編集セッションで打ったまま確定する
  if (key == VK_SHIFT && shift_alone_ && ctx) {
    shift_alone_ = false;
    chinese_ = !chinese_;
    ctx->AddRef();  // あとで動く編集セッションの間は放さない
    auto* es = new EditSession([this, ctx](TfEditCookie ec) {
      CommitRaw(ctx, ec);
      ctx->Release();
    });
    HRESULT hr = S_OK;
    ctx->RequestEditSession(client_id_, es, TF_ES_ASYNCDONTCARE | TF_ES_READWRITE, &hr);
    es->Release();
  }
  return S_OK;
}

STDMETHODIMP TextService::OnKeyUp(ITfContext* ctx, WPARAM key, LPARAM, BOOL* eaten) {
  Trace("up", key);
  *eaten = FALSE;
  if (key == VK_SHIFT && shift_alone_ && ctx) {
    shift_alone_ = false;
    chinese_ = !chinese_;
    Run(ctx, [this, ctx](TfEditCookie ec) { CommitRaw(ctx, ec); });
  }
  return S_OK;
}

STDMETHODIMP TextService::OnPreservedKey(ITfContext*, REFGUID, BOOL* eaten) {
  *eaten = FALSE;
  return S_OK;
}

STDMETHODIMP TextService::OnInitDocumentMgr(ITfDocumentMgr*) { return S_OK; }
STDMETHODIMP TextService::OnUninitDocumentMgr(ITfDocumentMgr*) { return S_OK; }
STDMETHODIMP TextService::OnSetFocus(ITfDocumentMgr*, ITfDocumentMgr*) {
  popup_.Hide();
  return S_OK;
}
STDMETHODIMP TextService::OnPushContext(ITfContext*) { return S_OK; }
STDMETHODIMP TextService::OnPopContext(ITfContext*) { return S_OK; }

}  // namespace centaur_tip
