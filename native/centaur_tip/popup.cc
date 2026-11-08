#include "popup.h"

#include <algorithm>

extern HINSTANCE g_instance;

namespace centaur_tip {
namespace {

const wchar_t kClassName[] = L"CentaurIMEEnglishPopup";
const int kPad = 6;

}  // namespace

Popup::~Popup() {
  if (hwnd_) DestroyWindow(hwnd_);
  if (font_) DeleteObject(font_);
}

bool Popup::Create() {
  if (hwnd_) return true;
  WNDCLASSEXW wc = {sizeof(wc)};
  if (!GetClassInfoExW(g_instance, kClassName, &wc)) {
    wc.lpfnWndProc = WndProc;
    wc.hInstance = g_instance;
    wc.hCursor = LoadCursor(nullptr, IDC_ARROW);
    wc.lpszClassName = kClassName;
    if (!RegisterClassExW(&wc)) return false;
  }
  hwnd_ = CreateWindowExW(WS_EX_TOPMOST | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW, kClassName, L"", WS_POPUP | WS_BORDER,
                          0, 0, 10, 10, nullptr, nullptr, g_instance, nullptr);
  if (!hwnd_) return false;
  SetWindowLongPtrW(hwnd_, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(this));
  NONCLIENTMETRICSW m = {sizeof(m)};
  SystemParametersInfoW(SPI_GETNONCLIENTMETRICS, sizeof(m), &m, 0);
  font_ = CreateFontIndirectW(&m.lfMessageFont);
  return true;
}

void Popup::Show(const RECT& caret, const std::wstring& completion, const std::vector<std::wstring>& corrections) {
  lines_.clear();
  if (!completion.empty()) lines_.push_back(completion + L"    Tab");
  if (!corrections.empty()) {
    std::wstring s = L"もしかして: ";
    for (size_t i = 0; i < corrections.size(); ++i) s += (i ? L", " : L"") + corrections[i];
    lines_.push_back(s);
  }
  if (lines_.empty() || !Create()) {
    Hide();
    return;
  }
  HDC dc = GetDC(hwnd_);
  HGDIOBJ old = SelectObject(dc, font_);
  int w = 0, h = 0;
  for (const auto& l : lines_) {
    SIZE sz;
    GetTextExtentPoint32W(dc, l.c_str(), static_cast<int>(l.size()), &sz);
    w = std::max<int>(w, sz.cx);
    h += sz.cy;
  }
  SelectObject(dc, old);
  ReleaseDC(hwnd_, dc);
  SetWindowPos(hwnd_, HWND_TOPMOST, caret.left, caret.bottom + 2, w + 2 * kPad, h + 2 * kPad,
               SWP_NOACTIVATE | SWP_SHOWWINDOW);
  InvalidateRect(hwnd_, nullptr, TRUE);
  visible_ = true;
}

void Popup::Hide() {
  if (hwnd_ && visible_) ShowWindow(hwnd_, SW_HIDE);
  visible_ = false;
}

void Popup::Paint(HDC dc) {
  RECT rc;
  GetClientRect(hwnd_, &rc);
  FillRect(dc, &rc, GetSysColorBrush(COLOR_INFOBK));
  HGDIOBJ old = SelectObject(dc, font_);
  SetBkMode(dc, TRANSPARENT);
  SetTextColor(dc, GetSysColor(COLOR_INFOTEXT));
  int y = kPad;
  for (const auto& l : lines_) {
    SIZE sz;
    GetTextExtentPoint32W(dc, l.c_str(), static_cast<int>(l.size()), &sz);
    TextOutW(dc, kPad, y, l.c_str(), static_cast<int>(l.size()));
    y += sz.cy;
  }
  SelectObject(dc, old);
}

LRESULT CALLBACK Popup::WndProc(HWND hwnd, UINT msg, WPARAM wparam, LPARAM lparam) {
  auto* self = reinterpret_cast<Popup*>(GetWindowLongPtrW(hwnd, GWLP_USERDATA));
  switch (msg) {
    case WM_MOUSEACTIVATE:
      return MA_NOACTIVATE;  // 押されてもフォーカスを取らない
    case WM_PAINT: {
      PAINTSTRUCT ps;
      HDC dc = BeginPaint(hwnd, &ps);
      if (self) self->Paint(dc);
      EndPaint(hwnd, &ps);
      return 0;
    }
    default:
      return DefWindowProcW(hwnd, msg, wparam, lparam);
  }
}

}  // namespace centaur_tip
