#!/usr/bin/env python3
"""シナリオから native_posix_64 用の ZMK_CONFIG 一式を生成する。

生成物は「実機と同じ config/keymap.keymap を include し、
実機と同じマトリクストランスフォームを持ち、
kscan をモックに差し替えただけ」のビルド設定。
キーマップ本体は複製しないので、実機と挙動がズレない。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generated import write_if_changed
from layout import KEYMAP_FILE, Layout, load_layout
from scenario import MockEvent, Scenario, load_scenario, to_mock_events

KEYMAP_TEMPLATE = """\
/*
 * 自動生成ファイル - tests/harness/gen_case.py が作成。直接編集しない。
 *
 * シナリオ: {name}
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

    /* 実機シールドの {transform_label} と同じ内容 (gen_case.py が生成) */
    pc_test_transform: pc_test_transform {{
        compatible = "zmk,matrix-transform";
        columns = <{columns}>;
        rows = <{rows}>;
        map = <
{map_property}
        >;
    }};
}};

&kscan {{
    rows = <{rows}>;
    columns = <{columns}>;
    events = <
{events}
    >;
}};
"""

CONF_TEMPLATE = """\
# 自動生成ファイル - tests/harness/gen_case.py が作成。直接編集しない。

# &mkp (マウスボタン) を使うため
CONFIG_ZMK_POINTING=y

# コンボ・ホールドタップの判定ログを出す
CONFIG_ZMK_LOG_LEVEL_DBG=y
"""


def render_keymap(scenario: Scenario, layout: Layout, events: list[MockEvent]) -> str:
    description = (scenario.description or "(説明なし)").strip()
    return KEYMAP_TEMPLATE.format(
        name=scenario.name,
        description=description.replace("\n", "\n * "),
        keymap_path=KEYMAP_FILE,
        transform_label=layout.transform_label,
        columns=layout.columns,
        rows=layout.rows,
        map_property=layout.map_property(),
        events="\n".join(f"        {event.as_dts()}" for event in events),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", type=Path, help="シナリオ YAML のパス")
    parser.add_argument("out_dir", type=Path, help="生成先ディレクトリ")
    args = parser.parse_args(argv)

    layout = load_layout()
    scenario = load_scenario(args.scenario)
    events = to_mock_events(scenario, layout)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_if_changed(
        args.out_dir / "native_posix_64.keymap", render_keymap(scenario, layout, events)
    )
    write_if_changed(args.out_dir / "native_posix_64.conf", CONF_TEMPLATE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
