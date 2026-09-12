#!/usr/bin/env python3
"""キー位置番号の一覧を表示する。シナリオを書くときの早見表。

    python3 tests/harness/show_layout.py          # レイヤ0
    python3 tests/harness/show_layout.py 4        # レイヤ4
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from layout import CENTRAL_SIDE, PERIPHERAL_SIDE, load_layout, read_layer_bindings

CELL_WIDTH = 18


def render(layer_index: int) -> str:
    layout = load_layout()
    bindings = read_layer_bindings(layer_index)

    lines = [
        f"レイヤ {layer_index} / 全 {layout.key_count} キー "
        f"({PERIPHERAL_SIDE}=ペリフェラル, {CENTRAL_SIDE}=セントラル)",
        "",
    ]
    for row in range(layout.rows):
        left_cells, right_cells = [], []
        for position in range(layout.key_count):
            position_row, _ = layout.row_col(position)
            if position_row != row:
                continue
            label = bindings[position].replace("&kp ", "")
            cell = f"{position:>2}:{label}"[: CELL_WIDTH - 1].ljust(CELL_WIDTH)
            if layout.side(position) == PERIPHERAL_SIDE:
                left_cells.append(cell)
            else:
                right_cells.append(cell)
        lines.append("".join(left_cells) + " | " + "".join(right_cells))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("layer", nargs="?", type=int, default=0, help="レイヤ番号 (既定 0)")
    args = parser.parse_args(argv)
    print(render(args.layer))
    return 0


if __name__ == "__main__":
    sys.exit(main())
