# Centaur IME Chinese（ウィンドウズの TSF の部品）。64 ビットと 32 ビットの両方を組み立てる。
# Rime（librime）の見出しは -DRIME_INCLUDE=<dist/include> で渡す。rime.dll は実行時に読み込む。
cmake_minimum_required(VERSION 3.20)
project(centaur_tip_zh CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")  # ほかの DLL に頼らない

add_compile_options(/utf-8 /W4 /permissive- /EHsc)
add_compile_definitions(UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX)
include_directories(${RIME_INCLUDE})

# Rime を窓なしで試す道具
add_executable(zh_probe zh_probe.cc rime_engine.cc)

set(EN ${CMAKE_CURRENT_SOURCE_DIR}/../centaur_tip)
set(CORE ${CMAKE_CURRENT_SOURCE_DIR}/../centaur_core)
add_library(centaur_tip_zh SHARED dllmain.cc text_service.cc rime_engine.cc ${EN}/popup.cc ${CORE}/zh_mixed.cc ${CORE}/tiny_lm.cc tip.def)
target_link_libraries(centaur_tip_zh PRIVATE ole32 oleaut32 uuid user32 gdi32 advapi32 shell32)

# 登録できたかを確かめる小さな道具（GitHub の流れで使う）
add_executable(tip_check_zh tip_check.cc)
target_link_libraries(tip_check_zh PRIVATE ole32 oleaut32 uuid advapi32)

# 英単語まじりの分け方が Python の決まりと同じ答えになるか（tools/zh_ime/export_mixed.py --check）
add_executable(zh_mixed_cli ${CORE}/zh_mixed_cli.cc ${CORE}/zh_mixed.cc)

# 字の模型の計算が Python と同じ答えになるか（tools/models/export_tiny.py --check）
add_executable(tiny_lm_cli ${CORE}/tiny_lm_cli.cc ${CORE}/tiny_lm.cc)

# 実際にキーを送って打つ試験（登録した DLL を使う）
add_executable(zh_e2e zh_e2e.cc)
target_link_libraries(zh_e2e PRIVATE ole32 oleaut32 uuid user32)
