# Centaur IME Korean（ウィンドウズの TSF の部品）。64 ビットと 32 ビットの両方を組み立てる。
# 候補の窓は英語版（../centaur_tip/popup.cc）と同じものを使う。
cmake_minimum_required(VERSION 3.20)
project(centaur_tip_ko CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")  # ほかの DLL に頼らない

add_compile_options(/utf-8 /W4 /permissive- /EHsc)
add_compile_definitions(UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX)

set(CORE ${CMAKE_CURRENT_SOURCE_DIR}/../centaur_core)
set(EN ${CMAKE_CURRENT_SOURCE_DIR}/../centaur_tip)
add_library(centaur_tip_ko SHARED
  dllmain.cc text_service.cc ${EN}/popup.cc tip.def
  ${CORE}/core.cc ${CORE}/hangul.cc ${CORE}/ko_detect.cc)
target_link_libraries(centaur_tip_ko PRIVATE ole32 oleaut32 uuid user32 gdi32 advapi32 shell32)

# 登録できたかを確かめる小さな道具（GitHub の流れで使う）
add_executable(tip_check_ko tip_check.cc)
target_link_libraries(tip_check_ko PRIVATE ole32 oleaut32 uuid advapi32)

# 見分けが Python の決まりと同じ答えになるか（tools/ko_ime/export_detect.py --check）
add_executable(ko_detect_cli ${CORE}/ko_detect_cli.cc ${CORE}/core.cc ${CORE}/hangul.cc ${CORE}/ko_detect.cc)

# キーの字・カーソルの前の語・見分けの決まりの試験
add_executable(ko_test ko_test.cc text_service.cc ${EN}/popup.cc ${CORE}/core.cc ${CORE}/hangul.cc ${CORE}/ko_detect.cc)
target_link_libraries(ko_test PRIVATE ole32 oleaut32 uuid user32 gdi32 advapi32 shell32)

# 実際にキーを送って打つ試験（登録した DLL を使う）
add_executable(ko_e2e ko_e2e.cc)
target_link_libraries(ko_e2e PRIVATE ole32 oleaut32 uuid user32)
