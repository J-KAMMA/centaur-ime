namespace {
// Full-width digits (１０月) inside a candidate that also has other text become
// half-width (10月), as in newspapers and business writing; a candidate of
// digits only (１０) keeps its form so it stays choosable. A candidate that
// becomes the same as an earlier one is dropped. Full-width Latin letters with
// other text (Ｃ言語, Ｔシャツ) become half-width the same way (C言語).
void HalfWidthDigitsInText(Segments* segments) {
  static constexpr std::string_view kFull[] = {"０", "１", "２", "３", "４", "５", "６", "７", "８", "９"};
  // U+FF21-FF3A, U+FF41-FF5A (EF BC A1-BA, EF BD 81-9A) -> A-Z, a-z
  const auto letter = [](std::string_view c) -> char {
    if (c.size() != 3 || static_cast<unsigned char>(c[0]) != 0xEF) return 0;
    const auto b1 = static_cast<unsigned char>(c[1]), b2 = static_cast<unsigned char>(c[2]);
    if (b1 == 0xBC && b2 >= 0xA1 && b2 <= 0xBA) return static_cast<char>('A' + (b2 - 0xA1));
    if (b1 == 0xBD && b2 >= 0x81 && b2 <= 0x9A) return static_cast<char>('a' + (b2 - 0x81));
    return 0;
  };
  const auto convert = [&letter](std::string* text) {
    bool digit = false, other = false;
    for (size_t i = 0; i < text->size();) {
      const auto b = static_cast<unsigned char>((*text)[i]);
      const size_t len = b < 0x80 ? 1 : b < 0xE0 ? 2 : b < 0xF0 ? 3 : 4;
      const std::string_view c(text->data() + i, len);
      if (std::ranges::find(kFull, c) != std::end(kFull) || letter(c) != 0) {
        digit = true;
      } else {
        other = true;
      }
      i += len;
    }
    if (!digit || !other) return false;
    std::string out;
    for (size_t i = 0; i < text->size();) {
      const auto b = static_cast<unsigned char>((*text)[i]);
      const size_t len = b < 0x80 ? 1 : b < 0xE0 ? 2 : b < 0xF0 ? 3 : 4;
      const std::string_view c(text->data() + i, len);
      const auto it = std::ranges::find(kFull, c);
      if (it != std::end(kFull)) {
        out += static_cast<char>('0' + (it - std::begin(kFull)));
      } else if (const char a = letter(c); a != 0) {
        out += a;
      } else {
        out += c;
      }
      i += len;
    }
    *text = std::move(out);
    return true;
  };
  for (size_t s = 0; s < segments->conversion_segments_size(); ++s) {
    Segment& segment = *segments->mutable_conversion_segment(s);
    std::vector<std::string> seen;
    for (int i = 0; i < static_cast<int>(segment.candidates_size());) {
      converter::Candidate* candidate = segment.mutable_candidate(i);
      if (convert(&candidate->value)) convert(&candidate->content_value);
      if (std::ranges::find(seen, candidate->value) != seen.end()) {
        segment.erase_candidate(i);
        continue;
      }
      seen.push_back(candidate->value);
      ++i;
    }
  }
}
}  // namespace
