// Centaur IME Korean のテキストサービス（TSF）。
//
// 韓国語モード: 2 ボル式（두벌식）でハングルを組み立てる。英字のキーは横取りして、語の区切り（空白、数字、記号、
//   Enter、矢印など）まで 1 つの組み立て中の文字（コンポジション）にし、区切りのキーはそのままアプリに渡す。
//   打ったキーがブランド名（iphone → ㅑㅔㅗㅐㅜㄷ）なら、小さな窓に iPhone を出し、Tab で入れ替える。
// 英語モード: キーはそのままアプリに渡す。カーソルの前の語が、英語モードのまま打った韓国語（dkssud）なら、
//   小さな窓に 안녕 を出し、Tab で入れ替えて韓国語モードに戻す。
// 切り替え: 한/영 キー（VK_HANGUL）か Shift+Space。勝手に文字を直すことはない（直すのは Tab を押したときだけ）。
// パスワード欄、読み取り専用の欄、素通しにするアプリ（ターミナルなど）では組み立てない。
#ifndef CENTAUR_TIP_KO_TEXT_SERVICE_H_
#define CENTAUR_TIP_KO_TEXT_SERVICE_H_

#include <msctf.h>
#include <windows.h>

#include <functional>
#include <memory>
#include <string>

#include "../centaur_core/ko_detect.h"
#include "../centaur_tip/popup.h"

namespace centaur_tip {

// 仮想キーを 2 ボル式のキーの字にする（a〜z、Shift で R E Q T W O P）。英字のキーでなければ 0。
char32_t KoreanKey(WPARAM vk, bool shift);
// カーソルの前の文字の終わりの英字の語（前が英字でないところから）。64 字いっぱいの英字なら空（語の頭が見えない）。
std::u32string WordBeforeCaret(const std::wstring& text);

class TextService : public ITfTextInputProcessorEx,
                    public ITfKeyEventSink,
                    public ITfThreadMgrEventSink,
                    public ITfTextEditSink,
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

  // ITfTextEditSink
  STDMETHODIMP OnEndEdit(ITfContext* ctx, TfEditCookie ec, ITfEditRecord* record) override;

  // ITfCompositionSink
  STDMETHODIMP OnCompositionTerminated(TfEditCookie ec, ITfComposition* composition) override;

 private:
  // キーごとにすること（OnTestKeyDown と OnKeyDown で同じ答えにする）
  enum class Action { kPass, kCommitThenPass, kToggle, kLetter, kBack, kTab, kEscape };
  Action Decide(WPARAM key) const;

  ~TextService();
  void WatchDocument(ITfDocumentMgr* dim);
  void Clear();  // 窓と候補を消す（組み立て中の文字はそのまま）
  bool Allowed(ITfContext* ctx, TfEditCookie ec);
  std::shared_ptr<const centaur::KoDetector> detector() const;

  // 編集（どれも同期の編集セッションの中で呼ぶ）
  void Run(ITfContext* ctx, const std::function<void(TfEditCookie)>& f);
  void AddKey(ITfContext* ctx, TfEditCookie ec, char32_t key);
  void Backspace(TfEditCookie ec);
  void SetCompositionText(TfEditCookie ec, const std::wstring& text);
  void EndComposition(TfEditCookie ec);
  void ShowAtComposition(ITfContext* ctx, TfEditCookie ec, const std::wstring& line);
  void ShowAtCaret(ITfContext* ctx, TfEditCookie ec, const std::wstring& line);
  void ReplaceTypedWord(ITfContext* ctx, TfEditCookie ec);

  LONG ref_ = 1;
  ITfThreadMgr* thread_mgr_ = nullptr;
  TfClientId client_id_ = TF_CLIENTID_NULL;
  DWORD thread_mgr_cookie_ = TF_INVALID_COOKIE;
  ITfContext* watched_ = nullptr;
  DWORD text_edit_cookie_ = TF_INVALID_COOKIE;
  bool app_allowed_ = true;

  bool korean_ = true;                    // 韓国語モードか
  ITfComposition* composition_ = nullptr;  // 組み立て中の文字
  std::u32string keys_;                    // 組み立て中の文字の打ったキー
  std::u32string brand_;                   // Tab で組み立て中の文字と入れ替えるブランド名（無ければ空）
  std::u32string typed_;                   // 英語モード: カーソルの前の打った語
  std::u32string korean_word_;             // 英語モード: Tab で typed_ と入れ替える韓国語（無ければ空）
  Popup popup_;
};

}  // namespace centaur_tip

#endif  // CENTAUR_TIP_KO_TEXT_SERVICE_H_
