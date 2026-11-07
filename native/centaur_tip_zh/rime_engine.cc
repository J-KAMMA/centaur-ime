#include "rime_engine.h"

#include <rime_api.h>

#include <cstdio>
#include <cstring>

namespace centaur_zh {
namespace {

std::string Utf8(const std::wstring& w) {
  if (w.empty()) return {};
  const int n = WideCharToMultiByte(CP_UTF8, 0, w.data(), static_cast<int>(w.size()), nullptr, 0, nullptr, nullptr);
  std::string s(n, '\0');
  WideCharToMultiByte(CP_UTF8, 0, w.data(), static_cast<int>(w.size()), s.data(), n, nullptr, nullptr);
  return s;
}

std::wstring Wide(const char* s) {
  if (!s || !*s) return {};
  const int n = MultiByteToWideChar(CP_UTF8, 0, s, -1, nullptr, 0);
  std::wstring w(n, L'\0');
  MultiByteToWideChar(CP_UTF8, 0, s, -1, w.data(), n);
  w.resize(n - 1);
  return w;
}

const RimeApi* Api(const void* p) { return static_cast<const RimeApi*>(p); }

}  // namespace

RimeEngine::~RimeEngine() {
  if (api_ && session_) Api(api_)->destroy_session(session_);
  // Rime は処理の終わりまで残す（finalize と FreeLibrary は、ほかのセッションの糸と競るので呼ばない）
}

bool RimeEngine::Start(const std::filesystem::path& dll, const std::filesystem::path& shared,
                       const std::filesystem::path& user) {
  dll_ = LoadLibraryExW(dll.c_str(), nullptr, LOAD_WITH_ALTERED_SEARCH_PATH);
  if (!dll_) return false;
  using GetApi = RimeApi* (*)();
  auto get = reinterpret_cast<GetApi>(GetProcAddress(dll_, "rime_get_api"));
  if (!get) return false;
  const RimeApi* api = get();
  if (!api) return false;
  api_ = api;
  std::error_code ec;
  std::filesystem::create_directories(user, ec);
  // 簡体字の全拼だけを使い、候補は 1 ページ 9 つ、ページ送りは - と = だけ（「,」「.」は句読点として確定する）。
  // 利用者の置き場の default.custom.yaml。頭に印のある、自分で書いたものだけを書き直す（利用者が書いたものは触らない）
  const char kPatch[] =
      "# Centaur IME（この印がある間は入れ直しのたびに書き直す。自分で直すときは、この行を消す）\n"
      "patch:\n"
      "  schema_list:\n"
      "    - schema: luna_pinyin_simp\n"
      "  menu/page_size: 9\n"
      "  key_binder/bindings:\n"
      "    - { when: has_menu, accept: minus, send: Page_Up }\n"
      "    - { when: has_menu, accept: equal, send: Page_Down }\n";
  // 配る辞書の置き場に centaur-default.custom.yaml があれば、その中身を使う（万象拼音など、方式ごとの設定）
  std::string patch(kPatch, sizeof(kPatch) - 1);
  if (FILE* f = _wfopen((shared / L"centaur-default.custom.yaml").c_str(), L"rb")) {
    std::string body;
    char buf[4096];
    for (size_t n; (n = fread(buf, 1, sizeof(buf), f)) > 0;) body.append(buf, n);
    fclose(f);
    patch = "# Centaur IME（この印がある間は入れ直しのたびに書き直す。自分で直すときは、この行を消す）\n" + body;
  }
  const auto custom = user / L"default.custom.yaml";
  bool ours = !std::filesystem::exists(custom, ec);
  if (!ours) {
    if (FILE* f = _wfopen(custom.c_str(), L"rb")) {
      char head[16] = {};
      ours = fread(head, 1, 14, f) == 14 && memcmp(head, "# Centaur IME", 13) == 0;
      fclose(f);
    }
  }
  if (ours) {
    if (FILE* f = _wfopen(custom.c_str(), L"wb")) {
      fwrite(patch.data(), 1, patch.size(), f);
      fclose(f);
    }
  }
  static std::string shared_s, user_s, build_s;  // Rime は文字列を持ち続けるので、処理の終わりまで残す
  shared_s = Utf8(shared.wstring());
  user_s = Utf8(user.wstring());
  build_s = Utf8((shared / L"build").wstring());
  RIME_STRUCT(RimeTraits, traits);
  traits.shared_data_dir = shared_s.c_str();
  traits.user_data_dir = user_s.c_str();
  traits.prebuilt_data_dir = build_s.c_str();
  traits.distribution_name = "Centaur IME";
  traits.distribution_code_name = "centaur";
  traits.distribution_version = "1";
  traits.app_name = "rime.centaur";
  traits.min_log_level = 2;  // 誤りだけ
  static bool set_up = false;  // setup と initialize は処理の中で 1 度だけ
  if (!set_up) {
    api->setup(&traits);
    api->initialize(&traits);
    if (api->start_maintenance(False)) api->join_maintenance_thread();
    set_up = true;
  }
  session_ = api->create_session();
  return session_ != 0;
}

bool RimeEngine::Key(int keycode, int mask) {
  if (!session_) return false;
  return Api(api_)->process_key(session_, keycode, mask) != 0;
}

State RimeEngine::Read() {
  State st;
  if (!session_) return st;
  const RimeApi* api = Api(api_);
  RIME_STRUCT(RimeCommit, commit);
  if (api->get_commit(session_, &commit)) {
    st.commit = Wide(commit.text);
    api->free_commit(&commit);
  }
  RIME_STRUCT(RimeContext, ctx);
  if (api->get_context(session_, &ctx)) {
    if (ctx.composition.length > 0) st.preedit = Wide(ctx.composition.preedit);
    for (int i = 0; i < ctx.menu.num_candidates; ++i) st.candidates.push_back(Wide(ctx.menu.candidates[i].text));
    st.highlighted = ctx.menu.highlighted_candidate_index;
    st.page = ctx.menu.page_no;
    st.last_page = ctx.menu.is_last_page != 0;
    api->free_context(&ctx);
  }
  return st;
}

std::wstring RimeEngine::Input() {
  if (!session_) return {};
  return Wide(Api(api_)->get_input(session_));
}

void RimeEngine::Clear() {
  if (session_) Api(api_)->clear_composition(session_);
}

bool RimeEngine::Select(int index_on_page) {
  if (!session_) return false;
  return Api(api_)->select_candidate_on_current_page(session_, index_on_page) != 0;
}

}  // namespace centaur_zh
