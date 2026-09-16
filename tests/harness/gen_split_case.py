#!/usr/bin/env python3
"""シナリオから nrf52_bsim(BLE 分割エミュレーション)用のビルド設定を生成する。

生成物:
  nrf52_bsim.keymap   セントラル(右)側。実機と同じキーマップ + 右半身の打鍵
  nrf52_bsim.conf     bsim で成立させるためだけの設定(両側)
  shield_defaults.conf 実機シールドの Kconfig.defconfig の中身(両側)
  central.conf        実機のセントラル(右)と同じ設定
  peripheral.conf     実機のペリフェラル(左)と同じ設定
  peripheral.overlay  ペリフェラル(左)側の上書き(col-offset と 左半身の打鍵)
  sim.env             シミュレーション長などを実行スクリプトへ渡す

実機と同じく、各半身の kscan は自分の基板の座標(0..6列)を出し、
col-offset 付きのトランスフォームが全体のキー位置へ変換する。

Kconfig は実機の conf をそのまま読んで使う。手書きの写しを持つと実機と
ズレて問題が再現しなくなるため (実際に一度そうなった)。bsim に載らない
ハードウェア向けの項目だけを SKIP_SYMBOLS で落とす。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generated import write_if_changed
from layout import CENTRAL_SIDE, KEYMAP_FILE, PERIPHERAL_SIDE, Layout, load_layout
from scenario import MockEvent, Scenario, load_scenario, to_mock_events_by_side

# 実機のビルド構成 (build.yaml)。右がセントラル、左がペリフェラル。
REPO_ROOT = Path(__file__).resolve().parents[2]
# layout.py と同じく、過去のリビジョンを読ませたいときはここを差し替える。
CONFIG_ROOT = Path(os.environ.get("ZMK_CONFIG_SOURCE_ROOT", REPO_ROOT))
SHIELD_CONF_DIR = CONFIG_ROOT / "boards" / "shields" / "torabo_tsuki_lp"
CENTRAL_CONF_SOURCES = (
    SHIELD_CONF_DIR / "torabo_tsuki_lp_right.conf",
    CONFIG_ROOT / "snippets" / "split-central" / "split-central.conf",
)
PERIPHERAL_CONF_SOURCES = (SHIELD_CONF_DIR / "torabo_tsuki_lp_left.conf",)
# 実機のシールドが立てている既定値。Tier B は shield を使わないボードで
# ビルドするため、ここを読んで自分で流し込まないと丸ごと落ちる。
SHIELD_DEFCONFIG = SHIELD_CONF_DIR / "Kconfig.defconfig"

# nrf52_bsim には載らないので実機 conf から落とす設定。
# いずれも取得していないハードウェア向けモジュール (sekigon-gonnoc) のもので、
# 残すと「未定義シンボルへの代入」の警告になるだけで何も効かない。
SKIP_SYMBOLS = {
    # zmk-feature-cdc-acm-bootloader-trigger: USB がない
    "CONFIG_ZMK_CDC_ACM_BOOTLOADER_TRIGGER",
    # zmk-feature-status-led: LED の devicetree ノードがない
    "CONFIG_ZMK_STATUS_LED",
    # zmk-feature-non-lipo-battery-management: ADC が無いので載らない。
    # 電池そのものは擬似バッテリー (tests/harness/stubs) で代用する
    "CONFIG_ZMK_NON_LIPO_MIN_MV",
    "CONFIG_ZMK_NON_LIPO_LOW_MV",
    # nrf52_bsim に SPI コントローラが無い (トラックボール用で Tier B では不要)
    "CONFIG_SPI",
}

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
#include <physical_layouts.dtsi>

/* 実機と同じキーマップをそのまま使う */
#include "{keymap_path}"

/ {{
    chosen {{
        zmk,physical-layout = &pc_test_layout;
        zmk,battery = &fake_battery;
    }};

    /*
     * 実機は zmk-feature-non-lipo-battery-management が電池を読むが、
     * あれは ADC ドライバを要求するので nrf52_bsim には載らない。
     * 電池まわりの機能 (BAS / バッテリー履歴 / 分割のバッテリープロキシ) を
     * 実機と同じく有効にするため、電圧を固定で返すセンサーで代用する。
     */
    fake_battery: fake_battery {{
        compatible = "zmk,fake-battery";
        millivolts = <1250>;
    }};

    /*
     * 実機と同じく物理レイアウト経由でトランスフォームを指す。
     * chosen zmk,matrix-transform を直接指すと ZMK_STUDIO の BUILD_ASSERT
     * (physical_layouts.c) に引っかかる。
     */
    pc_test_layout: pc_test_layout {{
        compatible = "zmk,physical-layout";
        display-name = "PC Test";
        transform = <&pc_test_transform>;
        keys
{keys_property}
            ;
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

# 設定の永続化を実機と同じ NVS バックエンドで動かす。
# これが無いと Zephyr が CONFIG_SETTINGS_NONE=y を選び、settings_save_one() が
# 黙って捨てられるため、BLE プロファイル・ボンド・activity 設定など
# 「NVS に残った状態」に起因する不具合を一切再現できない。
# nrf52_bsim.dts は flash0 と storage_partition(512K) を既に持っているので
# Kconfig を立てるだけでよい (Zephyr 自身の tests/bsim/bluetooth/host/gatt/ccc_store
# や host/id/settings が同じ構成を使っている)。
CONFIG_FLASH=y
CONFIG_FLASH_MAP=y
CONFIG_NVS=y
CONFIG_SETTINGS=y
CONFIG_SETTINGS_NVS=y

# 実機では zmk-feature-non-lipo-battery-management が select している。
# あのモジュールは ADC を要求するので Tier B には載らないが、これが無いと
# activity.c の「USB 給電が無いときだけ寝る」経路ごと消える。
# USB の有無で挙動が変わる ZMK 中核の唯一の場所なので、ここは実機に揃える。
CONFIG_ZMK_SLEEP=y
"""

# 実機の conf を読むときの注記。生成ファイルの先頭に付ける。
SIDE_CONF_HEADER = """\
# 自動生成ファイル - tests/harness/gen_split_case.py が作成。直接編集しない。
#
# 実機の conf をそのまま取り込んだもの。手で書き写すと実機とズレるため、
# 中身を変えたいときは元ファイルの方を直すこと。
# 取り込み元:
{sources}
"""


def read_shield_defaults(source: Path = SHIELD_DEFCONFIG) -> str:
    """実機シールドの Kconfig.defconfig を conf 形式に落とす。

    Tier B のボードは `nrf52_bsim//zmk_test_mock` で shield を使わないため、
    `if SHIELD_TORABO_TSUKI_LP_*` の中身が一切適用されない。放っておくと
    キーボード名・バッテリー報告・バッテリー履歴・分割の通知などが
    実機と違う状態でテストすることになる。
    """
    if not source.exists():
        raise FileNotFoundError(f"実機の Kconfig.defconfig が見つかりません: {source}")

    lines: list[str] = []
    symbol: str | None = None
    for raw in source.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("config "):
            symbol = "CONFIG_" + line.split(None, 1)[1].strip()
        elif line.startswith("default ") and symbol is not None:
            value = line.split(None, 1)[1].strip()
            if symbol not in SKIP_SYMBOLS:
                lines.append(f"{symbol}={value}")
            symbol = None

    if not lines:
        raise ValueError(f"{source} から既定値を 1 つも読み取れませんでした")

    rel = source.relative_to(CONFIG_ROOT)
    return (
        "# 自動生成ファイル - tests/harness/gen_split_case.py が作成。直接編集しない。\n"
        "#\n"
        "# 実機シールドの Kconfig.defconfig をそのまま取り込んだもの。\n"
        "# Tier B は shield を使わないボードでビルドするので、ここを流し込まないと\n"
        "# 実機で有効な機能がまとめて落ちる。\n"
        f"# 取り込み元:\n#   {rel}\n\n" + "\n".join(lines) + "\n"
    )


def read_real_conf(sources: tuple[Path, ...]) -> str:
    """実機の conf を連結する。bsim に載らない項目だけ落とす。"""
    chunks: list[str] = []
    for source in sources:
        if not source.exists():
            raise FileNotFoundError(f"実機の conf が見つかりません: {source}")
        kept = [
            line
            for line in source.read_text(encoding="utf-8").splitlines()
            if line.split("=", 1)[0].strip() not in SKIP_SYMBOLS
        ]
        rel = source.relative_to(CONFIG_ROOT)
        chunks.append(f"# ----- {rel} -----\n" + "\n".join(kept).strip() + "\n")

    header = SIDE_CONF_HEADER.format(
        sources="\n".join(f"#   {s.relative_to(CONFIG_ROOT)}" for s in sources)
    )
    return header + "\n" + "\n".join(chunks)


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
            keys_property=layout.keys_property(),
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
    write_if_changed(out_dir / "shield_defaults.conf", read_shield_defaults())
    write_if_changed(out_dir / "central.conf", read_real_conf(CENTRAL_CONF_SOURCES))
    write_if_changed(out_dir / "peripheral.conf", read_real_conf(PERIPHERAL_CONF_SOURCES))
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
