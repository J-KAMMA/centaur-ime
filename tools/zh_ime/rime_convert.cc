// Rime（librime）に拼音を打ち込み、毎回一番の候補を選んで確定した文字を返す（中国語の計測用）。
//
//   rime_convert <共有データ> <利用者データ> <方式> < 入力 > 出力
// 入力は 1 行に 1 つの拼音（字母だけ、区切りなし）。出力は 1 行に 1 つの確定した文字と、かかった微秒。
#include <rime_api.h>

#include <chrono>
#include <cstdio>
#include <iostream>
#include <string>

int main(int argc, char* argv[]) {
  if (argc != 4) {
    std::cerr << "usage: rime_convert shared_dir user_dir schema\n";
    return 2;
  }
  RIME_STRUCT(RimeTraits, traits);
  traits.shared_data_dir = argv[1];
  traits.user_data_dir = argv[2];
  traits.distribution_name = "CentaurIME measure";
  traits.distribution_code_name = "centaur-measure";
  traits.distribution_version = "0";
  traits.app_name = "rime.centaur-measure";
  RimeApi* api = rime_get_api();
  api->setup(&traits);
  api->initialize(&traits);
  if (api->start_maintenance(True)) api->join_maintenance_thread();
  RimeSessionId s = api->create_session();
  if (!s || !api->select_schema(s, argv[3])) {
    std::cerr << "schema not available: " << argv[3] << "\n";
    return 1;
  }
  std::string line;
  while (std::getline(std::cin, line)) {
    const auto t0 = std::chrono::steady_clock::now();
    api->clear_composition(s);
    for (char c : line) api->process_key(s, static_cast<unsigned char>(c), 0);
    std::string out;
    // 一番の候補を選び続ける（残りの拼音があれば次のまとまりを選ぶ）
    for (int guard = 0; guard < 64; ++guard) {
      RIME_STRUCT(RimeCommit, commit);
      if (api->get_commit(s, &commit)) {
        if (commit.text) out += commit.text;
        api->free_commit(&commit);
      }
      RIME_STRUCT(RimeContext, ctx);
      bool composing = false;
      if (api->get_context(s, &ctx)) {
        composing = ctx.composition.length > 0;
        api->free_context(&ctx);
      }
      if (!composing) break;
      api->process_key(s, ' ', 0);
    }
    const auto us = std::chrono::duration_cast<std::chrono::microseconds>(
                        std::chrono::steady_clock::now() - t0)
                        .count();
    std::cout << out << '\t' << us << '\n' << std::flush;
  }
  api->destroy_session(s);
  api->finalize();
  return 0;
}
