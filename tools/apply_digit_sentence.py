"""数字を打った文で、人工知能の文全体の答えがカタカナや別の漢字に崩れるのを直す。

1mojihairuto（1文字入ると）が「1文字はイルト」、10jinikaeru が「10次に帰る」になっていた（11/11 利用者の報告。
アルファベット1文字はイルト一気に…ナッタリする）。人工知能の答えは 一文字入ると / 1文字入ると / 1モジハイルト の順。
1つ目は打った 1 を 一 に替えていて Mozc の文節に当てはまらず、組み直しは1つ目にしか試さないので 2つ目の正しい文は
使われず、3つ目の読みそのままのカタカナ（数字が混じるので「かなだけの文」の見張りをすり抜ける）が選ばれていた。

1. 打った数字（半角・全角の並び）を同じに書かない人工知能の文は、無いものとして飛ばす（順位も数えない）。
   算用数字を漢数字にしない決まり（10/22）と同じ考え。これで数字を残した最初の文が組み直しの対象になる。
2. 「かなだけの文」の見張りで、数字は記号と同じに扱う（1モジハイルト はカタカナのままの文）。

    python apply_digit_sentence.py <mozc/src>
"""
import sys
from pathlib import Path

src = Path(sys.argv[1])
p = src / "engine/engine.cc"
s = p.read_text(encoding="utf-8")


def edit(a, b):
    global s
    assert s.count(a) == 1, a[:80]
    s = s.replace(a, b)


edit("""      std::vector<int> indices; const char* rejection = "Compatible";
      // The AI's best whole sentence in kana only is a transliteration, not a""",
     """      std::vector<int> indices; const char* rejection = "Compatible";
      // The digits the user typed must stay as typed (1 -> 一 never fits
      // Mozc's segments): such a sentence does not count, so the first one
      // that keeps them may be resegmented.
      if (DigitRuns(candidate->value) != DigitRuns(key)) continue;
      // The AI's best whole sentence in kana only is a transliteration, not a""")
edit("""          const bool letter_or_digit = (c >= '0' && c <= '9') || ((c | 0x20) >= 'a' && (c | 0x20) <= 'z') ||
                                       (c >= 0xFF10 && c <= 0xFF19) || (c >= 0xFF21 && c <= 0xFF3A) ||
                                       (c >= 0xFF41 && c <= 0xFF5A);""",
     """          // Digits are typed as they are, like symbols (1モジハイルト).
          const bool letter_or_digit = ((c | 0x20) >= 'a' && (c | 0x20) <= 'z') ||
                                       (c >= 0xFF21 && c <= 0xFF3A) || (c >= 0xFF41 && c <= 0xFF5A);""")
edit("  static bool ResegmentToWholePhrase(",
     """  // The runs of digits in `text`, full-width ones as ASCII ("1もじ10" -> "1 10 ").
  static std::string DigitRuns(std::string_view text) {
    std::string runs;
    bool in_run = false;
    for (const char32_t c : Utf8AsChars32(text)) {
      const bool ascii = c >= '0' && c <= '9', wide = c >= 0xFF10 && c <= 0xFF19;
      if (ascii || wide) {
        runs += static_cast<char>(ascii ? c : c - 0xFF10 + '0');
        in_run = true;
      } else if (in_run) {
        runs += ' ';
        in_run = false;
      }
    }
    if (in_run) runs += ' ';
    return runs;
  }
  static bool ResegmentToWholePhrase(""")
p.write_text(s, encoding="utf-8", newline="\n")
print("apply_digit_sentence: ok")
