#!/usr/bin/env bash
#
# BLE 分割エミュレーション(Tier B)の本体。コンテナ内で動く。
#   1. シナリオ -> セントラル/ペリフェラル 2台分のビルド設定を生成
#   2. nrf52_bsim 向けに 2 台分をビルド
#   3. BabbleSim の仮想2.4GHz電波上で 2 台を同時に走らせる
#   4. セントラル側のログを期待値と比較
#
# 通常はホスト側の tests/run-split.sh から呼ばれる。
set -uo pipefail

REPO_ROOT=${ZMK_CONFIG_ROOT:-/zmk-config}
WORKSPACE=${ZMK_WORKSPACE:-/workspace}
WORK_DIR=${ZMK_TEST_WORK:-/work}
# nrf52_bsim のビルドは環境変数でBabbleSimの場所を受け取る
export BSIM_OUT_PATH=${BSIM_OUT_PATH:-$WORKSPACE/tools/bsim}
export BSIM_COMPONENTS_PATH=${BSIM_COMPONENTS_PATH:-$BSIM_OUT_PATH/components}
HARNESS_DIR="$REPO_ROOT/tests/harness"
SCENARIOS_DIR="$REPO_ROOT/tests/scenarios"
BOARD=nrf52_bsim
SNAPSHOT_NAME=expected-split.snapshot
PHY_TIMEOUT_SEC=600

export PYTHONPATH="$HARNESS_DIR"
export ZMK_APP_DIR="$WORKSPACE/zmk/app"

if [ ! -x "$BSIM_OUT_PATH/bin/bs_2G4_phy_v1" ]; then
    echo "BabbleSim が見つかりません。先に ./tests/env/setup-split.sh を実行してください。" >&2
    exit 1
fi

accept=0
show_trace=0
clean=0
pristine_arg=()
requested=()

while [ $# -gt 0 ]; do
    case "$1" in
        --accept) accept=1 ;;
        --trace) show_trace=1 ;;
        --clean) pristine_arg=(--pristine); clean=1 ;;
        -*) echo "不明なオプション: $1" >&2; exit 2 ;;
        *) requested+=("$1") ;;
    esac
    shift
done

if [ ${#requested[@]} -eq 0 ]; then
    mapfile -t scenario_dirs < <(find "$SCENARIOS_DIR" -mindepth 2 -maxdepth 2 -name scenario.yaml -printf "%h\n" | sort)
else
    scenario_dirs=()
    for name in "${requested[@]}"; do
        if [ -d "$SCENARIOS_DIR/$name" ]; then
            scenario_dirs+=("$SCENARIOS_DIR/$name")
        else
            echo "シナリオが見つかりません: $name" >&2
            exit 2
        fi
    done
fi

build_half() {
    local half="$1" build_dir="$2" gen_dir="$3" log="$4"
    shift 4
    (cd "$WORKSPACE" && west build -s "$WORKSPACE/zmk/app" -d "$build_dir/$half" -b "$BOARD" \
        "${pristine_arg[@]+"${pristine_arg[@]}"}" -- \
        -DZMK_CONFIG="$gen_dir" "$@") > "$log" 2>&1
}

failed=0
for scenario_dir in "${scenario_dirs[@]}"; do
    name=$(basename "$scenario_dir")
    gen_dir="$WORK_DIR/gen-split/$name"
    build_dir="$WORK_DIR/build-split/$name"
    expected="$scenario_dir/$SNAPSHOT_NAME"
    sim_id="tt_$(echo "$name" | tr -c '[:alnum:]_' '_')"

    printf '\n=== %s (BLE 分割) ===\n' "$name"

    [ $clean -eq 1 ] && rm -rf "$gen_dir"
    if ! python3 "$HARNESS_DIR/gen_split_case.py" "$scenario_dir/scenario.yaml" "$gen_dir"; then
        echo "FAIL: $name (シナリオの生成に失敗)"
        failed=1
        continue
    fi
    # シミュレーション長 (SIM_LENGTH_US)
    source "$gen_dir/sim.env"

    if ! build_half central "$build_dir" "$gen_dir" "$WORK_DIR/build-split-$name-central.log" \
            -DCONFIG_ZMK_SPLIT_ROLE_CENTRAL=y; then
        echo "FAIL: $name (セントラルのビルド失敗)"
        tail -25 "$WORK_DIR/build-split-$name-central.log"
        failed=1
        continue
    fi
    if ! build_half peripheral "$build_dir" "$gen_dir" "$WORK_DIR/build-split-$name-peripheral.log" \
            -DEXTRA_DTC_OVERLAY_FILE="$gen_dir/peripheral.overlay"; then
        echo "FAIL: $name (ペリフェラルのビルド失敗)"
        tail -25 "$WORK_DIR/build-split-$name-peripheral.log"
        failed=1
        continue
    fi

    central_exe="${sim_id}_central.exe"
    peripheral_exe="${sim_id}_peripheral.exe"
    cp "$build_dir/central/zephyr/zmk.exe" "$BSIM_OUT_PATH/bin/$central_exe"
    cp "$build_dir/peripheral/zephyr/zmk.exe" "$BSIM_OUT_PATH/bin/$peripheral_exe"

    cd "$BSIM_OUT_PATH/bin"
    "./$central_exe" -d=0 -s="$sim_id" > "$build_dir/central.log" 2>&1 &
    central_pid=$!
    ./bs_device_handbrake -s="$sim_id" -d=1 -r=10 > "$build_dir/handbrake.log" 2>&1 &
    handbrake_pid=$!
    "./$peripheral_exe" -d=2 -s="$sim_id" > "$build_dir/peripheral.log" 2>&1 &
    peripheral_pid=$!

    timeout "$PHY_TIMEOUT_SEC" ./bs_2G4_phy_v1 -s="$sim_id" -D=3 \
        -sim_length="$SIM_LENGTH_US" > "$build_dir/phy.log" 2>&1
    phy_status=$?
    kill "$central_pid" "$handbrake_pid" "$peripheral_pid" 2>/dev/null
    wait "$central_pid" "$handbrake_pid" "$peripheral_pid" 2>/dev/null

    if [ $phy_status -eq 124 ]; then
        echo "FAIL: $name (シミュレーションがタイムアウト)"
        failed=1
        continue
    fi

    # 左右が BLE 接続できていなければ、その先の比較には意味がない。
    if ! grep -qE "Discover complete|\[SUBSCRIBED\]" "$build_dir/central.log"; then
        echo "FAIL: $name (左右が BLE 接続できていません)"
        echo "  セントラル: $build_dir/central.log"
        echo "  ペリフェラル: $build_dir/peripheral.log"
        failed=1
        continue
    fi

    actual="$build_dir/actual.snapshot"
    sed -n -f "$HARNESS_DIR/events.patterns" "$build_dir/central.log" > "$actual"

    if [ $show_trace -eq 1 ]; then
        # 左右を同じ時間軸に並べると、BLE 転送にかかった時間がそのまま読める
        python3 "$HARNESS_DIR/trace.py" \
            "左=$build_dir/peripheral.log" "右=$build_dir/central.log"
        echo
    fi

    if [ ! -f "$expected" ]; then
        if [ $accept -eq 1 ]; then
            cp "$actual" "$expected"
            echo "NEW:  $name ($SNAPSHOT_NAME を作成)"
            cat "$expected"
            continue
        fi
        echo "FAIL: $name ($SNAPSHOT_NAME がありません。--accept で作成できます)"
        echo "--- 今回の出力 ---"
        cat "$actual"
        failed=1
        continue
    fi

    if diff -u "$expected" "$actual"; then
        echo "PASS: $name"
    elif [ $accept -eq 1 ]; then
        cp "$actual" "$expected"
        echo "UPDATED: $name ($SNAPSHOT_NAME を更新)"
    else
        echo "FAIL: $name (出力が期待値と異なる)"
        failed=1
    fi
done

printf '\n'
if [ $failed -eq 0 ]; then
    echo "すべて PASS"
else
    echo "失敗したシナリオがあります"
fi
exit $failed
