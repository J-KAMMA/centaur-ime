"""切り替えの一覧（Win+Space）のロゴを、版の番号のない決まったファイルから読ませる（ウィンドウズ版）。

  python tools/apply_tip_icon.py <mozc/src>

tools/apply_tip_versioned.py の後に動かす。

入力の部品を版ごとの名前（mozc_tip32-3.34.6239.175.dll）にしてから、版を入れ替えるたびに一覧の
ロゴが「日本」の字になった（1.173、1.175 で利用者が見た）。エクスプローラーを立ち上げ直すと戻る。
ロゴの登録（TSF の IconFile）が部品そのものを指していて、版ごとに場所が変わるため、エクスプローラーが
覚えている前の場所と食い違う見込み。

直し方: ロゴだけのファイル（tip_icon.ico、部品の中の先頭のロゴと同じ product_icon_langbar.ico）を
部品と同じフォルダーに決まった名前で置き、登録をそこへ向ける。.ico はエクスプローラーが読んだあと
開いたままにしないので、上書きで入れ替えられる。11/14 にこの PC で登録をこのファイルに向け、
ロゴが出ることを確かめた。ファイルが無いときは、これまでどおり部品を指す。
"""
import sys
from pathlib import Path

src = Path(sys.argv[1])


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


# ロゴのファイルをインストーラーの組み立てに渡す
edit("data/images/win/BUILD.bazel", '''    srcs = ["product_icon.ico"],''',
     '''    srcs = [
        "product_icon.ico",
        "product_icon_langbar.ico",
    ],''')
B = "win32/installer/BUILD.bazel"
edit(B, '''        "//data/images/win:product_icon.ico",
''', '''        "//data/images/win:product_icon.ico",
        "//data/images/win:product_icon_langbar.ico",
''')
edit(B, '''        "--icon_path=$(location //data/images/win:product_icon.ico)",
''', '''        "--icon_path=$(location //data/images/win:product_icon.ico)",
        "--tip_icon_path=$(location //data/images/win:product_icon_langbar.ico)",
''')
P = "win32/installer/build_installer.py"
edit(P, "  parser.add_argument('--icon_path', type=str)\n",
     "  parser.add_argument('--icon_path', type=str)\n  parser.add_argument('--tip_icon_path', type=str)\n")
edit(P, "      '-define', f'AddRemoveProgramIconPath={icon_path}',\n",
     "      '-define', f'AddRemoveProgramIconPath={icon_path}',\n"
     "      '-define', f'TipIconPath={pathlib.Path(args.tip_icon_path).resolve()}',\n")

# 部品と同じフォルダーに tip_icon.ico を置く
W = "win32/installer/installer_oss_64bit.wxs"
edit(W, '''      <ComponentRef Id="MozcTIP32" />
''', '''      <ComponentRef Id="MozcTIP32" />
      <ComponentRef Id="MozcTipIcon" />
''')
edit(W, '''        <Component Id="MozcTIP64" ''', '''        <Component Id="MozcTipIcon">
          <File Id="tip_icon.ico" Name="tip_icon.ico" DiskId="1" Source="$(var.TipIconPath)" />
        </Component>
        <Component Id="MozcTIP64" ''')

# 登録: ロゴは部品と同じフォルダーの tip_icon.ico から読ませる（無ければ部品から）
R = "win32/base/tsf_registrar.cc"
edit(R, '''    result = profiles->AddLanguageProfile(
        TsfProfile::GetTextServiceGuid(), TsfProfile::GetLangId(),
        TsfProfile::GetProfileGuid(), description.c_str(), description.size(),
        resource_dll_path.data(), resource_dll_path.length(),
        TsfProfile::GetIconIndex());''', '''    // The DLL has the version in its name (mozc_tip32-<version>.dll), so its
    // path changes with every update, and the input switcher kept showing
    // text instead of the logo until Explorer restarted. The icon is read
    // from a file with a fixed name next to it instead, when it is there.
    std::wstring icon_path(resource_dll_path);
    int icon_index = TsfProfile::GetIconIndex();
    {
      const size_t slash = icon_path.find_last_of(L"\\\\/");
      const std::wstring fixed =
          (slash == std::wstring::npos ? std::wstring()
                                       : icon_path.substr(0, slash + 1)) +
          L"tip_icon.ico";
      const DWORD attributes = ::GetFileAttributesW(fixed.c_str());
      if (attributes != INVALID_FILE_ATTRIBUTES &&
          (attributes & FILE_ATTRIBUTE_DIRECTORY) == 0) {
        icon_path = fixed;
        icon_index = 0;
      }
    }
    result = profiles->AddLanguageProfile(
        TsfProfile::GetTextServiceGuid(), TsfProfile::GetLangId(),
        TsfProfile::GetProfileGuid(), description.c_str(), description.size(),
        icon_path.c_str(), icon_path.size(), icon_index);''')
print("tip icon: ok")
