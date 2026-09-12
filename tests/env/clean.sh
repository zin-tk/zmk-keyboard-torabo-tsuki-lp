#!/usr/bin/env bash
# テスト環境(コンテナとボリューム)を削除してディスクを空ける。
#   ./tests/env/clean.sh         Tier A
#   ./tests/env/clean.sh split   Tier B(BLE 分割)
#
# 削除後にもう一度使うには setup.sh / setup-split.sh をやり直す(再取得が走る)。
set -euo pipefail
export ZMK_TEST_PROFILE=${1:-native}
source "$(dirname "${BASH_SOURCE[0]}")/config.sh"
require_docker

echo "削除します: コンテナ $CONTAINER / ボリューム $WORKSPACE_VOLUME, $WORK_VOLUME"
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
docker volume rm "$WORKSPACE_VOLUME" "$WORK_VOLUME" >/dev/null 2>&1 || true
echo "完了"
