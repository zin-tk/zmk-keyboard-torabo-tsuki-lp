#!/usr/bin/env bash
# テスト環境(コンテナ/ボリューム)の共通設定。
#
# プロファイルは2種類。
#   native ... 既定。native_sim でキーマップ挙動を高速に確認する(Tier A)
#   split  ... nrf52_bsim + BabbleSim で BLE 分割そのものを再現する(Tier B)
#              nrf52_bsim は 32bit x86 前提のため、Apple Silicon では
#              Rosetta 経由の x86_64 コンテナを使う。
set -euo pipefail

# ZMK 公式 CI と同じビルドイメージ (west + Zephyr SDK 入り)
# ZMK v0.4 は Zephyr 4.1 なので 3.5 タグでは通らない
IMAGE=${ZMK_TEST_IMAGE:-zmkfirmware/zmk-build-arm:stable}

PROFILE=${ZMK_TEST_PROFILE:-native}
case "$PROFILE" in
    native)
        CONTAINER=${ZMK_TEST_CONTAINER:-torabo-tsuki-pc-test}
        WORKSPACE_VOLUME=${ZMK_TEST_WORKSPACE_VOLUME:-torabo-tsuki-zmk-workspace}
        WORK_VOLUME=${ZMK_TEST_WORK_VOLUME:-torabo-tsuki-zmk-work}
        PLATFORM_ARGS=()
        # Tier A は速さが取り柄なので、キーマップに要るモジュールだけ取る。
        MODULE_PROFILE=${ZMK_TEST_MODULE_PROFILE:-keymap}
        ;;
    split)
        CONTAINER=${ZMK_TEST_CONTAINER:-torabo-tsuki-pc-test-split}
        WORKSPACE_VOLUME=${ZMK_TEST_WORKSPACE_VOLUME:-torabo-tsuki-zmk-workspace-x86}
        WORK_VOLUME=${ZMK_TEST_WORK_VOLUME:-torabo-tsuki-zmk-work-x86}
        PLATFORM_ARGS=(--platform linux/amd64)
        # Tier B は実機との差が問題を隠すので、実機と同じモジュール構成にする。
        MODULE_PROFILE=${ZMK_TEST_MODULE_PROFILE:-full}
        ;;
    *)
        echo "不明なプロファイル: $PROFILE (native / split)" >&2
        exit 2
        ;;
esac

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)

require_docker() {
    if ! docker info >/dev/null 2>&1; then
        echo "docker に接続できません。先に colima を起動してください:" >&2
        echo "  colima start --vm-type=vz --vz-rosetta --cpu 6 --memory 12 --disk 80" >&2
        exit 1
    fi
}

container_running() {
    [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null)" = "true" ]
}

# コンテナが無ければ作る。既にあれば何もしない。
ensure_container() {
    if container_running; then
        return
    fi
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
    echo "コンテナを作成します: $CONTAINER ($IMAGE / プロファイル $PROFILE)"
    docker volume create "$WORKSPACE_VOLUME" >/dev/null
    docker volume create "$WORK_VOLUME" >/dev/null
    docker run -d --name "$CONTAINER" \
        "${PLATFORM_ARGS[@]+"${PLATFORM_ARGS[@]}"}" \
        -v "$REPO_ROOT:/zmk-config" \
        -v "$WORKSPACE_VOLUME:/workspace" \
        -v "$WORK_VOLUME:/work" \
        -w /workspace \
        "$IMAGE" sleep infinity >/dev/null
}

# west ワークスペースを用意する(2回目以降は差分取得のみ)。
# マニフェストは毎回作り直す。gen_manifest.py やプロファイルを変えたときに
# 手で作り直す必要がないようにするため。
update_workspace() {
    docker exec "$CONTAINER" bash -euc "
        python3 /zmk-config/tests/env/gen_manifest.py --profile '$MODULE_PROFILE' \
            /workspace/manifest/west.yml
        if [ ! -d /workspace/.west ]; then
            cd /workspace && west init -l manifest
        fi
        cd /workspace
        west update --fetch-opt=--filter=tree:0
        west zephyr-export
    "
}
