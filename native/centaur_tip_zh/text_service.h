// Centaur IME Chinese のテキストサービス（TSF）。
//
// 中国語モード: 打った英字を Rime（簡体字の全拼、luna_pinyin_simp）に渡し、組み立て中の拼音を文字の欄に、
//   候補を小さな窓に出す。空白で一番の候補、数字で番号の候補、Enter で打った英字のまま、Esc で取り消し、
//   - と = でページ送り。記号は全角（，。）になる。
// 英語モード: キーはそのままアプリに渡す。
// 切り替え: Shift だけを押して離す、か Shift+Space。組み立て中なら打った英字のまま確定する。
// 英単語まじり（日本語版の「英単語を切り替えずに残す」）: 打った英字が全部は拼音として読めず、英単語（iphone、github）を
//   含むなら（native/centaur_core/zh_mixed、tools/zh_ime/mixed.py と同じ決まり）、拼音の部分だけを変換し英単語を正式な
//   書き方で残した文（我用iPhone）を候補の窓の 1 行目に出し、空白でそれを確定する。数字はこれまでどおり Rime の候補。
// AI（data/zh-lm.bin があるときだけ。tools/models/rr_zh.py と同じ決まり）: Rime の一番の候補が打った音節を全部
//   覆うとき、字の模型が音節ごとに選んだ答えと比べ、模型の点数が Rime の点数＋重み（data/zh-lm-beta.txt）より
//   大きければ、模型の答えを候補の窓の 1 行目に出し、空白でそれを確定する。計算は裏の糸で行い、打つのを待たせない
//   （空白を押した時にまだなら、少しだけ待つ）。
// パスワード欄、読み取り専用の欄、メールアドレス・URL の欄、素通しにするアプリ（ターミナルなど）では英字のまま。
#ifndef CENTAUR_TIP_ZH_TEXT_SERVICE_H_
#define CENTAUR_TIP_ZH_TEXT_SERVICE_H_

#include <msctf.h>
#include <windows.h>

#include <functional>
#include <memory>
#include <string>

#include "../centaur_tip/popup.h"
#include "rime_engine.h"

namespace centaur_tip {

// 仮想キーを Rime のキーの値にする（英字・数字・記号は打った字、後退などは決まった値）。渡さないキーは 0。
int RimeKeyFor(WPARAM vk, UINT scan, const BYTE state[256]);
// 候補の窓の 1 行（1.你好  2.妳好 …）
std::wstring CandidateLine(const centaur_zh::State& st);

class TextService : public ITfTextInputProcessorEx,
                    public ITfKeyEventSink,
                    public ITfThreadMgrEventSink,
                    public ITfCompositionSink {
 public:
  TextService();

  // IUnknown
  STDMETHODIMP QueryInterface(REFIID riid, void** out) override;
  STDMETHODIMP_(ULONG) AddRef() override;
  STDMETHODIMP_(ULONG) Release() override;

  // ITfTextInputProcessor(Ex)
  STDMETHODIMP Activate(ITfThreadMgr* tm, TfClientId id) override;
  STDMETHODIMP Deactivate() override;
  STDMETHODIMP ActivateEx(ITfThreadMgr* tm, TfClientId id, DWORD flags) override;

  // ITfKeyEventSink
  STDMETHODIMP OnSetFocus(BOOL foreground) override;
  STDMETHODIMP OnTestKeyDown(ITfContext* ctx, WPARAM key, LPARAM lparam, BOOL* eaten) override;
  STDMETHODIMP OnTestKeyUp(ITfContext* ctx, WPARAM key, LPARAM lparam, BOOL* eaten) override;
  STDMETHODIMP OnKeyDown(ITfContext* ctx, WPARAM key, LPARAM lparam, BOOL* eaten) override;
  STDMETHODIMP OnKeyUp(ITfContext* ctx, WPARAM key, LPARAM lparam, BOOL* eaten) override;
  STDMETHODIMP OnPreservedKey(ITfContext* ctx, REFGUID guid, BOOL* eaten) override;

  // ITfThreadMgrEventSink
  STDMETHODIMP OnInitDocumentMgr(ITfDocumentMgr* dim) override;
  STDMETHODIMP OnUninitDocumentMgr(ITfDocumentMgr* dim) override;
  STDMETHODIMP OnSetFocus(ITfDocumentMgr* focus, ITfDocumentMgr* prev) override;
  STDMETHODIMP OnPushContext(ITfContext* ctx) override;
  STDMETHODIMP OnPopContext(ITfContext* ctx) override;

  // ITfCompositionSink
  STDMETHODIMP OnCompositionTerminated(TfEditCookie ec, ITfComposition* composition) override;

 private:
  enum class Action { kPass, kToggle, kRime };
  Action Decide(WPARAM key, LPARAM lparam, int* rime_key) const;

  ~TextService();
  bool Allowed(ITfContext* ctx, TfEditCookie ec);
  void Run(ITfContext* ctx, const std::function<void(TfEditCookie)>& f);
  // Rime の今の様子を文字の欄と候補の窓に写す
  void Sync(ITfContext* ctx, TfEditCookie ec);
  void Insert(ITfContext* ctx, TfEditCookie ec, const std::wstring& text);  // 組み立ての外に文字を入れる
  void SetCompositionText(ITfContext* ctx, TfEditCookie ec, const std::wstring& text);
  void EndComposition(TfEditCookie ec);
  void CommitRaw(ITfContext* ctx, TfEditCookie ec);  // 打った英字のまま確定する

  LONG ref_ = 1;
  ITfThreadMgr* thread_mgr_ = nullptr;
  TfClientId client_id_ = TF_CLIENTID_NULL;
  DWORD thread_mgr_cookie_ = TF_INVALID_COOKIE;
  bool app_allowed_ = true;

  bool chinese_ = true;
  std::wstring mixed_;  // 英単語まじりの文（空白で確定する。無ければ空）
  std::wstring ai_;     // AI が選んだ文（空白で確定する。無ければ空）
  std::wstring ai_key_;  // AI に頼んだときの入力（打った英字。入力が変わったら古い答えは使わない）
  RECT last_rect_ = {};  // 候補の窓の場所と行（AI の答えが来たら出し直す）
  std::vector<std::wstring> last_lines_;
  HWND notify_ = nullptr;  // 裏の糸から AI の答えが来たことを知らせてもらう窓
  void OnAiReady();
  static LRESULT CALLBACK NotifyProc(HWND hwnd, UINT msg, WPARAM wparam, LPARAM lparam);
  bool shift_alone_ = false;  // Shift を押してからほかのキーを押していない
  ITfComposition* composition_ = nullptr;
  Popup popup_;
};

}  // namespace centaur_tip

#endif  // CENTAUR_TIP_ZH_TEXT_SERVICE_H_
