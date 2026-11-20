"""旧名（CompoundIME／複合IME）の設定と学習を、新しい名前（CentaurIME）の置き場へ写す。

  python tools/apply_centaur_migration.py <mozc/src>
apply_compound_branding.py の最後から呼ばれる。

変換の常駐（mozc_server）が起きた最初に一度だけ、旧名の置き場にあって新しい置き場に無いファイルを写す。
旧名の側は消さない（前の版に戻したときにそのまま使える）。写し終えたら新しい置き場に印のファイルを置き、
二度目からは何もしない。途中で失敗したら印を置かず、次に起きたときにやり直す（あるファイルは上書きしない）。

  ウィンドウズ: %USERPROFILE%\\AppData\\{LocalLow,Local,Roaming}\\CompoundIME → CentaurIME、
                HKCU\\Software\\CompoundIME の値 → HKCU\\Software\\CentaurIME（新しい側に無い値だけ）
  Linux:        $XDG_CONFIG_HOME（~/.config）と $XDG_DATA_HOME（~/.local/share）の compound-ime → centaur-ime
  Mac:          ~/Library/Application Support/CompoundIME → CentaurIME
"""
import sys
from pathlib import Path

src = Path(sys.argv[1])
M = "server/mozc_server_main.cc"


def edit(path, old, new, count=1):
    p = src / path
    t = p.read_text(encoding="utf-8")
    assert t.count(old) == count, (path, old[:70], t.count(old))
    p.write_text(t.replace(old, new), encoding="utf-8", newline="")


edit(M, '#include "converter/engine_config.h"\n', r'''#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <string>
#include <system_error>

#include "converter/engine_config.h"
''')

edit(M, "int main(int argc, char* argv[]) {\n", r'''namespace {

// 旧名（CompoundIME）の置き場から、新しい置き場に無いファイルだけを写す（apply_centaur_migration.py）。
// 途中で作る名前は .migrating で終わり、写し終えてから本来の名前に替える。
bool CopyMissing(const std::filesystem::path& from,
                 const std::filesystem::path& to) {
  namespace fs = std::filesystem;
  std::error_code ec;
  if (!fs::is_directory(from, ec)) return true;
  bool ok = true;
  fs::create_directories(to, ec);
  for (auto it = fs::recursive_directory_iterator(from, ec);
       !ec && it != fs::recursive_directory_iterator(); it.increment(ec)) {
    std::error_code e;
    const fs::path rel = fs::relative(it->path(), from, e);
    if (e) {
      ok = false;
      continue;
    }
    const fs::path dst = to / rel;
    if (it->is_directory(e)) {
      fs::create_directories(dst, e);
      continue;
    }
    const std::string ext = it->path().extension().string();
    if (ext == ".ipc" || ext == ".lock" || ext == ".migrating") continue;
    if (fs::exists(dst, e)) continue;
    fs::path tmp = dst;
    tmp += ".migrating";
    if (fs::copy_file(it->path(), tmp, fs::copy_options::overwrite_existing,
                      e)) {
      fs::rename(tmp, dst, e);
    }
    if (e) {
      fs::remove(tmp, e);
      ok = false;
    }
  }
  return ok && !ec;
}

#ifdef _WIN32
// ウィンドウズでは利用者名に日本語があっても読めるように、環境変数を UTF-16 で読む。
std::filesystem::path EnvPath(const wchar_t* name) {
  const wchar_t* v = ::_wgetenv(name);
  return v != nullptr && *v != L'\0' ? std::filesystem::path(v)
                                     : std::filesystem::path();
}
#else
std::filesystem::path EnvPath(const char* name) {
  const char* v = std::getenv(name);
  return v != nullptr && *v != '\0' ? std::filesystem::path(v)
                                    : std::filesystem::path();
}
#endif

void MigrateFromCompoundIme() {
  namespace fs = std::filesystem;
  std::error_code ec;
  bool ok = true;
#if defined(_WIN32)
  const fs::path home = EnvPath(L"USERPROFILE");
  if (home.empty()) return;
  const fs::path appdata = home / "AppData";
  const fs::path marker =
      appdata / "LocalLow" / "CentaurIME" / ".migrated-from-compoundime";
  if (fs::exists(marker, ec)) return;
  for (const char* sub : {"LocalLow", "Local", "Roaming"}) {
    ok = CopyMissing(appdata / sub / "CompoundIME",
                     appdata / sub / "CentaurIME") && ok;
  }
  HKEY old_key = nullptr;
  if (::RegOpenKeyExW(HKEY_CURRENT_USER, L"Software\\CompoundIME", 0,
                      KEY_READ, &old_key) == ERROR_SUCCESS) {
    HKEY new_key = nullptr;
    if (::RegCreateKeyExW(HKEY_CURRENT_USER, L"Software\\CentaurIME", 0,
                          nullptr, 0, KEY_READ | KEY_WRITE, nullptr, &new_key,
                          nullptr) == ERROR_SUCCESS) {
      for (DWORD i = 0;; ++i) {
        wchar_t name[256];
        DWORD name_len = 256, type = 0, size = 0;
        BYTE data[4096];
        size = sizeof(data);
        const LSTATUS s = ::RegEnumValueW(old_key, i, name, &name_len, nullptr,
                                          &type, data, &size);
        if (s == ERROR_NO_MORE_ITEMS) break;
        if (s != ERROR_SUCCESS) {
          ok = false;
          continue;
        }
        if (::RegQueryValueExW(new_key, name, nullptr, nullptr, nullptr,
                               nullptr) == ERROR_SUCCESS) {
          continue;  // 新しい側で設定済みの値は替えない
        }
        if (::RegSetValueExW(new_key, name, 0, type, data, size) !=
            ERROR_SUCCESS) {
          ok = false;
        }
      }
      ::RegCloseKey(new_key);
    } else {
      ok = false;
    }
    ::RegCloseKey(old_key);
  }
#elif defined(__APPLE__)
  const fs::path home = EnvPath("HOME");
  if (home.empty()) return;
  const fs::path support = home / "Library" / "Application Support";
  const fs::path marker =
      support / "CentaurIME" / ".migrated-from-compoundime";
  if (fs::exists(marker, ec)) return;
  ok = CopyMissing(support / "CompoundIME", support / "CentaurIME");
#elif defined(__linux__)
  const fs::path home = EnvPath("HOME");
  if (home.empty()) return;
  fs::path config = EnvPath("XDG_CONFIG_HOME");
  if (config.empty()) config = home / ".config";
  fs::path data = EnvPath("XDG_DATA_HOME");
  if (data.empty()) data = home / ".local" / "share";
  const fs::path marker = config / "centaur-ime" / ".migrated-from-compoundime";
  if (fs::exists(marker, ec)) return;
  ok = CopyMissing(config / "compound-ime", config / "centaur-ime");
  ok = CopyMissing(data / "compound-ime", data / "centaur-ime") && ok;
#else
  return;
#endif
  if (ok) {
    fs::create_directories(marker.parent_path(), ec);
    std::ofstream(marker) << "1\n";
  }
}

}  // namespace

int main(int argc, char* argv[]) {
  // 旧名の設定と学習を先に写す（模型の有無の確かめや設定の読み込みより前）。
  MigrateFromCompoundIme();
''')
print("centaur migration applied")
