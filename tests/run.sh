#!/usr/bin/env bash
#
# PC 上でキーマップの動作を確認する。
#
#   ./tests/run.sh                      すべてのシナリオを実行
#   ./tests/run.sh <シナリオ名> ...      指定したシナリオだけ実行
#   ./tests/run.sh --trace <シナリオ名>  打鍵と出力の時系列を表示
#   ./tests/run.sh --accept              出力を期待値として記録/更新
#   ./tests/run.sh --clean               ビルドをやり直す
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/env/config.sh"

require_docker

if ! container_running; then
    echo "テスト環境が起動していません。先に ./tests/env/setup.sh を実行してください。" >&2
    exit 1
fi

docker exec "$CONTAINER" bash /zmk-config/tests/harness/run_tests.sh "$@"
