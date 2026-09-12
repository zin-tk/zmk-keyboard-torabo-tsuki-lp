#!/usr/bin/env bash
#
# PC テスト環境(Tier A: native_sim)の初回セットアップ。
#   - テスト用コンテナを作成
#   - west ワークスペース(ZMK 本体 + Zephyr)を構築
#
# 2回目以降に実行した場合は west update の差分取得だけが走る。
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/config.sh"

require_docker
ensure_container
echo "west ワークスペースを準備します(初回は数十分かかります)"
update_workspace
docker exec "$CONTAINER" bash /zmk-config/tests/env/patch-zmk-native.sh

echo
echo "準備完了。テストを実行するには:"
echo "  ./tests/run.sh"
