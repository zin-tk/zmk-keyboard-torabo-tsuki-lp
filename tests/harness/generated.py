#!/usr/bin/env python3
"""生成ファイルの書き出し。

内容が同じファイルは書き換えない。タイムスタンプが変わると CMake の
再構成とリビルドが走ってしまい、2回目以降の実行が無駄に遅くなるため。
"""

from __future__ import annotations

from pathlib import Path


def write_if_changed(path: Path, text: str) -> bool:
    """内容が変わったときだけ書き込む。書き込んだら True。"""
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True
