#!/usr/bin/env python3
"""シナリオから nrf52_bsim(BLE 分割エミュレーション)用のビルド設定を生成する。

生成物:
  nrf52_bsim.keymap   セントラル(右)側。実機と同じキーマップ + 右半身の打鍵
  nrf52_bsim.conf     両側に効く設定
  central.conf        セントラル(右)側にだけ効く設定
  peripheral.overlay  ペリフェラル(左)側の上書き(col-offset と 左半身の打鍵)
  sim.env             シミュレーション長などを実行スクリプトへ渡す

実機と同じく、各半身の kscan は自分の基板の座標(0..6列)を出し、
col-offset 付きのトランスフォームが全体のキー位置へ変換する。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generated import write_if_changed
from layout import CENTRAL_SIDE, KEYMAP_FILE, PERIPHERAL_SIDE, Layout, load_layout
from scenario import MockEvent, Scenario, load_scenario, to_mock_events_by_side

# BLE のペアリングが終わるまで待つ必要があるため、Tier A より長めに置く。
SPLIT_START_OFFSET_MS = 5000
SPLIT_SETTLE_MS = 2000
SIM_MARGIN_MS = 5000

CENTRAL_KEYMAP_TEMPLATE = """\
/*
 * 自動生成ファイル - tests/harness/gen_split_case.py が作成。直接編集しない。
 *
 * セントラル(右)側。シナリオ: {name}
 * {description}
 */

#include <dt-bindings/zmk/matrix_transform.h>
#include <dt-bindings/zmk/kscan_mock.h>

/* 実機と同じキーマップをそのまま使う */
#include "{keymap_path}"

/ {{
    chosen {{
        zmk,matrix-transform = &pc_test_transform;
    }};

    /* 実機シールドの {transform_label} と同じ内容 */
    pc_test_transform: pc_test_transform {{
        compatible = "zmk,matrix-transform";
        columns = <{columns}>;
        rows = <{rows}>;
        col-offset = <{central_col_offset}>;
        map = <
{map_property}
        >;
    }};
}};

&kscan {{
    rows = <{rows}>;
    columns = <{half_columns}>;
    events = <
{central_events}
    >;
}};
"""

PERIPHERAL_OVERLAY_TEMPLATE = """\
/*
 * 自動生成ファイル - tests/harness/gen_split_case.py が作成。直接編集しない。
 *
 * ペリフェラル(左)側。セントラル用の設定に重ねて適用される。
 */

#include <dt-bindings/zmk/kscan_mock.h>

&pc_test_transform {{
    col-offset = <{peripheral_col_offset}>;
}};

&kscan {{
    events = <
{peripheral_events}
    >;
}};
"""

CONF_TEMPLATE = """\
# 自動生成ファイル - tests/harness/gen_split_case.py が作成。直接編集しない。
CONFIG_ZMK_SPLIT=y
CONFIG_ZMK_POINTING=y
CONFIG_ZMK_LOG_LEVEL_DBG=y

# 実機と同じ初期化順序にするために必要。
# ZMK は SYS_INIT で settings_register() したハンドラの h_commit で
# 分割セントラルのスキャンを開始する。実機では bt_enable() (BT_SETTINGS=y) が
# SYS_INIT 中に settings_subsys_init() を済ませるため登録が残るが、
# nrf52_bsim はフラッシュが無く BT_SETTINGS が既定で無効になるため、
# main() の settings_subsys_init() が動的ハンドラを消してしまい
# 左右が永久に接続しない。
CONFIG_BT_SETTINGS=y
"""

# セントラル側にだけ効かせる設定。
# runtime macro / combo はソースを無条件にコンパイルする一方で、
# 依存する ZMK のシンボル (zmk_behavior_queue_add,
# zmk_keymap_highest_layer_active, as_zmk_keycode_state_changed 等) は
# ZMK がセントラルでしかビルドしないため、ペリフェラルに入れるとリンクで落ちる。
# 実機も同じ理由で snippets/split-central/split-central.conf に置いている。
CENTRAL_CONF_TEMPLATE = """\
# 自動生成ファイル - tests/harness/gen_split_case.py が作成。直接編集しない。

# config/keymap.keymap が使っているモジュール (Tier A と同じ)。
# コンボは zmk,combos から runtime combo の既定値に移行済みなので、
# これを切ると全コンボのテストが落ちる。
CONFIG_ZMK_RUNTIME_COMBO=y
CONFIG_ZMK_RUNTIME_COMBO_MAX_COMBOS=16
CONFIG_ZMK_RUNTIME_MACRO=y
# 実機 (snippets/split-central/split-central.conf) と同じローカル ID 方式。
# 既定の逐次採番だと ZMK 本体が読み取り専用セクションの
# zmk_behavior_local_id_map に書き込んで落ちる (nrf52_bsim で顕在化)
CONFIG_ZMK_BEHAVIOR_LOCAL_ID_TYPE_CRC16=y
# 実機と同じ値。既定の 64 のままだと ZMK_RUNTIME_MACRO_MAX_BYTES が
# クランプされ、Kconfig の警告でビルドが止まる
CONFIG_ZMK_CUSTOM_SETTINGS_LARGE_VALUE_MAX_SIZE=256
"""


def _render_events(events: list[MockEvent]) -> str:
    return "\n".join(f"        {event.as_dts()}" for event in events)


def simulation_length_ms(scenario: Scenario) -> int:
    span = max(step.at_ms for step in scenario.steps) - min(
        step.at_ms for step in scenario.steps
    )
    return SPLIT_START_OFFSET_MS * 2 + span + SPLIT_SETTLE_MS + SIM_MARGIN_MS


def write_case(scenario: Scenario, layout: Layout, out_dir: Path) -> None:
    by_side = to_mock_events_by_side(
        scenario,
        layout,
        start_offset_ms=SPLIT_START_OFFSET_MS,
        settle_ms=SPLIT_SETTLE_MS,
    )
    description = (scenario.description or "(説明なし)").strip().replace("\n", "\n * ")

    out_dir.mkdir(parents=True, exist_ok=True)
    write_if_changed(
        out_dir / "nrf52_bsim.keymap",
        CENTRAL_KEYMAP_TEMPLATE.format(
            name=scenario.name,
            description=description,
            keymap_path=KEYMAP_FILE,
            transform_label=layout.transform_label,
            columns=layout.columns,
            rows=layout.rows,
            half_columns=layout.columns - layout.col_offset,
            central_col_offset=layout.col_offset_of(CENTRAL_SIDE),
            map_property=layout.map_property(),
            central_events=_render_events(by_side[CENTRAL_SIDE]),
        ),
    )
    write_if_changed(
        out_dir / "peripheral.overlay",
        PERIPHERAL_OVERLAY_TEMPLATE.format(
            peripheral_col_offset=layout.col_offset_of(PERIPHERAL_SIDE),
            peripheral_events=_render_events(by_side[PERIPHERAL_SIDE]),
        ),
    )
    write_if_changed(out_dir / "nrf52_bsim.conf", CONF_TEMPLATE)
    write_if_changed(out_dir / "central.conf", CENTRAL_CONF_TEMPLATE)
    write_if_changed(
        out_dir / "sim.env", f"SIM_LENGTH_US={simulation_length_ms(scenario) * 1000}\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", type=Path, help="シナリオ YAML のパス")
    parser.add_argument("out_dir", type=Path, help="生成先ディレクトリ")
    args = parser.parse_args(argv)

    write_case(load_scenario(args.scenario), load_layout(), args.out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
