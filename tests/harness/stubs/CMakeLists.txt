# PC テスト(native_posix_64)専用のスタブ。実機ビルドには一切含まれない。
if(NOT CONFIG_ZMK_BLE)
  zephyr_library_named(torabo_tsuki_pc_test_stubs)
  # ビヘイビア API のヘッダは ZMK 本体の app/include にあり、
  # app ターゲットに PRIVATE で追加されているため外部モジュールからは見えない。
  zephyr_library_include_directories(${APPLICATION_SOURCE_DIR}/include)
  zephyr_library_sources(src/behavior_bt_stub.c)
endif()
