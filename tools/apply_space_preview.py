"""打っている途中の候補の先頭に、空白（変換）を押したときと同じ結果を出す。

使い方: python apply_space_preview.py <mozc/src>（apply_jaen_integration.py の最後に呼ばれる）

しくみ:
- 打つのが止まると、Windows の TIP が REQUEST_TYPO_SUGGESTION を送る（元からある「止まったら
  候補を出し直す」道。今までは設定 IdleResuggest が 1 のときだけ。SpacePreview（既定 1）でも送る）。
- 出し直しのとき EngineConverter::Suggest は、空白を押したときと同じ変換を写しの Segments で行い、
  その結果を候補の先頭に置く。文全体の AI は、打っている間に裏で済ませた結果（先回り）だけを使い、
  待たない・新しく頼まない（g_myime_peek_prefetch）。AI が裏でまだ動いていれば、150ms 後にもう一度
  出し直すよう TIP に頼む（最大 12 回）。空白のときと同じにならない場合（文節ごとの AI 呼び出しが要る、
  先回りしていない読み）は何も出さない。
- 打つたびの候補には何もしないので、打つ速さは変わらない。
"""
import sys
from pathlib import Path

src = Path(sys.argv[1])


def edit(path, old, new):
    p = src / path
    text = p.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"{path}: expected one match for {old[:60]!r}, found {text.count(old)}")
    p.write_text(text.replace(old, new), encoding="utf-8", newline="")


# 1. 先回りの結果だけを使う印（同じスレッドの中で EngineConverter からエンジンへ渡す）。
edit("request/options.h", """static_assert(std::is_trivially_copyable<ConversionOptions>::value,
              "ConversionOptions must be trivially copyable");
""", """static_assert(std::is_trivially_copyable<ConversionOptions>::value,
              "ConversionOptions must be trivially copyable");

// CentaurIME: set to 1 by EngineConverter around a conversion that previews
// what Space would give while typing. The engine then uses only a whole-
// sentence AI result that the typing prefetch already finished, and sets it
// to 2 when that result is still being computed or 3 when the preview cannot
// equal Space (the engine would call the AI itself).
inline thread_local int g_myime_peek_prefetch = 0;
""")

# 2. エンジン: 先回りの結果を消費せず写す。無ければ頼まず、待たない。
E = "engine/engine.cc"
edit(E, """      const Query& query, std::chrono::steady_clock::time_point deadline) {
    std::unique_lock<std::mutex> lock(mu_);
""", """      const Query& query, std::chrono::steady_clock::time_point deadline) {
    if (g_myime_peek_prefetch) {
      // Space preview: copy a finished result; never submit, wait or consume.
      // MYIME_SPACE_PREVIEW_WAIT=1 (tests) waits for this query to finish.
      static const bool wait_for_test = [] {
        const char* value = std::getenv("MYIME_SPACE_PREVIEW_WAIT");
        return value && std::string_view(value) == "1";
      }();
      std::unique_lock<std::mutex> lock(mu_);
      const auto busy = [&] {
        return (running_ && running_->Same(query)) || (pending_ && pending_->Same(query));
      };
      if (wait_for_test) cv_.wait(lock, [&] { return !busy(); });
      if (done_ && done_->query.Same(query) &&
          std::chrono::steady_clock::now() - done_->finished <= std::chrono::seconds(30))
        return done_->candidates;
      g_myime_peek_prefetch = busy() ? 2 : 3;
      return std::nullopt;
    }
    std::unique_lock<std::mutex> lock(mu_);
""")
edit(E, """        (no_context && intra_mode != 1) || whole_only ? 0 : segments->conversion_segments_size();
""", """        (no_context && intra_mode != 1) || whole_only ? 0 : segments->conversion_segments_size();
    // Space preview: per-segment AI calls would run here synchronously.
    if (g_myime_peek_prefetch && segment_calls > 0) {
      g_myime_peek_prefetch = 3;
      return true;
    }
""")

# 3. EngineConverter: 出し直しのとき、空白と同じ変換の結果を候補の先頭に置く。
C = "engine/engine_converter.cc"
edit(C, """  // Copy current suggestions so that we can merge
  // prediction/suggestions later
  previous_suggestions_ = segments_.conversion_segment(0);
""", """  // CentaurIME: on an idle resuggest, put what Space would give first.
  space_preview_retry_ = false;
  // The idle resuggest command carries no surrounding text: use the text of
  // the last key, which Space would also see.
  if (!preferences.idle_resuggest) space_preview_context_ = context;
  if (preferences.idle_resuggest) {
    const std::string preview_key(segments_.conversion_segment(0).key());
    if (preview_key != space_preview_key_) {
      space_preview_key_ = preview_key;
      space_preview_tries_ = 0;
    }
    const int state = PutSpacePreviewFirst(composer, space_preview_context_, preferences);
    space_preview_retry_ = state == 2 && ++space_preview_tries_ <= 12;
  }

  // Copy current suggestions so that we can merge
  // prediction/suggestions later
  previous_suggestions_ = segments_.conversion_segment(0);
""")
edit(C, """bool EngineConverter::IsEmptySegment(const Segment& segment) const {""",
     """// Converts the composition as Space would, on a copy of the segments, using
// only an already finished whole-sentence AI result, and puts the result first
// among the suggestions. Returns 1 when done (or Space gives a suggestion
// already first), 2 when the AI result is still being computed, 3 otherwise.
int EngineConverter::PutSpacePreviewFirst(const composer::Composer& composer,
                                          const commands::Context& context,
                                          const ConversionPreferences& preferences) {
  if (segments_.conversion_segments_size() != 1 ||
      segments_.conversion_segment(0).candidates_size() == 0)
    return 3;
  Segments preview = segments_;
  ConversionRequest::Options options;
  options.enable_user_history_for_conversion = preferences.use_history;
  options.request_type = ConversionRequest::CONVERSION;
  const ConversionRequest request =
      ConversionRequestBuilder()
          .SetComposer(composer)
          .SetRequestView(*request_)
          .SetContextView(context)
          .SetConfigView(*config_)
          .SetOptions(std::move(options))
          .Build();
  g_myime_peek_prefetch = 1;
  const bool converted = converter_->StartConversion(request, &preview);
  const int state = g_myime_peek_prefetch;
  g_myime_peek_prefetch = 0;
  if (!converted) return 3;
  if (state != 1) return state;
  std::string key, value;
  for (const Segment& segment : preview.conversion_segments()) {
    if (segment.candidates_size() == 0) return 3;
    key += segment.key();
    value += segment.candidate(0).value;
  }
  Segment* target = segments_.mutable_conversion_segment(0);
  if (key != target->key() || value.empty()) return 3;
  for (size_t i = 0; i < target->candidates_size(); ++i) {
    if (target->candidate(i).value != value) continue;
    if (i > 0) target->move_candidate(static_cast<int>(i), 0);
    return 1;
  }
  const converter::Candidate& first = target->candidate(0);
  const int32_t cost = first.cost;
  converter::Candidate* added = target->insert_candidate(0);
  added->key = key;
  added->content_key = key;
  added->value = value;
  added->content_value = value;
  added->lid = preview.conversion_segment(0).candidate(0).lid;
  added->rid = preview.conversion_segment(preview.conversion_segments_size() - 1).candidate(0).rid;
  added->cost = cost;
  added->attributes = converter::Attribute::NO_VARIANTS_EXPANSION;
  return 1;
}

bool EngineConverter::IsEmptySegment(const Segment& segment) const {""")
edit(C, """  if (const uint64_t token = GetAsyncConversionToken();
      SupportsAsyncConversion(conversion_context_) && token) {""", """  if (output->has_callback() && output->callback().has_session_command() &&
      output->callback().session_command().type() == commands::SessionCommand::REQUEST_TYPO_SUGGESTION)
    output->clear_callback();
  // CentaurIME: the AI result for the Space preview is still being computed.
  if (space_preview_retry_ && CheckState(SUGGESTION)) {
    auto* callback = output->mutable_callback();
    callback->set_delay_millisec(150);
    callback->mutable_session_command()->set_type(commands::SessionCommand::REQUEST_TYPO_SUGGESTION);
  }
  if (const uint64_t token = GetAsyncConversionToken();
      SupportsAsyncConversion(conversion_context_) && token) {""")
H = "engine/engine_converter.h"
edit(H, """  // Sets request type and update the engine_converter's state
  void SetRequestType(ConversionRequest::RequestType request_type,
                      ConversionRequest::Options& options);
""", """  // Sets request type and update the engine_converter's state
  void SetRequestType(ConversionRequest::RequestType request_type,
                      ConversionRequest::Options& options);

  // CentaurIME: what Space would give, first among the suggestions.
  int PutSpacePreviewFirst(const composer::Composer& composer,
                           const commands::Context& context,
                           const ConversionPreferences& preferences);
  bool space_preview_retry_ = false;
  std::string space_preview_key_;
  int space_preview_tries_ = 0;
  commands::Context space_preview_context_;
""")

# 4. 設定: SpacePreview（既定 1）。
edit("converter/engine_config.h", "bool IsIdleResuggestEnabled();\n",
     "bool IsIdleResuggestEnabled();\n// Typing pause: show what Space would give first among the suggestions.\n"
     "bool IsSpacePreviewEnabled();\n")
edit("converter/engine_config.cc", "bool IsIdleResuggestEnabled() {", """bool IsSpacePreviewEnabled() {
#ifdef _WIN32
  return internal::ReadHkcuMozcDwordAsBool(L"SpacePreview", true);
#else
  return true;
#endif
}

bool IsIdleResuggestEnabled() {""")

# 5. TIP: 打つのが止まったら出し直しを頼む。サーバーが頼んだら（AI がまだ）もう一度。
K = "win32/tip/tip_keyevent_handler.cc"
edit(K, """  if (IsAsyncConversionCallback(temporal_output) ||
      (IsIdleResuggestEnabled() &&""", """  if (IsAsyncConversionCallback(temporal_output) ||
      ((IsIdleResuggestEnabled() || IsSpacePreviewEnabled()) &&""")
T = "win32/tip/tip_text_service.cc"
edit(T, "constexpr UINT kIdleResuggestDelayMs = 400;\n",
     "constexpr UINT kIdleResuggestDelayMs = 400;\n"
     "// CentaurIME: the first Space preview after typing pauses.\n"
     "constexpr UINT kSpacePreviewDelayMs = 250;\n")
edit(T, """    const auto& output = private_context->last_output();
    const bool async_conversion = IsAsyncConversionCallback(output);
    if (output.has_callback() ? !async_conversion
                              : (!IsIdleResuggestEnabled() ||
                                 !IsIdleResuggestTargetOutput(output))) return;
    const UINT delay = async_conversion ? output.callback().delay_millisec()
                                        : kIdleResuggestDelayMs;""", """    const auto& output = private_context->last_output();
    const bool async_conversion = IsAsyncConversionCallback(output);
    const bool space_preview = IsSpacePreviewCallback(output);
    if (output.has_callback() ? !(async_conversion || space_preview)
                              : (!(IsIdleResuggestEnabled() || IsSpacePreviewEnabled()) ||
                                 !IsIdleResuggestTargetOutput(output))) return;
    const UINT delay = async_conversion || space_preview ? output.callback().delay_millisec()
                       : IsIdleResuggestEnabled() ? kIdleResuggestDelayMs
                                                  : kSpacePreviewDelayMs;""")
edit(T, """  static bool IsIdleResuggestTargetOutput(const commands::Output& output) {
    return HasNonEmptyPreedit(output) && output.has_candidate_window() &&
           output.candidate_window().has_category() &&
           output.candidate_window().category() == commands::SUGGESTION;
  }
""", """  static bool IsIdleResuggestTargetOutput(const commands::Output& output) {
    return HasNonEmptyPreedit(output) && output.has_candidate_window() &&
           output.candidate_window().has_category() &&
           output.candidate_window().category() == commands::SUGGESTION;
  }

  // CentaurIME: the server asks to resuggest again (Space preview pending).
  static bool IsSpacePreviewCallback(const commands::Output& output) {
    return output.has_callback() && output.callback().has_session_command() &&
           output.callback().session_command().type() ==
               commands::SessionCommand::REQUEST_TYPO_SUGGESTION &&
           output.callback().delay_millisec() > 0 &&
           output.callback().delay_millisec() <= 1000 &&
           IsIdleResuggestTargetOutput(output);
  }
""")
edit(T, """    const bool async_conversion = IsAsyncConversionCallback(last_output);
    if ((last_output.has_callback() ? !async_conversion
                                   : (!IsIdleResuggestEnabled() ||
                                      !IsIdleResuggestTargetOutput(last_output))) ||""",
     """    const bool async_conversion = IsAsyncConversionCallback(last_output);
    const bool space_preview = IsSpacePreviewCallback(last_output);
    if ((last_output.has_callback() ? !(async_conversion || space_preview)
                                   : (!(IsIdleResuggestEnabled() || IsSpacePreviewEnabled()) ||
                                      !IsIdleResuggestTargetOutput(last_output))) ||""")
edit(T, """    if (async_conversion && output.has_callback()) {
      ScheduleIdleResuggest(context.get());
    }""", """    if ((async_conversion || IsSpacePreviewCallback(output)) && output.has_callback()) {
      ScheduleIdleResuggest(context.get());
    }""")
print("space preview applied")
