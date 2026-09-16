# PC テスト(native_sim / nrf52_bsim)専用のスタブ。実機ビルドには一切含まれない。
set(stub_sources)

# &bt ビヘイビア。Tier A には BLE が無いので実体を置き換える。
if(NOT CONFIG_ZMK_BLE)
  list(APPEND stub_sources src/behavior_bt_stub.c)
endif()

# 擬似バッテリー。Tier B で実機と同じく電池まわりの機能を有効にするため。
if(CONFIG_ZMK_BATTERY_REPORTING)
  list(APPEND stub_sources src/fake_battery.c)
endif()

# sys_poweroff() の実装。CONFIG_ZMK_SLEEP を成立させるために要る。
if(CONFIG_POWEROFF)
  list(APPEND stub_sources src/poweroff_stub.c)
endif()

# bsim の機体に、起動をまたいで変わらない BLE アドレスを与える。
if(CONFIG_BOARD_NRF52_BSIM)
  list(APPEND stub_sources src/bsim_static_addr.c)
endif()

if(stub_sources)
  zephyr_library_named(torabo_tsuki_pc_test_stubs)
  # ビヘイビア API のヘッダは ZMK 本体の app/include にあり、
  # app ターゲットに PRIVATE で追加されているため外部モジュールからは見えない。
  zephyr_library_include_directories(${APPLICATION_SOURCE_DIR}/include)
  zephyr_library_sources(${stub_sources})
endif()
