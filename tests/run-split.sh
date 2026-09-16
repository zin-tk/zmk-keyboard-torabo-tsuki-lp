#!/usr/bin/env bash
#
# BLE 分割エミュレーション(Tier B)でキーマップの動作を確認する。
#
# 左(ペリフェラル)と右(セントラル)を別プロセスとして起動し、
# BabbleSim の仮想2.4GHz電波で実際に BLE 接続させる。
# tests/run.sh と同じシナリオを使うが、期待値は expected-split.snapshot。
#
#   ./tests/run-split.sh                      すべてのシナリオを実行
#   ./tests/run-split.sh <シナリオ名> ...      指定したシナリオだけ実行
#   ./tests/run-split.sh --trace <シナリオ名>  左右それぞれの時系列を表示
#   ./tests/run-split.sh --accept              出力を期待値として記録/更新
set -euo pipefail

export ZMK_TEST_PROFILE=split
source "$(dirname "${BASH_SOURCE[0]}")/env/config.sh"

require_docker

if ! container_running; then
    echo "分割エミュレーション環境が起動していません。" >&2
    echo "先に ./tests/env/setup-split.sh を実行してください。" >&2
    exit 1
fi

docker exec \
    -e "ZMK_CONFIG_SOURCE_ROOT=${ZMK_CONFIG_SOURCE_ROOT:-/zmk-config}" \
    -e "ZMK_TEST_BOARD=${ZMK_TEST_BOARD:-nrf52_bsim//zmk_test_mock}" \
    -e "ZMK_TEST_EXTRA_CONF=${ZMK_TEST_EXTRA_CONF:-}" \
    -e "ZMK_TEST_EXTRA_OVERLAY=${ZMK_TEST_EXTRA_OVERLAY:-}" \
    -e "ZMK_TEST_PERSISTENCE=${ZMK_TEST_PERSISTENCE:-nvs}" \
    -e "ZMK_TEST_CHECK_REPORTS=${ZMK_TEST_CHECK_REPORTS:-1}" \
    "$CONTAINER" bash /zmk-config/tests/harness/run_split_tests.sh "$@"
