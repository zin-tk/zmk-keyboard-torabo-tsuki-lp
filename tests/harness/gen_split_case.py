#!/usr/bin/env python3
"""シナリオから nrf52_bsim(BLE 分割エミュレーション)用のビルド設定を生成する。

生成物:
  nrf52_bsim.keymap   セントラル(右)側。実機と同じキーマップ + 右半身の打鍵
  nrf52_bsim.conf     両側に効く設定
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
