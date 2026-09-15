#!/usr/bin/env python3
"""config/west.yml から ZMK 本体と、キーマップが使うモジュールだけを
抜き出したテスト用マニフェストを作る。

実機用でもキーマップに出てこないもの(トラックボール、BLE 管理、診断など)は
取得しない。取得量とビルド時間を抑えつつ、ZMK 本体と各モジュールの
リビジョンは実機ビルドと必ず一致させる。

キーマップが新しいモジュールのビヘイビアを使い始めたら、
KEYMAP_MODULE_NAMES に名前を足す。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_MANIFEST = REPO_ROOT / "config" / "west.yml"
ZMK_PROJECT_NAME = "zmk"

# config/keymap.keymap が参照するモジュール。west.yml の定義をそのまま引き写す。
KEYMAP_MODULE_NAMES = (
    # 下の 2 つが設定の永続化に使う
    "zmk-feature-custom-settings",
    # &rmacro
    "zmk-feature-runtime-macro",
    # runtime_combo_defaults
    "zmk-feature-runtime-combo",
    # キーマップは使わないが、実機で再起動ループを起こしていたフリーズ検出
    # (task_wdt + 周期フィード) を再現するために必要
    "zmk-feature-watchdog",
)


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

    selected = [
        {
            "name": ZMK_PROJECT_NAME,
            "remote": remote_name,
            "revision": zmk["revision"],
            "import": zmk.get("import", {"file": "app/west.yml"}),
        }
    ]
    used_remotes = [remote_name]

    for name in KEYMAP_MODULE_NAMES:
        module = next((p for p in projects if p.get("name") == name), None)
        if module is None:
            raise ManifestError(f"{SOURCE_MANIFEST} に {name} プロジェクトがありません")
        module_remote = module.get("remote")
        if module_remote not in remotes:
            raise ManifestError(f"remote {module_remote!r} の定義が見つかりません")
        selected.append(dict(module))
        if module_remote not in used_remotes:
            used_remotes.append(module_remote)

    return {
        "manifest": {
            "remotes": [remotes[name] for name in used_remotes],
            "projects": selected,
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
