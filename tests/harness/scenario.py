#!/usr/bin/env python3
"""シナリオ(打鍵の台本)を読み込み、kscan mock のイベント列に変換する。

実機の分割キーボードでは、ペリフェラル(左)の打鍵は BLE 経由でセントラル(右)に
届くため、指が触れた時刻よりも遅れてキーマップに入力される。
ここではその遅延を `peripheral_latency_ms` として時刻をずらすことで再現する。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from layout import CENTRAL_SIDE, PERIPHERAL_SIDE, Layout, LayoutError

# ZMK_MOCK_PRESS の msec は 15bit に格納されるため上限がある。
MAX_EVENT_GAP_MS = 32767
# 起動直後の打鍵だと require-prior-idle-ms の判定に引っかかるため、十分に間を置く。
DEFAULT_START_OFFSET_MS = 250
DEFAULT_SETTLE_MS = 400
DEFAULT_TAP_HOLD_MS = 30


class ScenarioError(Exception):
    """シナリオ記述が不正な場合に送出する。"""


@dataclass(frozen=True)
class Step:
    """シナリオ上の1打鍵(指が動いた時刻)。"""

    at_ms: int
    position: int
    pressed: bool


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    peripheral_latency_ms: int
    settle_ms: int
    start_offset_ms: int
    steps: tuple[Step, ...]


@dataclass(frozen=True)
class MockEvent:
    """kscan mock に渡す1イベント。gap_ms は「このイベントの後の待ち時間」。"""

    row: int
    col: int
    pressed: bool
    gap_ms: int
    comment: str

    def as_dts(self) -> str:
        macro = "ZMK_MOCK_PRESS" if self.pressed else "ZMK_MOCK_RELEASE"
        return f"{macro}({self.row},{self.col},{self.gap_ms}) /* {self.comment} */"


def _require_int(value: object, field: str, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ScenarioError(f"{field} は整数で指定してください: {value!r}")
    if value < minimum:
        raise ScenarioError(f"{field} は {minimum} 以上で指定してください: {value}")
    return value


def _parse_step(raw: object, index: int, default_hold_ms: int) -> list[Step]:
    if not isinstance(raw, dict):
        raise ScenarioError(f"steps[{index}] はマッピングで指定してください: {raw!r}")

    at_ms = _require_int(raw.get("at", 0), f"steps[{index}].at")
    actions = [key for key in ("press", "release", "tap") if key in raw]
    if len(actions) != 1:
        raise ScenarioError(
            f"steps[{index}] には press / release / tap のいずれか1つが必要です"
        )

    action = actions[0]
    position = _require_int(raw[action], f"steps[{index}].{action}")

    if action == "press":
        return [Step(at_ms, position, True)]
    if action == "release":
        return [Step(at_ms, position, False)]

    hold_ms = _require_int(raw.get("hold_ms", default_hold_ms), f"steps[{index}].hold_ms")
    return [Step(at_ms, position, True), Step(at_ms + hold_ms, position, False)]


def load_scenario(path: Path) -> Scenario:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ScenarioError(f"{path}: YAML として読めません: {exc}") from exc

    if not isinstance(raw, dict):
        raise ScenarioError(f"{path}: トップレベルはマッピングにしてください")

    raw_steps = raw.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ScenarioError(f"{path}: steps を1つ以上定義してください")

    default_hold_ms = _require_int(
        raw.get("tap_hold_ms", DEFAULT_TAP_HOLD_MS), "tap_hold_ms"
    )
    steps: list[Step] = []
    for index, raw_step in enumerate(raw_steps):
        steps.extend(_parse_step(raw_step, index, default_hold_ms))

    return Scenario(
        name=str(raw.get("name") or path.parent.name),
        description=str(raw.get("description") or ""),
        peripheral_latency_ms=_require_int(
            raw.get("peripheral_latency_ms", 0), "peripheral_latency_ms"
        ),
        settle_ms=_require_int(raw.get("settle_ms", DEFAULT_SETTLE_MS), "settle_ms", 1),
        start_offset_ms=_require_int(
            raw.get("start_offset_ms", DEFAULT_START_OFFSET_MS), "start_offset_ms", 1
        ),
        steps=tuple(steps),
    )


def arrival_times(scenario: Scenario, layout: Layout) -> list[tuple[int, Step]]:
    """セントラル(キーマップ)に届く時刻順に並べ替える。"""
    try:
        arrivals = [
            (
                step.at_ms
                + (scenario.peripheral_latency_ms if layout.is_peripheral(step.position) else 0),
                step,
            )
            for step in scenario.steps
        ]
    except LayoutError as exc:
        raise ScenarioError(str(exc)) from exc

    # 同時刻はシナリオの記述順を保つ(sorted は安定ソート)。
    return sorted(arrivals, key=lambda item: item[0])


def _check_gap(gap_ms: int) -> None:
    if gap_ms > MAX_EVENT_GAP_MS:
        raise ScenarioError(
            f"イベント間隔 {gap_ms}ms が上限 {MAX_EVENT_GAP_MS}ms を超えています"
        )


def _build_events(
    entries: list[tuple[int, Step]],
    layout: Layout,
    *,
    base_time_ms: int,
    start_offset_ms: int,
    settle_ms: int,
    local_coords: bool,
    col_offset: int,
) -> list[MockEvent]:
    """1台分の kscan イベント列を作る。

    mock ドライバは events[i] の msec を「events[i] を出した後の待ち時間」として
    使い、かつ最初の要素の msec を起動後の初回待ちにも使う。
    そのため先頭にトランスフォーム外の座標(=キーマップに影響しない)のダミーを
    2つ置き、実イベント同士の間隔がシナリオ通りになるようにしている。
    """
    dummy_row, dummy_col = layout.unmapped_row_col(col_offset)

    def dummy(gap_ms: int, comment: str) -> MockEvent:
        _check_gap(gap_ms)
        return MockEvent(
            row=dummy_row,
            col=dummy_col,
            pressed=False,
            gap_ms=gap_ms,
            comment=comment,
        )

    if not entries:
        return [dummy(settle_ms, "このデバイスには打鍵が無い")]

    # 1つ目は起動待ち(その msec が初回待ちと次イベントまでの間隔の両方に使われる)、
    # 2つ目で「共通の基準時刻からこのデバイスの初回打鍵までのずれ」を作る。
    # これで左右のデバイス間の相対的なタイミングが保たれる。
    lead_in_ms = entries[0][0] - base_time_ms
    events = [
        dummy(start_offset_ms, "起動待ち(トランスフォーム外のため無視される)"),
        dummy(lead_in_ms, f"基準時刻から +{lead_in_ms}ms のずれを作る"),
    ]

    for index, (arrival, step) in enumerate(entries):
        row, col = (
            layout.local_row_col(step.position)
            if local_coords
            else layout.row_col(step.position)
        )
        if index + 1 < len(entries):
            gap_ms = entries[index + 1][0] - arrival
        else:
            gap_ms = settle_ms

        _check_gap(gap_ms)

        action = "press" if step.pressed else "release"
        delay = arrival - step.at_ms
        delay_note = f" (+{delay}ms 転送遅延)" if delay else ""
        events.append(
            MockEvent(
                row=row,
                col=col,
                pressed=step.pressed,
                gap_ms=gap_ms,
                comment=(
                    f"t={arrival - base_time_ms}ms {layout.side(step.position)} "
                    f"pos {step.position} {action}{delay_note}"
                ),
            )
        )

    return events


def to_mock_events(scenario: Scenario, layout: Layout) -> list[MockEvent]:
    """セントラル1台に両半身を流し込む場合(Tier A)のイベント列。"""
    timeline = arrival_times(scenario, layout)
    return _build_events(
        timeline,
        layout,
        base_time_ms=timeline[0][0],
        start_offset_ms=scenario.start_offset_ms,
        settle_ms=scenario.settle_ms,
        local_coords=False,
        col_offset=0,
    )


def to_mock_events_by_side(
    scenario: Scenario, layout: Layout, *, start_offset_ms: int, settle_ms: int
) -> dict[str, list[MockEvent]]:
    """半身ごとに分けたイベント列(Tier B)。

    転送遅延は実際の BLE 通信が生むため、ここでは注入しない
    (scenario の peripheral_latency_ms は無視される)。
    """
    entries = sorted(((step.at_ms, step) for step in scenario.steps), key=lambda item: item[0])
    base_time_ms = entries[0][0]

    return {
        side: _build_events(
            [item for item in entries if layout.side(item[1].position) == side],
            layout,
            base_time_ms=base_time_ms,
            start_offset_ms=start_offset_ms,
            settle_ms=settle_ms,
            local_coords=True,
            col_offset=layout.col_offset_of(side),
        )
        for side in (PERIPHERAL_SIDE, CENTRAL_SIDE)
    }
