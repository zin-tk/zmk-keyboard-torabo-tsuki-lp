#!/usr/bin/env python3
"""zmk.exe のログを、打鍵と出力が時系列で並んだ読みやすい表に変換する。

スナップショット比較(expected.snapshot)とは別に、
「何がいつ起きたか」を目で追うための出力。

    python3 trace.py full.log                   1台分
    python3 trace.py 左=peri.log 右=central.log  複数台を同じ時間軸で並べる

複数台を渡した場合は共通のシミュレーション時刻で並ぶので、
ペリフェラルの打鍵がセントラルに届くまでの遅延がそのまま読める。
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from keycodes import name_of
from layout import SIDE_LABEL, load_layout, read_layer_bindings

# native_posix は "[00:00:00.100,000] <dbg> ..."、
# BabbleSim は "d_00: @00:00:00.100000  [00:00:00.100,000] <dbg> ..." で始まる。
LOG_LINE = re.compile(
    r"^(?:d_\d+:\s+@[\d:.]+\s+)?"
    r"\[(?P<h>\d+):(?P<m>\d+):(?P<s>\d+)\.(?P<ms>\d+),(?P<us>\d+)\]\s+"
    r"<\w+>\s+\w+:\s+(?P<func>[\w.]+):\s+(?P<message>.*)$"
)
KSCAN_EVENT = re.compile(r"Row: (\d+), col: (\d+), position: (\d+), pressed: (true|false)")
HID_EVENT = re.compile(r"usage_page 0x(\w+) keycode 0x(\w+) implicit_mods 0x(\w+) explicit_mods 0x(\w+)")
LAYER_EVENT = re.compile(r"layer_changed: layer (\d+) state (\d+)")
SPLIT_RECEIVED = re.compile(r"Trigger key position state change for (\d+)")


@dataclass(frozen=True)
class Row:
    at_ms: int
    label: str
    kind: str
    text: str


def _timestamp_ms(match: re.Match[str]) -> int:
    return (
        int(match.group("h")) * 3_600_000
        + int(match.group("m")) * 60_000
        + int(match.group("s")) * 1_000
        + int(match.group("ms"))
    )


def _binding_note(bindings: list[str], position: int) -> str:
    # 表示するのはレイヤ0の割当。実際にどのレイヤで解決されたかは
    # 直前の LAYER 行と HID 出力から読む。
    return f"  [L0 {bindings[position]}]" if bindings else ""


def _rows(log_text: str, label: str) -> list[Row]:
    layout = load_layout()
    try:
        bindings = read_layer_bindings(0)
    except Exception:  # 表示用の付加情報なので失敗しても続行する
        bindings = []

    rows: list[Row] = []
    for line in log_text.splitlines():
        match = LOG_LINE.match(line)
        if not match:
            continue

        at_ms = _timestamp_ms(match)
        message = match.group("message")
        func = match.group("func")

        kscan = KSCAN_EVENT.search(message)
        if kscan and func.startswith("zmk_physical_layouts"):
            row, col, position, pressed = kscan.groups()
            side = SIDE_LABEL[layout.side(int(position))]
            action = "押下" if pressed == "true" else "離上"
            rows.append(
                Row(
                    at_ms,
                    label,
                    "KEY",
                    f"{side} pos {position:>2} ({row},{col}) {action}"
                    f"{_binding_note(bindings, int(position))}",
                )
            )
            continue

        split = SPLIT_RECEIVED.search(message)
        if split:
            position = int(split.group(1))
            rows.append(
                Row(
                    at_ms,
                    label,
                    "SPLIT",
                    f"pos {position:>2} をペリフェラルから受信"
                    f"{_binding_note(bindings, position)}",
                )
            )
            continue

        hid = HID_EVENT.search(message)
        if hid and func.startswith("hid_listener_keycode"):
            page, keycode, implicit, explicit = hid.groups()
            action = "press " if func.endswith("pressed") else "release"
            key_name = name_of(int(page, 16), int(keycode, 16))
            named = f"0x{keycode}({key_name})" if key_name else f"0x{keycode}"
            rows.append(
                Row(
                    at_ms,
                    label,
                    "HID",
                    f"{action} page 0x{page} code {named} "
                    f"mods(暗黙 0x{implicit} / 明示 0x{explicit})",
                )
            )
            continue

        layer = LAYER_EVENT.search(message)
        if layer:
            layer_id, state = layer.groups()
            rows.append(
                Row(at_ms, label, "LAYER", f"レイヤ {layer_id} を{'有効' if state == '1' else '無効'}")
            )
            continue

        if "Mouse buttons set to" in message:
            rows.append(Row(at_ms, label, "MOUSE", message))
            continue

        if "bt_stub:" in message:
            rows.append(Row(at_ms, label, "BT", message.replace("bt_stub: ", "")))

    return rows


def render(sources: list[tuple[str, str]]) -> str:
    rows: list[Row] = []
    for label, log_text in sources:
        rows.extend(_rows(log_text, label))
    if not rows:
        return "(トレース対象のイベントがありません)"

    rows.sort(key=lambda row: row.at_ms)
    origin = next((row.at_ms for row in rows if row.kind in ("KEY", "SPLIT")), rows[0].at_ms)
    width = max(len(row.label) for row in rows)

    return "\n".join(
        f"t={row.at_ms - origin:>6}ms  {row.label:<{width}} {row.kind:<5} {row.text}"
        if width
        else f"t={row.at_ms - origin:>6}ms  {row.kind:<5} {row.text}"
        for row in rows
    )


def _parse_source(argument: str) -> tuple[str, str]:
    """`ラベル=パス` または `パス` を受け取る。"""
    label, separator, path = argument.partition("=")
    if not separator:
        label, path = "", argument
    return label, Path(path).read_text(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="+", help="ログのパス(`ラベル=パス` も可)")
    args = parser.parse_args(argv)
    print(render([_parse_source(argument) for argument in args.logs]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
