#!/usr/bin/env python3
"""HID usage コードをキー名に変換する(トレース表示用)。

対応表は ZMK 本体のヘッダから読む。ヘッダが見つからない場合は
名前を付けずに続行する(表示上の補助情報にすぎないため)。
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

KEYBOARD_PAGE = 0x07
CONSUMER_PAGE = 0x0C

HEADER_PATH = (
    Path(os.environ.get("ZMK_APP_DIR", "/workspace/zmk/app"))
    / "include"
    / "dt-bindings"
    / "zmk"
    / "hid_usage.h"
)

# キーボードページは HID_USAGE_KEY_KEYBOARD_* と HID_USAGE_KEY_KEYPAD_* の両方を含む。
DEFINE = re.compile(r"#define\s+HID_USAGE_(KEY|CONSUMER)_(\w+)\s+\(0x([0-9A-Fa-f]+)\)")
PAGE_OF = {"KEY": KEYBOARD_PAGE, "CONSUMER": CONSUMER_PAGE}


@lru_cache(maxsize=1)
def _names() -> dict[tuple[int, int], str]:
    if not HEADER_PATH.exists():
        return {}

    table: dict[tuple[int, int], str] = {}
    for match in DEFINE.finditer(HEADER_PATH.read_text(encoding="utf-8", errors="replace")):
        group, name, value = match.groups()
        key = (PAGE_OF[group], int(value, 16))
        table.setdefault(key, name)  # 同じコードに複数の別名がある場合は先勝ち
    return table


def name_of(page: int, keycode: int) -> str | None:
    return _names().get((page, keycode))
