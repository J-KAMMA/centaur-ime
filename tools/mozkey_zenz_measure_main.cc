// 一般的な IME との比べ: Mozkey の変換を、Zenz（AI）の書き換えまで込みで測る（測るだけ）。
//
// .github/workflows/mozkey-measure.yml が mozkey/src/session/ に写して組み立てる。
// 1 行に 1 文のローマ字を読み、人が打つのと同じく 1 文字ずつキーを送る。打ち終わったら、
// Mozkey が返す「後で呼んで」（callback）を、言われた時間だけ待ってから送り返す。これで遅らせた
// その場の変換（live conversion）と、Zenz の問い合わせと、その結果の取り込み（APPLY_ZENZ_LIVE_CORRECTION）
// が、手を止めたときと同じ順に進む。callback が出なくなったら Enter で確定し、確定した文を書く。
// 文ごとに RESET_CONTEXT で前の文の続きにしない。設定は Mozkey の既定（ConfigHandler::GetDefaultConfig、
// その場の変換と Zenz は入）で、Zenz の 1 回の問い合わせの待ち時間だけ --timeout_msec にする
// （0 は Mozkey の既定。試験の機械でも Zenz は 50 ミリ秒ほどで答え、既定の 180 ミリ秒に収まる）。
//
// 出力: ローマ字<TAB>確定した文<TAB>Zenz を取り込みに行った回数

#include <chrono>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <memory>
#include <string>
#include <thread>
#include <utility>

#include "absl/flags/flag.h"
#include "base/file_util.h"
#include "base/protobuf/text_format.h"
#include "base/init_mozc.h"
#include "base/system_util.h"
#include "config/config_handler.h"
#include "data_manager/oss/oss_data_manager.h"
#include "engine/engine.h"
#include "protocol/commands.pb.h"
#include "protocol/config.pb.h"
#include "session/session_handler.h"

ABSL_FLAG(std::string, input, "", "1 行 1 文のローマ字");
ABSL_FLAG(std::string, output, "", "結果の TSV");
ABSL_FLAG(std::string, profile, "/tmp/mozkey_measure_profile", "利用者の置き場");
ABSL_FLAG(int32_t, timeout_msec, 0, "Zenz の 1 回の問い合わせの待ち時間（0 は Mozkey の既定）");
ABSL_FLAG(int32_t, max_callbacks, 400, "1 文で送り返す callback の上限");

namespace mozc {
namespace {

class Driver {
 public:
  explicit Driver(std::unique_ptr<EngineInterface> engine)
      : handler_(std::make_unique<SessionHandler>(std::move(engine))) {}

  bool Eval(commands::Input input, commands::Output* output) {
    commands::Command command;
    *command.mutable_input() = std::move(input);
    command.mutable_input()->set_id(id_);
    const bool ok = handler_->EvalCommand(&command);
    *output = command.output();
    // 確定した文字は、どの命令の答えに出ても集める
    if (output->has_result()) committed_ += output->result().value();
    return ok;
  }

  std::string TakeCommitted() { return std::exchange(committed_, ""); }

  void CreateSession() {
    commands::Input input;
    input.set_type(commands::Input::CREATE_SESSION);
    input.mutable_capability()->set_text_deletion(
        commands::Capability::DELETE_PRECEDING_TEXT);
    commands::Output output;
    Eval(std::move(input), &output);
    id_ = output.id();
  }

  void SetConfig(const config::Config& config) {
    commands::Input input;
    input.set_type(commands::Input::SET_CONFIG);
    *input.mutable_config() = config;
    commands::Output output;
    Eval(std::move(input), &output);
  }

  void SendCommand(commands::SessionCommand command, commands::Output* output) {
    commands::Input input;
    input.set_type(commands::Input::SEND_COMMAND);
    *input.mutable_command() = std::move(command);
    Eval(std::move(input), output);
  }

  void SendKey(commands::KeyEvent key, commands::Output* output) {
    commands::Input input;
    input.set_type(commands::Input::SEND_KEY);
    *input.mutable_key() = std::move(key);
    Eval(std::move(input), output);
  }

  // Waits for and sends back callbacks as the client would, until none is left.
  int FollowCallbacks(commands::Output* output, int limit, int* zenz_applies) {
    int count = 0;
    while (count < limit && output->has_callback() &&
           output->callback().has_session_command()) {
      const commands::SessionCommand next = output->callback().session_command();
      const uint32_t delay = output->callback().delay_millisec();
      if (next.type() == commands::SessionCommand::APPLY_ZENZ_LIVE_CORRECTION) {
        ++*zenz_applies;
      }
      std::this_thread::sleep_for(std::chrono::milliseconds(delay));
      SendCommand(next, output);
      ++count;
    }
    return count;
  }

 private:
  std::unique_ptr<SessionHandler> handler_;
  uint64_t id_ = 0;
  std::string committed_;
};

}  // namespace
}  // namespace mozc

int main(int argc, char** argv) {
  mozc::InitMozc(argv[0], &argc, &argv);
  // 利用者の置き場は作っておく（無いと設定・学習が書けない）
  (void)mozc::FileUtil::CreateDirectory(absl::GetFlag(FLAGS_profile));
  mozc::SystemUtil::SetUserProfileDirectory(absl::GetFlag(FLAGS_profile));
  auto engine = mozc::Engine::CreateEngine(
      std::make_unique<const mozc::oss::OssDataManager>());
  if (!engine.ok()) {
    std::cerr << "engine: " << engine.status() << std::endl;
    return 1;
  }
  mozc::Driver driver(*std::move(engine));
  driver.CreateSession();

  mozc::config::Config config;
  // Mozkey の製品の既定（その場の変換・Zenz・句読点での確定などが入）。GetDefaultConfig は Mozc の既定
  config = mozc::config::ConfigHandler::GetProductDefaultConfig();
  if (absl::GetFlag(FLAGS_timeout_msec) > 0) {
    config.set_zenz_live_correction_timeout_msec(absl::GetFlag(FLAGS_timeout_msec));
  }
  driver.SetConfig(config);
  std::cerr << "live_conversion=" << config.use_live_conversion()
            << " zenz=" << config.use_zenz_live_correction()
            << " defer=" << config.defer_live_conversion_display_until_zenz_result()
            << " zenz_delay=" << config.zenz_live_correction_delay_msec()
            << " zenz_timeout=" << config.zenz_live_correction_timeout_msec()
            << std::endl;

  std::ifstream in(absl::GetFlag(FLAGS_input));
  std::ofstream out(absl::GetFlag(FLAGS_output));
  std::string romaji;
  int n = 0;
  while (std::getline(in, romaji)) {
    if (romaji.empty()) continue;
    const bool debug = n < 3;  // 最初の 3 文は中身を書き出して確かめる
    mozc::commands::Output output;
    int zenz_applies = 0;
    const int limit = absl::GetFlag(FLAGS_max_callbacks);
    auto collect = [&](const char* label) {
      if (debug) std::cerr << "== " << label << "\n" << mozc::protobuf::Utf8Format(output) << std::endl;
    };
    // Mozkey は「。」「、」（と ！？）を打つと、見えている変換をそのまま確定する（direct commit）。
    // 人は手を止めて Zenz の結果を見てから句読点を打つ、として、句読点の前で callback を待つ。
    for (const char c : romaji) {
      const bool punctuation = c == '.' || c == ',' || c == '!' || c == '?';
      if (punctuation) {
        driver.FollowCallbacks(&output, limit, &zenz_applies);
        collect("before punctuation");
      }
      mozc::commands::KeyEvent key;
      key.set_key_code(static_cast<unsigned char>(c));
      driver.SendKey(std::move(key), &output);
      if (punctuation && debug) collect("after punctuation");
    }
    // 句読点で終わらない文: 待ってから Enter で確定する
    driver.FollowCallbacks(&output, limit, &zenz_applies);
    collect("after callbacks");
    mozc::commands::KeyEvent enter;
    enter.set_special_key(mozc::commands::KeyEvent::ENTER);
    driver.SendKey(std::move(enter), &output);
    collect("after enter");
    int unused = 0;
    driver.FollowCallbacks(&output, 8, &unused);
    const std::string committed = driver.TakeCommitted();
    out << romaji << "\t" << committed << "\t" << zenz_applies << "\n";
    out.flush();
    mozc::commands::SessionCommand reset;
    reset.set_type(mozc::commands::SessionCommand::RESET_CONTEXT);
    driver.SendCommand(std::move(reset), &output);
    if (++n % 100 == 0) std::cerr << n << " sentences" << std::endl;
  }
  return 0;
}
