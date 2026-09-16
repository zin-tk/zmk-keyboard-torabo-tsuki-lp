#!/usr/bin/env bash
#
# 過去のリビジョンの設定で Tier B を走らせる。
#
#   ./tests/run-split-baseline.sh <git ref> [run-split.sh の引数...]
#
# 「v0.3 なら通るのに v0.4 で落ちる」を、実機に焼かずに同じ土俵で比べるためのもの。
# ハーネス(tests/) は現在のワークツリーのものを使い、ZMK・モジュール・
# シールドの設定だけを指定リビジョンのものに差し替える。
#
# リビジョンごとに別のコンテナ/ボリュームを使う (Zephyr のバージョンが違うため)。
set -euo pipefail

if [ $# -lt 1 ]; then
    echo "使い方: $0 <git ref> [run-split.sh の引数...]" >&2
    exit 2
fi

ref=$1
shift

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
slug=$(printf '%s' "$ref" | tr -c '[:alnum:]' '-' | tr -s '-' | sed 's/^-//;s/-$//')
baseline_dir="$here/../.baseline-$slug"

"$here/env/export_baseline.sh" "$ref" "$baseline_dir"
baseline_dir=$(cd "$baseline_dir" && pwd)

# ベースライン側の Zephyr は別バージョンなので、ワークスペースを分ける。
export ZMK_TEST_PROFILE=split
export ZMK_TEST_BASELINE_DIR="$baseline_dir"
export ZMK_CONFIG_SOURCE_ROOT=/zmk-config-src
export ZMK_TEST_CONTAINER="${ZMK_TEST_CONTAINER:-torabo-tsuki-pc-test-split-$slug}"
export ZMK_TEST_WORKSPACE_VOLUME="${ZMK_TEST_WORKSPACE_VOLUME:-torabo-tsuki-zmk-workspace-x86-$slug}"
export ZMK_TEST_WORK_VOLUME="${ZMK_TEST_WORK_VOLUME:-torabo-tsuki-zmk-work-x86-$slug}"
# Zephyr 3.5 にはボードバリアントの書式が無い。
export ZMK_TEST_BOARD="${ZMK_TEST_BOARD:-nrf52_bsim}"
export ZMK_TEST_IMAGE="${ZMK_TEST_IMAGE:-zmkfirmware/zmk-build-arm:3.5}"
# Zephyr 3.5 の bsim には使えるフラッシュドライバが無いので、
# ソフトウェア実装のフラッシュを差し込んで実機と同じく永続化を成立させる。
export ZMK_TEST_EXTRA_OVERLAY="${ZMK_TEST_EXTRA_OVERLAY:-/zmk-config/tests/harness/sim-flash.overlay}"
# フラッシュはシミュレータ任せ (-flash= は NVMC モデルに取られるため渡さない)。
export ZMK_TEST_PERSISTENCE="${ZMK_TEST_PERSISTENCE:-simflash}"
# Zephyr 3.5 の GATT クライアントは、探索が「もう無い」で終わったあと
# ATT のやり取りが進まなくなる (ホスト役側の制約で、キーボードは正常に応答
# している)。判定は HID のレポート特性を見つけるところまでとする。
export ZMK_TEST_CHECK_REPORTS="${ZMK_TEST_CHECK_REPORTS:-0}"

# ベースライン用のワークスペースは Zephyr のバージョンが違うので別物になる。
# 無ければここで作る (取得と BabbleSim のビルドで初回は時間がかかる)。
if [ "$(docker inspect -f '{{.State.Running}}' "$ZMK_TEST_CONTAINER" 2>/dev/null)" != "true" ]; then
    echo "ベースライン用の環境を用意します: $ZMK_TEST_CONTAINER"
    "$here/env/setup-split.sh"
fi

exec "$here/run-split.sh" "$@"
