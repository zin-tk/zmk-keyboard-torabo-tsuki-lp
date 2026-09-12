#!/usr/bin/env python3
"""config/west.yml から ZMK 本体の取得先だけを抜き出したテスト用マニフェストを作る。

PC テストで使うのは ZMK コアのビヘイビア(kp/mt/lt/mo/mkp/macro/combo など)だけなので、
実機用のモジュール(トラックボール、BLE 管理など)は取得しない。取得量と
ビルド時間を抑えつつ、ZMK 本体のリビジョンは実機ビルドと必ず一致させる。

キーマップが独自モジュールのビヘイビアを使い始めたら、そのモジュールを
ここに追加する必要がある。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_MANIFEST = REPO_ROOT / "config" / "west.yml"
ZMK_PROJECT_NAME = "zmk"


class ManifestError(Exception):
    pass


def build_manifest(source_text: str) -> dict:
    source = yaml.safe_load(source_text)
    try:
        manifest = source["manifest"]
        projects = manifest["projects"]
        remotes = {remote["name"]: remote for remote in manifest.get("remotes", [])}
    except (KeyError, TypeError) as exc:
        raise ManifestError(f"{SOURCE_MANIFEST} の形式が想定と違います: {exc}") from exc

    zmk = next((p for p in projects if p.get("name") == ZMK_PROJECT_NAME), None)
    if zmk is None:
        raise ManifestError(f"{SOURCE_MANIFEST} に {ZMK_PROJECT_NAME} プロジェクトがありません")

    remote_name = zmk.get("remote")
    if remote_name not in remotes:
        raise ManifestError(f"remote {remote_name!r} の定義が見つかりません")

    project = {
        "name": ZMK_PROJECT_NAME,
        "remote": remote_name,
        "revision": zmk["revision"],
        "import": zmk.get("import", {"file": "app/west.yml"}),
    }
    return {
        "manifest": {
            "remotes": [remotes[remote_name]],
            "projects": [project],
            "self": {"path": "manifest"},
        }
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path, help="生成する west.yml のパス")
    args = parser.parse_args(argv)

    manifest = build_manifest(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        "# 自動生成ファイル - tests/env/gen_manifest.py が作成。直接編集しない。\n"
        + yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    print(f"生成しました: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
