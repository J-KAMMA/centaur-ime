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
