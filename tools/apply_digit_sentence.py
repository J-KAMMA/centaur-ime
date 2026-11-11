"""数字を打った文で、人工知能の文全体の答えがカタカナや別の漢字に崩れるのを直す。

1mojihairuto（1文字入ると）が「1文字はイルト」、10jinikaeru が「10次に帰る」になっていた（11/11 利用者の報告。
アルファベット1文字はイルト一気に…ナッタリする）。人工知能の答えは 一文字入ると / 1文字入ると / 1モジハイルト の順。
1つ目は打った 1 を 一 に替えていて Mozc の文節に当てはまらず、組み直しは1つ目にしか試さないので 2つ目の正しい文は
使われず、3つ目の読みそのままのカタカナ（数字が混じるので「かなだけの文」の見張りをすり抜ける）が選ばれていた。

1. 打った数字（半角・全角の並び）を漢数字にした人工知能の文は、その漢数字を打った数字に書き戻す
   （十時に帰る → 10時に帰る。文節の長さも直す）。書き戻せない文は無いものとして飛ばす（順位も数えない）。
   算用数字を漢数字にしない決まり（10/22）と同じ考え。飛ばすだけだと、人工知能の一番の答え（十時）を捨てて
   下位の 10次 を使ってしまった（全体試験の holdout で 10時から → 10次から）。
2. 「かなだけの文」の見張りで、数字は記号と同じに扱う（1モジハイルト はカタカナのままの文）。
3. 組み直しで、数字だけの一字の区切り（1|文字|入ると の 1）を「一字の記号の区切り」として断らない。

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
      // Mozc's segments): the AI's kanji numerals are written back as the
      // typed digits (十時 -> 10時); a sentence that cannot be does not count.
      converter::Candidate digit_fixed;
      if (DigitRuns(candidate->value) != DigitRuns(key)) {
        if (!TypedDigits(*candidate, key, &digit_fixed)) continue;
        candidate = &digit_fixed;
      }
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
  // Kanji numerals as ASCII digits (十 -> 10, 二十三 -> 23, 一〇 -> 10); empty when not a plain number.
  static std::string KanjiNumber(std::u32string_view run) {
    static constexpr std::u32string_view kDigits = U"〇一二三四五六七八九";
    bool positional = false;
    for (const char32_t c : run) positional |= c == U'十' || c == U'百' || c == U'千';
    std::string out;
    if (!positional) {
      for (const char32_t c : run) out += static_cast<char>('0' + kDigits.find(c));
      return out;
    }
    uint64_t total = 0, current = 0;
    bool has_current = false;
    for (const char32_t c : run) {
      const size_t d = kDigits.find(c);
      if (d != std::u32string_view::npos) {
        if (has_current) return "";
        current = d; has_current = true;
        continue;
      }
      if (has_current && current == 0) return "";
      total += (has_current ? current : 1) * (c == U'十' ? 10 : c == U'百' ? 100 : 1000);
      current = 0; has_current = false;
    }
    return std::to_string(total + current);
  }
  static bool EncodedLengths(std::optional<uint32_t> encoded, uint32_t* out) {
    if (!encoded) return false;
    *out = *encoded;
    return true;
  }
  // `candidate` with the kanji numerals that stand for the typed digits written
  // as typed, in order (一文字入ると一気に -> 1文字入ると一気に for 1もじ…いっきに).
  static bool TypedDigits(const converter::Candidate& candidate, std::string_view key,
                          converter::Candidate* fixed) {
    std::vector<std::string> expected;
    {
      const std::string runs = DigitRuns(key);
      for (size_t at = 0; at < runs.size();) {
        const size_t space = runs.find(' ', at);
        expected.push_back(runs.substr(at, space - at));
        at = space + 1;
      }
    }
    static constexpr std::string_view kNumerals[] = {"〇", "一", "二", "三", "四", "五", "六",
                                                     "七", "八", "九", "十", "百", "千"};
    const auto numeral = [](std::string_view text, size_t at) -> int {
      for (size_t n = 0; n < std::size(kNumerals); ++n)
        if (text.substr(at, kNumerals[n].size()) == kNumerals[n]) return static_cast<int>(n);
      return -1;
    };
    const auto digit = [](std::string_view text, size_t at) -> size_t {  // bytes of one digit, or 0
      if (text[at] >= '0' && text[at] <= '9') return 1;
      if (at + 2 < text.size() && static_cast<unsigned char>(text[at]) == 0xEF &&
          static_cast<unsigned char>(text[at + 1]) == 0xBC &&
          static_cast<unsigned char>(text[at + 2]) >= 0x90 && static_cast<unsigned char>(text[at + 2]) <= 0x99)
        return 3;
      return 0;
    };
    struct Change { size_t at, old_len, new_len; };
    std::vector<Change> changes;
    const std::string_view old = candidate.value;
    std::string value;
    size_t k = 0;
    for (size_t i = 0; i < old.size();) {
      if (digit(old, i)) {
        std::string typed;
        size_t j = i;
        for (size_t n; j < old.size() && (n = digit(old, j)); j += n)
          typed += n == 1 ? old[j] : static_cast<char>(old[j + 2] - 0x90 + '0');
        if (k >= expected.size() || expected[k] != typed) return false;
        ++k;
        value += old.substr(i, j - i);
        i = j;
      } else if (numeral(old, i) >= 0) {
        std::u32string run;
        size_t j = i;
        for (int n; j < old.size() && (n = numeral(old, j)) >= 0; j += kNumerals[n].size())
          run += U"〇一二三四五六七八九十百千"[n];
        const std::string number = KanjiNumber(run);
        if (k < expected.size() && !number.empty() && number == expected[k]) {
          changes.push_back({i, j - i, number.size()});
          value += number;
          ++k;
        } else {
          value += old.substr(i, j - i);
        }
        i = j;
      } else {
        const unsigned char lead = static_cast<unsigned char>(old[i]);
        const size_t n = lead < 0x80 ? 1 : lead < 0xE0 ? 2 : lead < 0xF0 ? 3 : 4;
        value += old.substr(i, n);
        i += n;
      }
    }
    if (k != expected.size() || changes.empty()) return false;
    const auto delta = [&](size_t begin, size_t end, bool* ok) {
      int64_t d = 0;
      for (const Change& c : changes) {
        if (c.at >= begin && c.at + c.old_len <= end) d += static_cast<int64_t>(c.new_len) - c.old_len;
        else if (c.at < end && c.at + c.old_len > begin) *ok = false;
      }
      return d;
    };
    *fixed = candidate;
    fixed->value = value;
    if (candidate.content_value == candidate.value) fixed->content_value = value;
    fixed->inner_segment_boundary.clear();
    size_t at = 0;
    for (const uint32_t encoded : candidate.inner_segment_boundary) {
      const auto length = converter::DecodeLengths(encoded);
      bool ok = true;
      const int64_t dv = delta(at, at + length.value_len, &ok);
      const int64_t dc = delta(at, at + length.content_value_len, &ok);
      uint32_t out = 0;
      if (!ok || !EncodedLengths(converter::EncodeLengths(length.key_len, length.value_len + dv,
                                                          length.content_key_len, length.content_value_len + dc),
                                 &out))
        return false;
      fixed->inner_segment_boundary.push_back(out);
      at += length.value_len;
    }
    return true;
  }
  static bool ResegmentToWholePhrase(""")
# 組み直しで、数字だけの一字の区切り（1|文字|入ると の 1）は「一字の記号」ではない。
edit("""      if (Util::CharsLen(piece_key) == 1 &&
          std::find(std::begin(kParticles)""", """      if (Util::CharsLen(piece_key) == 1 && Util::GetScriptType(piece_key) != Util::NUMBER &&
          std::find(std::begin(kParticles)""")
p.write_text(s, encoding="utf-8", newline="\n")
print("apply_digit_sentence: ok")
