#!/usr/bin/env bash
# 調査用にテストコンテナへ入る。
#   ./tests/env/shell.sh         Tier A のコンテナ
#   ./tests/env/shell.sh split   Tier B(BLE 分割)のコンテナ
set -euo pipefail
export ZMK_TEST_PROFILE=${1:-native}
source "$(dirname "${BASH_SOURCE[0]}")/config.sh"
require_docker
exec docker exec -it "$CONTAINER" bash
