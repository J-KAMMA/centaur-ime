# Centaur IME English（ウィンドウズの TSF の部品）。64 ビットと 32 ビットの両方を組み立てる
# （32 ビットのアプリの中では 32 ビットの DLL が読み込まれるため）。
cmake_minimum_required(VERSION 3.20)
project(centaur_tip_en CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")  # ほかの DLL に頼らない

add_compile_options(/utf-8 /W4 /permissive- /EHsc)
add_compile_definitions(UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX)

set(CORE ${CMAKE_CURRENT_SOURCE_DIR}/../centaur_core)
add_library(centaur_tip_en SHARED
  dllmain.cc text_service.cc popup.cc tip.def
  ${CORE}/core.cc ${CORE}/word_tracker.cc)
target_link_libraries(centaur_tip_en PRIVATE ole32 oleaut32 uuid user32 gdi32 advapi32 shell32)

# 登録できたかを確かめる小さな道具（GitHub の流れで使う）
add_executable(tip_check tip_check.cc)
target_link_libraries(tip_check PRIVATE ole32 oleaut32 uuid)

# 組み立て済みの表を作る道具（文字の表 → table.bin）
add_executable(centaur_core_cli ${CORE}/cli.cc ${CORE}/core.cc)

# 今の語の切り出しの試験
add_executable(parse_test parse_test.cc text_service.cc popup.cc ${CORE}/core.cc ${CORE}/word_tracker.cc)
target_link_libraries(parse_test PRIVATE ole32 oleaut32 uuid user32 gdi32 advapi32 shell32)
