"""右クリックのメニュー（ひらがな・全角カタカナ…）の文字を大きくする（ウィンドウズ版）。

  python tools/apply_big_menu.py <mozc/src>

右クリックのメニューは IME が自分で出す POPUP メニュー（TipLangBarButton::OnClick の TrackPopupMenu）で、
ウィンドウズの決まりの大きさの文字で描かれる。画面の拡大率が 100% だと小さくて読みにくい
（利用者の声 10/27「これが小さすぎる」「ちいさい」）。

項目を自前で描く（MFT_OWNERDRAW）ようにし、メニューの文字の kBigMenuScale/10 倍の大きさで描く:
  - 描く知らせ（WM_MEASUREITEM・WM_DRAWITEM）はメニューの持ち主の窓に届く。メニューを出している間だけ
    持ち主の窓の受け口を差し替えて自分で受け、閉じたら元に戻す（同じスレッドの窓なので安全）
  - 地の色はウィンドウズの「アプリ モード」（暗い・明るい）に合わせ、メニュー全体と区切り線も同じ色で描く
    （ウィンドウズ 11 のメニューに似せる: 選んでいる項目は角の丸い帯、選ばれている種類は小さな点）
  - 項目の左に印を出す（Microsoft IME と同じく、入力の種類は あ・カ・Ａ・ｶ・A、道具は Segoe MDL2 Assets の
    歯車などのアイコンの字）。利用者の声 11/02「デザインもなんとかして」
apply_version_display.py（一番上に版の名前を出す）のあとに流す。
"""
import sys
from pathlib import Path

src = Path(sys.argv[1])
M = "win32/tip/tip_lang_bar_menu.cc"


def edit(path, old, new, count=1):
    # 改行の記号（LF か CRLF）は、ファイルによって違う。LF で探し、見つからなければ CRLF で探す
    p = src / path
    text = p.read_bytes().decode("utf-8")
    for newline in ("\n", "\r\n"):
        o, n = old.replace("\n", newline), new.replace("\n", newline)
        if text.count(o) == count:
            p.write_bytes(text.replace(o, n).encode("utf-8"))
            return
    raise SystemExit(f"{path}: expected {count} match(es) for {old[:70]!r}, found {text.count(old)}")


edit(M, "#include <algorithm>\n", "#include <algorithm>\n#include <vector>\n")
edit(M, "// メニューの一番上に出す", r"""// 右クリックのメニューを、決まりの文字の kScale 倍で自前で描く（apply_big_menu.py）。
constexpr int kBigMenuScale = 13;  // 10 分の 1 の単位（1.3 倍。1.8 倍は大きすぎた）

struct BigMenu {
  std::vector<std::wstring> texts;
  std::vector<bool> checked;
  std::vector<UINT> ids;
  HFONT font = nullptr;
  HFONT icon_font = nullptr;  // 道具の項目の印（Segoe MDL2 Assets）
  WNDPROC original = nullptr;
  bool dark = false;          // ウィンドウズの「アプリのモード」が暗い
  COLORREF background = 0;
};
thread_local BigMenu* g_big_menu = nullptr;  // メニューを出している間だけ
constexpr ULONG_PTR kSeparatorData = 0xFFFF;  // 自前で描く区切り線

COLORREF Shift(COLORREF color, int amount) {
  const auto channel = [&](int value) { return static_cast<BYTE>(std::clamp(value + amount, 0, 255)); };
  return RGB(channel(GetRValue(color)), channel(GetGValue(color)), channel(GetBValue(color)));
}

// ウィンドウズの設定（個人用設定 > 色 > アプリ モード）が暗いか。メニューの色をこれに合わせる。
bool AppsUseDarkTheme() {
  DWORD light = 1;
  DWORD size = sizeof(light);
  return ::RegGetValueW(HKEY_CURRENT_USER, L"Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize",
                        L"AppsUseLightTheme", RRF_RT_REG_DWORD, nullptr, &light, &size) == ERROR_SUCCESS &&
         light == 0;
}

// 項目の左に出す印。入力の種類は文字（Microsoft IME と同じ あ・カ・Ａ・ｶ・A）、道具はアイコンの字。
// 2つ目は、アイコンの字（icon_font で描く）か。
std::pair<const wchar_t*, bool> MenuGlyph(UINT id) {
  switch (id) {
    case TipLangBarCallback::kHiragana: return {L"あ", false};
    case TipLangBarCallback::kFullKatakana: return {L"カ", false};
    case TipLangBarCallback::kFullAlphanumeric: return {L"Ａ", false};
    case TipLangBarCallback::kHalfKatakana: return {L"ｶ", false};
    case TipLangBarCallback::kHalfAlphanumeric: return {L"A", false};
    case TipLangBarCallback::kDirect: return {L"", true};         // キーボード
    case TipLangBarCallback::kDictionary: return {L"", true};     // 辞書
    case TipLangBarCallback::kWordRegister: return {L"", true};   // 足す
    case TipLangBarCallback::kProperty: return {L"", true};       // 設定（歯車）
    case TipLangBarCallback::kAbout: return {L"", true};          // 情報
    case TipLangBarCallback::kHelp: return {L"", true};           // ヘルプ
    default: return {L"", false};
  }
}

LRESULT CALLBACK BigMenuProc(HWND window, UINT message, WPARAM wparam, LPARAM lparam) {
  BigMenu* big = g_big_menu;
  if (big != nullptr && message == WM_MEASUREITEM) {
    auto* item = reinterpret_cast<MEASUREITEMSTRUCT*>(lparam);
    const bool separator = item->itemData == kSeparatorData;
    if (item->CtlType == ODT_MENU && (separator || (item->itemData > 0 && item->itemData <= big->texts.size()))) {
      const std::wstring text = separator ? L"A" : big->texts[item->itemData - 1];
      HDC dc = ::GetDC(window);
      HGDIOBJ old = ::SelectObject(dc, big->font);
      SIZE size = {};
      ::GetTextExtentPoint32W(dc, text.c_str(), static_cast<int>(text.size()), &size);
      ::SelectObject(dc, old);
      ::ReleaseDC(window, dc);
      if (separator) {
        item->itemHeight = (std::max)(5, static_cast<int>(size.cy) / 2);
        item->itemWidth = 0;
        return TRUE;
      }
      // ウィンドウズ 11 のメニューと同じく、行の高さは文字のおよそ 2 倍。左に点と印の場所、右に余白
      item->itemHeight = size.cy * 9 / 5;
      item->itemWidth = size.cx + item->itemHeight * 3;
      return TRUE;
    }
  }
  if (big != nullptr && message == WM_DRAWITEM) {
    auto* item = reinterpret_cast<DRAWITEMSTRUCT*>(lparam);
    if (item->CtlType == ODT_MENU && item->itemData == kSeparatorData) {
      RECT rect = item->rcItem;
      HBRUSH fill = ::CreateSolidBrush(big->background);
      ::FillRect(item->hDC, &rect, fill);
      ::DeleteObject(fill);
      const int inset = (rect.bottom - rect.top) * 2;
      RECT line = {rect.left + inset, (rect.top + rect.bottom) / 2, rect.right - inset, (rect.top + rect.bottom) / 2 + 1};
      HBRUSH pen = ::CreateSolidBrush(Shift(big->background, big->dark ? 40 : -32));
      ::FillRect(item->hDC, &line, pen);
      ::DeleteObject(pen);
      return TRUE;
    }
    if (item->CtlType == ODT_MENU && item->itemData > 0 && item->itemData <= big->texts.size()) {
      const size_t index = item->itemData - 1;
      const bool selected = (item->itemState & ODS_SELECTED) != 0;
      const bool grayed = (item->itemState & (ODS_GRAYED | ODS_DISABLED)) != 0;
      RECT rect = item->rcItem;
      const int height = rect.bottom - rect.top;
      const COLORREF background = big->background;
      const bool dark = big->dark;
      HBRUSH fill = ::CreateSolidBrush(background);
      ::FillRect(item->hDC, &rect, fill);
      ::DeleteObject(fill);
      if (selected && !grayed) {  // 選んでいる項目は、角の丸い少し違う色の帯
        const int inset = height / 8;
        HBRUSH band = ::CreateSolidBrush(Shift(background, dark ? 20 : -14));
        HGDIOBJ old_brush = ::SelectObject(item->hDC, band);
        HGDIOBJ old_pen = ::SelectObject(item->hDC, ::GetStockObject(NULL_PEN));
        ::RoundRect(item->hDC, rect.left + inset, rect.top + inset / 2, rect.right - inset + 1,
                    rect.bottom - inset / 2 + 1, height / 4, height / 4);
        ::SelectObject(item->hDC, old_pen);
        ::SelectObject(item->hDC, old_brush);
        ::DeleteObject(band);
      }
      const COLORREF text_color = grayed ? (dark ? RGB(0x9d, 0x9d, 0x9d) : RGB(0x6d, 0x6d, 0x6d))
                                         : (dark ? RGB(0xff, 0xff, 0xff) : RGB(0x1a, 0x1a, 0x1a));
      if (big->checked[index]) {  // 選ばれている入力の種類には、小さな点
        const int dot = (std::max)(4, height / 7);
        const int cx = rect.left + height * 3 / 10, cy = (rect.top + rect.bottom) / 2;
        HBRUSH brush = ::CreateSolidBrush(text_color);
        HGDIOBJ old_brush = ::SelectObject(item->hDC, brush);
        HGDIOBJ old_pen = ::SelectObject(item->hDC, ::GetStockObject(NULL_PEN));
        ::Ellipse(item->hDC, cx - dot / 2, cy - dot / 2, cx + dot / 2 + 1, cy + dot / 2 + 1);
        ::SelectObject(item->hDC, old_pen);
        ::SelectObject(item->hDC, old_brush);
        ::DeleteObject(brush);
      }
      ::SetBkMode(item->hDC, TRANSPARENT);
      ::SetTextColor(item->hDC, text_color);
      // 左の印（あ・カ・歯車など）。選ばれている種類の印は、文字の色、ほかは少し薄く
      const auto [glyph, icon] = MenuGlyph(big->ids[index]);
      if (*glyph != L'\0' && (!icon || big->icon_font != nullptr)) {
        RECT box = {rect.left + height * 6 / 10, rect.top, rect.left + height * 16 / 10, rect.bottom};
        ::SetTextColor(item->hDC, big->checked[index] || grayed ? text_color : Shift(text_color, dark ? -60 : 70));
        HGDIOBJ old_font = ::SelectObject(item->hDC, icon ? big->icon_font : big->font);
        ::DrawTextW(item->hDC, glyph, -1, &box, DT_CENTER | DT_VCENTER | DT_SINGLELINE | DT_NOPREFIX);
        ::SelectObject(item->hDC, old_font);
        ::SetTextColor(item->hDC, text_color);
      }
      HGDIOBJ old = ::SelectObject(item->hDC, big->font);
      rect.left += height * 17 / 10;
      const std::wstring& text = big->texts[index];
      ::DrawTextW(item->hDC, text.c_str(), static_cast<int>(text.size()), &rect,
                  DT_LEFT | DT_VCENTER | DT_SINGLELINE | DT_NOPREFIX);
      ::SelectObject(item->hDC, old);
      return TRUE;
    }
  }
  return ::CallWindowProcW(big != nullptr ? big->original : ::DefWindowProcW, window, message, wparam,
                           lparam);
}

// |menu| の文字の項目を自前で描く印に替え、|owner| の窓の受け口を差し替えてメニューを出す。
// 差し替えられないとき（持ち主の窓がない）は、そのまま出す。
UINT TrackBigPopupMenu(HMENU menu, UINT flags, int x, int y, HWND owner) {
  BigMenu big;
  NONCLIENTMETRICSW metrics = {};
  metrics.cbSize = sizeof(metrics);
  if (owner != nullptr && g_big_menu == nullptr &&
      ::SystemParametersInfoW(SPI_GETNONCLIENTMETRICS, sizeof(metrics), &metrics, 0)) {
    metrics.lfMenuFont.lfHeight = metrics.lfMenuFont.lfHeight * kBigMenuScale / 10;
    metrics.lfMenuFont.lfWidth = 0;
    big.font = ::CreateFontIndirectW(&metrics.lfMenuFont);
    big.icon_font = ::CreateFontW(metrics.lfMenuFont.lfHeight, 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE, DEFAULT_CHARSET,
                                  OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH,
                                  L"Segoe MDL2 Assets");
  }
  // 地の色はウィンドウズ 11 のメニューの色。メニュー全体（縁の余白も）をこの色にする
  big.dark = AppsUseDarkTheme();
  big.background = big.dark ? RGB(0x2c, 0x2c, 0x2c) : RGB(0xf9, 0xf9, 0xf9);
  HBRUSH background = nullptr;
  if (big.font != nullptr) {
    big.original = reinterpret_cast<WNDPROC>(
        ::SetWindowLongPtrW(owner, GWLP_WNDPROC, reinterpret_cast<LONG_PTR>(&BigMenuProc)));
  }
  if (big.original != nullptr) {
    g_big_menu = &big;
    background = ::CreateSolidBrush(big.background);
    MENUINFO menu_info = {};
    menu_info.cbSize = sizeof(menu_info);
    menu_info.fMask = MIM_BACKGROUND;
    menu_info.hbrBack = background;
    ::SetMenuInfo(menu, &menu_info);
    const int count = ::GetMenuItemCount(menu);
    for (int i = 0; i < count; ++i) {
      wchar_t text[256] = {};
      MENUITEMINFOW info = {};
      info.cbSize = sizeof(info);
      info.fMask = MIIM_FTYPE | MIIM_STATE | MIIM_STRING | MIIM_ID;
      info.dwTypeData = text;
      info.cch = ARRAYSIZE(text);
      if (!::GetMenuItemInfoW(menu, i, TRUE, &info)) continue;
      if (info.fType & MFT_SEPARATOR) {  // 区切り線も地の色に合わせて自前で描く
        MENUITEMINFOW line = {};
        line.cbSize = sizeof(line);
        line.fMask = MIIM_FTYPE | MIIM_DATA;
        line.fType = MFT_SEPARATOR | MFT_OWNERDRAW;
        line.dwItemData = kSeparatorData;
        ::SetMenuItemInfoW(menu, i, TRUE, &line);
        continue;
      }
      big.texts.emplace_back(text);
      big.checked.push_back((info.fState & MFS_CHECKED) != 0);
      big.ids.push_back(info.wID);
      MENUITEMINFOW owner_draw = {};
      owner_draw.cbSize = sizeof(owner_draw);
      owner_draw.fMask = MIIM_FTYPE | MIIM_DATA;
      owner_draw.fType = (info.fType & ~MFT_RADIOCHECK) | MFT_OWNERDRAW;
      owner_draw.dwItemData = big.texts.size();
      ::SetMenuItemInfoW(menu, i, TRUE, &owner_draw);
    }
  }
  const UINT result = static_cast<UINT>(::TrackPopupMenu(menu, flags, x, y, 0, owner, nullptr));
  if (g_big_menu == &big) {
    ::SetWindowLongPtrW(owner, GWLP_WNDPROC, reinterpret_cast<LONG_PTR>(big.original));
    g_big_menu = nullptr;
  }
  if (big.font != nullptr) ::DeleteObject(big.font);
  if (big.icon_font != nullptr) ::DeleteObject(big.icon_font);
  if (background != nullptr) ::DeleteObject(background);
  return result;
}

// メニューの一番上に出す""")
edit(M, """  const BOOL result = ::TrackPopupMenu(menu.get(), kMenuFlags, point.x, point.y,
                                       0, ::GetFocus(), nullptr);""",
     """  const UINT result = TrackBigPopupMenu(menu.get(), kMenuFlags, point.x, point.y, ::GetFocus());""")
