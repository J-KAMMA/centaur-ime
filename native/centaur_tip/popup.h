// 候補の小さな窓。フォーカスを取らず、最前面に出し、タスクバーに出さない。
#ifndef CENTAUR_TIP_POPUP_H_
#define CENTAUR_TIP_POPUP_H_

#include <windows.h>

#include <string>
#include <vector>

namespace centaur_tip {

class Popup {
 public:
  ~Popup();
  // 補完（無ければ空）と直しの候補を、文字の位置 caret（画面の座標）の下に出す。
  void Show(const RECT& caret, const std::wstring& completion, const std::vector<std::wstring>& corrections);
  // 行をそのまま出す（中国語版の候補の一覧など）
  void ShowLines(const RECT& caret, const std::vector<std::wstring>& lines);
  void Hide();
  bool visible() const { return visible_; }

 private:
  bool Create();
  static LRESULT CALLBACK WndProc(HWND hwnd, UINT msg, WPARAM wparam, LPARAM lparam);
  void Paint(HDC dc);

  HWND hwnd_ = nullptr;
  HFONT font_ = nullptr;
  bool visible_ = false;
  std::vector<std::wstring> lines_;
};

}  // namespace centaur_tip

#endif  // CENTAUR_TIP_POPUP_H_
