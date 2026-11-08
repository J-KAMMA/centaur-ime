"""打ち始めにアプリが組み立てを打ち切ったとき、かなになる前のローマ字（ｓ、ｓｈ）を確定しない（ウィンドウズ版の TIP）。

  python tools/apply_tip_first_key.py <mozc/src>
apply_compound_branding.py の最後から呼ばれる。

Claude（Electron）などのアプリは、入力欄の最初の 1 字で画面を作り直し、そのときに IME の組み立てを打ち切ることが
ある（ITfCompositionSink::OnCompositionTerminated）。上流の Mozc はそこで SUBMIT して、表示中の「ｓ」をそのまま
確定するので、sita が「ｓいた」になる（2026-11-06 利用者の報告。打ち始めだけ、打ち直すと起きない。MS-IME でも
最初の文字だけローマ字のまま出ることがある）。

組み立ての文字が、かなになる前のローマ字だけ（全角の英小文字 1〜3 字）のときは、その字を文書から消して確定せず、
変換の常駐には打ちかけのまま残す。次のキー（i）で「し」に続き、新しい組み立てとして出る。
それ以外（かなや漢字を含む、4 字以上、大文字、半角）は今までどおり確定する。
次のキーで組み立てが無いときは、TIP が新しく作る（DoEditSessionInComposition の CreateComposition）。
残った打ちかけは、別の欄をクリックして打つとそこに続く（1〜3 字のローマ字だけなので、害は小さいと判断）。
"""
import sys
from pathlib import Path

src = Path(sys.argv[1])
P = "win32/tip/tip_edit_session_impl.cc"


def edit(path, old, new, count=1):
    p = src / path
    t = p.read_text(encoding="utf-8")
    assert t.count(old) == count, (path, old[:70], t.count(old))
    p.write_text(t.replace(old, new), encoding="utf-8", newline="")


edit(P, """using Annotation = ::mozc::commands::Preedit::Segment::Annotation;
""", """using Annotation = ::mozc::commands::Preedit::Segment::Annotation;

// かなになる前のローマ字だけの組み立て（ｓ、ｓｈ、ｔｓ）か。全角の英小文字 1〜3 字（apply_tip_first_key.py）。
bool IsPendingRomajiOnly(const std::wstring& text) {
  if (text.empty() || text.size() > 3) {
    return false;
  }
  for (const wchar_t c : text) {
    if (c < L'\\xFF41' || c > L'\\xFF5A') {  // ａ〜ｚ
      return false;
    }
  }
  return true;
}
""")

edit(P, """  SessionCommand command;
  command.set_type(SessionCommand::SUBMIT);
  Output output;
  TipPrivateContext* private_context = text_service->GetPrivateContext(context);
  if (private_context == nullptr) {
    return E_FAIL;
  }
  if (!private_context->GetClient()->SendCommand(command, &output)) {
    return E_FAIL;
  }
  const HRESULT result = DoEditSessionAfterComposition(text_service, context,
                                                       write_cookie, output);
  UpdateUI(text_service, context, write_cookie);
  return result;
}""", """  // 打ち始めにアプリが打ち切ったのが、かなになる前のローマ字（ｓ）だけなら、確定せずに消して、常駐には
  // 打ちかけのまま残す（sita が「ｓいた」にならないように。apply_tip_first_key.py）。
  if (composition) {
    wil::com_ptr_nothrow<ITfRange> range;
    std::wstring text;
    if (SUCCEEDED(composition->GetRange(&range)) && range &&
        SUCCEEDED(TipRangeUtil::GetText(range.get(), write_cookie, &text)) &&
        IsPendingRomajiOnly(text) &&
        SUCCEEDED(range->SetText(write_cookie, 0, L"", 0))) {
      return S_OK;
    }
  }

  SessionCommand command;
  command.set_type(SessionCommand::SUBMIT);
  Output output;
  TipPrivateContext* private_context = text_service->GetPrivateContext(context);
  if (private_context == nullptr) {
    return E_FAIL;
  }
  if (!private_context->GetClient()->SendCommand(command, &output)) {
    return E_FAIL;
  }
  const HRESULT result = DoEditSessionAfterComposition(text_service, context,
                                                       write_cookie, output);
  UpdateUI(text_service, context, write_cookie);
  return result;
}""")
print("tip first key applied")
