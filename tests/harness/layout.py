#!/usr/bin/env python3
"""シールド定義から物理レイアウト(マトリクストランスフォーム)を読み出す。

キー位置番号と (row, col) の対応、および左右どちらの半身かは
boards/shields/torabo_tsuki_lp/ が唯一の出典。
ここでは値を複製せず読み取るだけにして、実機ファームとテストのズレを防ぐ。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
# 過去のリビジョンと比べたいときは、tests/env/export_baseline.sh で展開した
# ディレクトリを ZMK_CONFIG_SOURCE_ROOT で指す。
CONFIG_ROOT = Path(os.environ.get("ZMK_CONFIG_SOURCE_ROOT", REPO_ROOT))

SHIELD_DIR = CONFIG_ROOT / "boards" / "shields" / "torabo_tsuki_lp"
SHIELD_DTSI = SHIELD_DIR / "torabo_tsuki_lp.dtsi"
RIGHT_OVERLAY = SHIELD_DIR / "torabo_tsuki_lp_right.overlay"
KEYMAP_FILE = CONFIG_ROOT / "config" / "keymap.keymap"

# build.yaml のビルドターゲット定義より: 左がペリフェラル / 右がセントラル。
PERIPHERAL_SIDE = "left"
CENTRAL_SIDE = "right"

SIDE_LABEL = {PERIPHERAL_SIDE: "L(周辺)", CENTRAL_SIDE: "R(中央)"}

# 物理レイアウトのキー 1 個分の大きさ。実機の layouts.dtsi と同じ単位。
KEY_UNIT = 100


class LayoutError(Exception):
    """シールド定義の読み取りに失敗した場合に送出する。"""


def _read(path: Path) -> str:
    if not path.exists():
        raise LayoutError(f"必要なファイルが見つかりません: {path}")
    return path.read_text(encoding="utf-8")


def _block_of(text: str, start_pattern: str) -> str:
    """`start_pattern` にマッチした直後の `{...}` ブロック本体を返す。"""
    match = re.search(start_pattern, text)
    if not match:
        raise LayoutError(f"定義が見つかりません: /{start_pattern}/")

    open_index = text.find("{", match.end() - 1)
    if open_index < 0:
        raise LayoutError(f"ブロックの開始 '{{' が見つかりません: /{start_pattern}/")

    depth = 0
    for index in range(open_index, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[open_index + 1 : index]
    raise LayoutError(f"ブロックが閉じていません: /{start_pattern}/")


def _int_prop(block: str, name: str) -> int:
    match = re.search(rf"\b{re.escape(name)}\s*=\s*<\s*(\d+)\s*>", block)
    if not match:
        raise LayoutError(f"プロパティ {name} が見つかりません")
    return int(match.group(1))


@dataclass(frozen=True)
class Layout:
    """実機と同じキー位置 <-> マトリクス座標の対応。"""

    transform_label: str
    rows: int
    columns: int
    col_offset: int
    positions: tuple[tuple[int, int], ...]  # index = キー位置, 値 = (row, col)

    @property
    def key_count(self) -> int:
        return len(self.positions)

    def row_col(self, position: int) -> tuple[int, int]:
        if not 0 <= position < self.key_count:
            raise LayoutError(
                f"キー位置 {position} は範囲外です (0..{self.key_count - 1})"
            )
        return self.positions[position]

    def side(self, position: int) -> str:
        """そのキー位置がどちらの半身にあるか。"""
        _, col = self.row_col(position)
        return CENTRAL_SIDE if col >= self.col_offset else PERIPHERAL_SIDE

    def is_peripheral(self, position: int) -> bool:
        return self.side(position) == PERIPHERAL_SIDE

    def local_row_col(self, position: int) -> tuple[int, int]:
        """その半身の基板から見た (row, col)。

        実機では各半身が自分の基板の座標を読み、セントラル側の
        トランスフォームが col-offset を足して全体のキー位置に変換する。
        """
        row, col = self.row_col(position)
        if self.side(position) == CENTRAL_SIDE:
            return (row, col - self.col_offset)
        return (row, col)

    def col_offset_of(self, side: str) -> int:
        return self.col_offset if side == CENTRAL_SIDE else 0

    def unmapped_row_col(self, col_offset: int = 0) -> tuple[int, int]:
        """トランスフォームに含まれない (row, col)。ダミーイベント用。

        col_offset を渡すと、その半身の座標系での座標を返す。
        """
        mapped = set(self.positions)
        for row in range(self.rows):
            for col in range(self.columns - col_offset):
                if (row, col + col_offset) not in mapped:
                    return (row, col)
        raise LayoutError("未使用のマトリクス座標がありません")

    def map_property(self, indent: str = "            ") -> str:
        """devicetree の map プロパティ本体を組み立てる。

        並び順がそのままキー位置番号になるため、読み取った順序を崩さない。
        改行は行(row)が変わる箇所に入れるだけの見た目上の処理。
        """
        lines: list[str] = []
        current: list[str] = []
        last_row: int | None = None
        for row, col in self.positions:
            if last_row is not None and row != last_row:
                lines.append(indent + " ".join(current))
                current = []
            current.append(f"RC({row},{col})")
            last_row = row
        if current:
            lines.append(indent + " ".join(current))
        return "\n".join(lines)


    def keys_property(self, indent: str = "            ") -> str:
        """devicetree の keys プロパティ本体を組み立てる。

        ZMK_STUDIO を有効にすると物理レイアウトに keys が必須になる
        (`physical_layouts.c` の BUILD_ASSERT)。テストは Studio のレイアウト
        UI を使わないので、実機の座標を写さず単純な格子で足りる。
        並び順は map と同じでなければならない。
        """
        lines = [
            f"{indent}{'=' if index == 0 else ','} "
            f"<&key_physical_attrs {KEY_UNIT} {KEY_UNIT} "
            f"{col * KEY_UNIT} {row * KEY_UNIT} 0 0 0>"
            for index, (row, col) in enumerate(self.positions)
        ]
        return "\n".join(lines)


def load_layout() -> Layout:
    """chosen zmk,physical-layout -> transform を辿って実機の定義を読む。"""
    dtsi = _read(SHIELD_DTSI)

    chosen = _block_of(dtsi, r"\bchosen\s*\{")
    layout_match = re.search(r"zmk,physical-layout\s*=\s*&(\w+)", chosen)
    if not layout_match:
        raise LayoutError("chosen に zmk,physical-layout がありません")
    layout_label = layout_match.group(1)

    layout_block = _block_of(dtsi, rf"&{layout_label}\s*\{{")
    transform_match = re.search(r"transform\s*=\s*<&(\w+)>", layout_block)
    if not transform_match:
        raise LayoutError(f"&{layout_label} に transform がありません")
    transform_label = transform_match.group(1)

    transform_block = _block_of(dtsi, rf"\b{transform_label}\s*:\s*\w+\s*\{{")
    rows = _int_prop(transform_block, "rows")
    columns = _int_prop(transform_block, "columns")
    map_match = re.search(r"\bmap\s*=\s*<(.*?)>\s*;", transform_block, re.S)
    if not map_match:
        raise LayoutError(f"{transform_label} に map がありません")
    positions = tuple(
        (int(r), int(c))
        for r, c in re.findall(r"RC\(\s*(\d+)\s*,\s*(\d+)\s*\)", map_match.group(1))
    )
    if not positions:
        raise LayoutError(f"{transform_label} の map が空です")

    right = _read(RIGHT_OVERLAY)
    offset_block = _block_of(right, rf"&{transform_label}\s*\{{")
    col_offset = _int_prop(offset_block, "col-offset")

    return Layout(
        transform_label=transform_label,
        rows=rows,
        columns=columns,
        col_offset=col_offset,
        positions=positions,
    )


def read_layer_bindings(layer_index: int = 0) -> list[str]:
    """config/keymap.keymap から指定レイヤのバインディング一覧を読む(表示用)。"""
    keymap_node = _block_of(_read(KEYMAP_FILE), r"\bkeymap\s*\{")
    layers = re.findall(r"bindings\s*=\s*<(.*?)>\s*;", keymap_node, re.S)
    if layer_index >= len(layers):
        raise LayoutError(f"レイヤ {layer_index} がありません (全 {len(layers)} レイヤ)")
    tokens = ["&" + token.strip() for token in layers[layer_index].split("&")[1:]]
    return [" ".join(token.split()) for token in tokens]
