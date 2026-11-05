"""しばらく打たなかったあとの最初のキーが、IME に届いているかを記録する（ウィンドウズ版の TIP）。

  python tools/apply_tip_keytrace.py <mozc/src>
apply_compound_branding.py の最後から呼ばれる。

「しばらく入力しないと最初の文字だけローマ字のまま出る」（MS-IME でも起きる）を調べるため。
20 秒以上キーが来なかったあとの 6 打だけ、%USERPROFILE%\\AppData\\LocalLow\\CompoundIME\\keytrace.log に
1 行ずつ足す。打った文字は残さない（英字・数字・その他の別だけ）。記録が 2 MB を超えたら足さない。

列: 時刻、T（試し）か K（本番）、前のキーからのミリ秒、文脈（1 あり）、オン（1 オン、0 オフ、- 読めない）、
    食べた（1 IME が受けた、0 アプリへ通した）、かかったマイクロ秒、キーの別（A 英字、D 数字、O その他）
最初の英字の行が無ければ、キーは IME に届いていない（ウィンドウズ側）。
行があってオン 1・食べた 0 なら、IME が通してしまっている（こちらで直せる）。
"""
import sys
from pathlib import Path

src = Path(sys.argv[1])
H = "win32/tip/tip_keyevent_handler.cc"


def edit(path, old, new, count=1):
    p = src / path
    t = p.read_text(encoding="utf-8")
    assert t.count(old) == count, (path, old[:70], t.count(old))
    p.write_text(t.replace(old, new), encoding="utf-8", newline="")


edit(H, "#include <cstdint>\n", "#include <atomic>\n#include <cstdint>\n#include <cstdio>\n")
edit(H, """constexpr bool kKeyDown = true;
constexpr bool kKeyUp = false;

}  // namespace
""", """constexpr bool kKeyDown = true;
constexpr bool kKeyUp = false;

// しばらく打たなかったあとの最初の数打を記録する（apply_tip_keytrace.py）。
constexpr ULONGLONG kTraceIdleMs = 20000;
constexpr int kTraceKeys = 6;
constexpr LONGLONG kTraceMaxBytes = 2 * 1024 * 1024;
std::atomic<ULONGLONG> g_trace_last_tick{0};
std::atomic<int> g_trace_left{0};

class KeyTrace {
 public:
  // test が true なら OnTestKeyDown（ここで間を測る）、false なら OnKeyDown。
  KeyTrace(bool test, WPARAM wparam) : test_(test), wparam_(wparam) {
    const ULONGLONG now = ::GetTickCount64();
    if (test_) {
      const ULONGLONG last = g_trace_last_tick.exchange(now);
      gap_ = last == 0 ? 0 : now - last;
      if (last != 0 && gap_ >= kTraceIdleMs) g_trace_left = kTraceKeys;
      active_ = g_trace_left.load() > 0;
      if (active_) --g_trace_left;
      traced_last_ = active_;
    } else {
      // 本番は、直前の試しを記録したときだけ記録する。
      active_ = traced_last_;
    }
    if (active_) ::QueryPerformanceCounter(&start_);
  }

  void Finish(TipTextService* text_service, ITfContext* context, BOOL eaten) {
    if (!active_) return;
    LARGE_INTEGER end, freq;
    ::QueryPerformanceCounter(&end);
    ::QueryPerformanceFrequency(&freq);
    const long long us = (end.QuadPart - start_.QuadPart) * 1000000 / freq.QuadPart;
    char open = '-';
    bool ctx = false;
    if (text_service != nullptr && context != nullptr) {
      ctx = text_service->GetPrivateContext(context) != nullptr;
      bool is_open = false;
      uint32_t logical = 0, visible = 0;
      if (GetOpenAndMode(text_service, context, &is_open, &logical, &visible)) {
        open = is_open ? '1' : '0';
      }
    }
    const char kind = (wparam_ >= 'A' && wparam_ <= 'Z')   ? 'A'
                      : (wparam_ >= '0' && wparam_ <= '9') ? 'D'
                                                           : 'O';
    SYSTEMTIME st;
    ::GetLocalTime(&st);
    char line[160];
    const int n = std::snprintf(
        line, sizeof(line),
        "%04hu-%02hu-%02hu %02hu:%02hu:%02hu.%03hu\\t%c\\t%llu\\t%d\\t%c\\t%d\\t%lld\\t%c\\r\\n",
        st.wYear, st.wMonth, st.wDay, st.wHour, st.wMinute, st.wSecond,
        st.wMilliseconds, test_ ? 'T' : 'K',
        static_cast<unsigned long long>(gap_), ctx ? 1 : 0, open,
        eaten ? 1 : 0, us, kind);
    if (n <= 0) return;
    wchar_t profile[MAX_PATH];
    const DWORD len = ::GetEnvironmentVariableW(L"USERPROFILE", profile, MAX_PATH);
    if (len == 0 || len >= MAX_PATH) return;
    std::wstring path(profile);
    path += L"\\\\AppData\\\\LocalLow\\\\CompoundIME\\\\keytrace.log";
    HANDLE file = ::CreateFileW(path.c_str(), FILE_APPEND_DATA,
                                FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr,
                                OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) return;
    LARGE_INTEGER size;
    if (::GetFileSizeEx(file, &size) && size.QuadPart < kTraceMaxBytes) {
      DWORD written = 0;
      ::WriteFile(file, line, static_cast<DWORD>(n), &written, nullptr);
    }
    ::CloseHandle(file);
  }

 private:
  static thread_local bool traced_last_;
  bool test_;
  WPARAM wparam_;
  bool active_ = false;
  ULONGLONG gap_ = 0;
  LARGE_INTEGER start_ = {};
};

thread_local bool KeyTrace::traced_last_ = false;

}  // namespace
""")
edit(H, """  text_service->CancelIdleResuggest();
  return OnTestKey(text_service, context, kKeyDown, wparam, lparam, eaten);
}""", """  text_service->CancelIdleResuggest();
  KeyTrace trace(true, wparam);
  const HRESULT hr =
      OnTestKey(text_service, context, kKeyDown, wparam, lparam, eaten);
  trace.Finish(text_service, context, *eaten);
  return hr;
}""")
edit(H, """  return OnKey(text_service, context, kKeyDown, wparam, lparam, eaten);
}""", """  KeyTrace trace(false, wparam);
  const HRESULT hr =
      OnKey(text_service, context, kKeyDown, wparam, lparam, eaten);
  trace.Finish(text_service, context, *eaten);
  return hr;
}""")
print("keytrace applied")
