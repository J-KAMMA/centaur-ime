// Centaur IME English のテキストサービス（TSF）。
//
// キーはすぐアプリに渡す（素通し）。文書が変わるたびにカーソルの前の文字を読み、今の語と前の語から
// 補完と直しの候補を作って小さな窓に出す。横取りするのは「補完が出ているときの Tab」と「窓が出ているときの Esc」だけ。
// パスワード欄、読み取り専用の欄、素通しにするアプリ（ターミナルなど）では何もしない。
// 設計: docs/design/02-tsf-frontend.md
#ifndef CENTAUR_TIP_TEXT_SERVICE_H_
#define CENTAUR_TIP_TEXT_SERVICE_H_

#include <msctf.h>
#include <windows.h>

#include <atomic>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

#include "../centaur_core/core.h"
#include "popup.h"

namespace centaur_tip {

// 今の語の情報（文書から読んだもの）
struct Context {
  std::u32string word;  // カーソルの前の語（打ったままの大文字・小文字）
  std::u32string prev;  // その前の語（小文字。文の頭は <s>）
  bool valid = false;   // 読めて、語の途中にいる
};

// カーソルの前の文字（最大 64 字）から今の語と前の語を切り出す（試験しやすいように外に出す）。
Context ParseBeforeCaret(const std::wstring& text);

class TextService : public ITfTextInputProcessorEx,
                    public ITfKeyEventSink,
                    public ITfThreadMgrEventSink,
                    public ITfTextEditSink {
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

  // ITfTextEditSink
  STDMETHODIMP OnEndEdit(ITfContext* ctx, TfEditCookie ec, ITfEditRecord* record) override;

 private:
  ~TextService();
  void WatchDocument(ITfDocumentMgr* dim);  // 文書の変化を見る相手を替える
  void Clear();                            // 候補を消す
  bool Allowed(ITfContext* ctx, TfEditCookie ec);  // パスワード欄などでないか
  bool TabWanted(WPARAM key) const;
  void InsertCompletion(ITfContext* ctx);
  std::shared_ptr<const centaur::Model> model() const;

  LONG ref_ = 1;
  ITfThreadMgr* thread_mgr_ = nullptr;
  TfClientId client_id_ = TF_CLIENTID_NULL;
  DWORD thread_mgr_cookie_ = TF_INVALID_COOKIE;
  ITfContext* watched_ = nullptr;
  DWORD text_edit_cookie_ = TF_INVALID_COOKIE;
  bool app_allowed_ = true;

  // 表は別の糸で読み、読めたら差し替える
  mutable std::mutex model_mutex_;
  std::shared_ptr<const centaur::Model> model_;

  // 今の候補（OnEndEdit で作り、キーの処理で使う）
  std::u32string word_;      // 候補を作ったときの語
  std::u32string insert_;    // Tab で足す文字（無ければ空）
  Popup popup_;
};

}  // namespace centaur_tip

#endif  // CENTAUR_TIP_TEXT_SERVICE_H_
