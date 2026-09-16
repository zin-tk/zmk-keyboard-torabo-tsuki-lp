#!/usr/bin/env bash
#
# BLE 分割エミュレーション(Tier B)の本体。コンテナ内で動く。
#   1. シナリオ -> セントラル/ペリフェラル 2台分のビルド設定を生成
#   2. nrf52_bsim 向けに 2 台分 + ホスト役をビルド
#   3. BabbleSim の仮想2.4GHz電波上で 3 台を同時に走らせる
#      (左右に加えて、PC/スマホ相当のホスト役を 1 台)
#   4. セントラル側のログを期待値と比較
#
# 各機のフラッシュは $WORK_DIR/build-split/<名前>/flash/*.bin に出る。
# --reboot を付けると、同じフラッシュのまま 2 回目を走らせる
# (= ボンドが NVS に残った状態での電源投入を再現する)。
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
# ZMK v0.4 (Zephyr 4.1) は mock kscan をボードのバリアントとして持つ。
# Zephyr 3.5 の頃はバリアントの書式が無く、ZMK の app/boards/nrf52_bsim.overlay が
# 同じ役目を果たすので、ベースライン比較のときは素の nrf52_bsim を指定する。
BOARD=${ZMK_TEST_BOARD:-nrf52_bsim//zmk_test_mock}
# ベースライン比較のときに最後へ重ねる conf。
EXTRA_CONF=${ZMK_TEST_EXTRA_CONF:-}
# 同じく重ねる devicetree オーバーレイ (tests/harness/sim-flash.overlay など)。
EXTRA_OVERLAY=${ZMK_TEST_EXTRA_OVERLAY:-}
# 設定の永続化の持ち方。
#   nvs  既定。-flash=<ファイル> で機体ごとに実体を持つ (--reboot が使える)
#   simflash  フラッシュシミュレータ任せ。-flash= は nrf52_bsim の NVMC モデルに
#             取られてしまうので渡さず、機体ごとの作業ディレクトリに置かれる
#             既定のファイル (flash.bin) をそのまま使う
PERSISTENCE=${ZMK_TEST_PERSISTENCE:-nvs}
# ホスト役が HID レポートの受信まで確認できるか。
# Zephyr 3.5 (ベースライン比較) では GATT クライアントが CCC の書き込みまで
# 進めないため、キーボードが HID を正しく公開しているところまでで判定する。
CHECK_REPORTS=${ZMK_TEST_CHECK_REPORTS:-1}
# ホスト役は ZMK を使わない素の Zephyr アプリなので、mock kscan の付いた
# バリアントではなく Zephyr 標準の nrf52_bsim をそのまま使う。
HOST_BOARD=nrf52_bsim
HOST_SRC_DIR="$REPO_ROOT/tests/harness/ble_host"
SNAPSHOT_NAME=expected-split.snapshot
PHY_TIMEOUT_SEC=600

export PYTHONPATH="$HARNESS_DIR"
export ZMK_APP_DIR="$WORKSPACE/zmk/app"

# コンテナを作り直すと ~/.cmake のパッケージ登録が消える。ZMK の app は
# find_package(Zephyr) をこれで解決しているので、無ければ登録し直す。
if [ ! -d "$HOME/.cmake/packages/Zephyr" ]; then
    (cd "$WORKSPACE" && west zephyr-export) >/dev/null 2>&1
fi

if [ ! -x "$BSIM_OUT_PATH/bin/bs_2G4_phy_v1" ]; then
    echo "BabbleSim が見つかりません。先に ./tests/env/setup-split.sh を実行してください。" >&2
    exit 1
fi

accept=0
show_trace=0
clean=0
reboot=0
pristine_arg=()
requested=()

while [ $# -gt 0 ]; do
    case "$1" in
        --accept) accept=1 ;;
        --trace) show_trace=1 ;;
        --clean) pristine_arg=(--pristine); clean=1 ;;
        --reboot) reboot=1 ;;
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

# ホスト役はシナリオに依存しないので、全シナリオで 1 つの成果物を使い回す。
host_build_dir="$WORK_DIR/build-split/_ble_host"
host_build_log="$WORK_DIR/build-split-ble-host.log"
host_conf_arg=()
if [ -n "$EXTRA_CONF" ] || [ -n "$EXTRA_OVERLAY" ]; then
    host_conf_arg=(--)
    [ -n "$EXTRA_CONF" ] && host_conf_arg+=("-DEXTRA_CONF_FILE=$EXTRA_CONF")
    [ -n "$EXTRA_OVERLAY" ] && host_conf_arg+=("-DEXTRA_DTC_OVERLAY_FILE=$EXTRA_OVERLAY")
fi
if ! (cd "$WORKSPACE" && west build -s "$HOST_SRC_DIR" -d "$host_build_dir" -b "$HOST_BOARD" \
        "${pristine_arg[@]+"${pristine_arg[@]}"}" \
        "${host_conf_arg[@]+"${host_conf_arg[@]}"}") > "$host_build_log" 2>&1; then
    echo "ホスト役のビルドに失敗しました: $host_build_log" >&2
    tail -25 "$host_build_log" >&2
    exit 1
fi

# 1 回分のシミュレーションを走らせる。$1 はログの接尾辞("" か "-2")。
# 結果は phy_status に入る。フラッシュはファイルに置くので、
# 同じ flash_dir でもう一度呼べば「電源を入れ直した」ことになる。
run_simulation() {
    local suffix="$1"
    local central_pid handbrake_pid peripheral_pid host_pid

    # 前回が途中で落ちていると、その時のロックが残っていて全機が起動に失敗する。
    # 中身は今から上書きするものだけなので、消してから始める。
    rm -rf "/tmp/bs_root/$sim_id"

    # 各機は自分の作業ディレクトリで動かす。フラッシュシミュレータは
    # 作業ディレクトリの flash.bin を既定で使うので、分けないと 4 台が
    # 同じファイルを掴んで壊れる。--reboot では同じ場所を引き継ぐ。
    local d
    for d in central peripheral host; do
        mkdir -p "$flash_dir/$d"
    done

    # NVMC モデルを使う構成では、フラッシュの実体をファイルで明示する。
    local flash_central=() flash_peripheral=() flash_host=()
    if [ "$PERSISTENCE" = nvs ]; then
        flash_central=(-flash="$flash_dir/central.bin")
        flash_peripheral=(-flash="$flash_dir/peripheral.bin")
        flash_host=(-flash="$flash_dir/host.bin")
    fi

    (cd "$flash_dir/central" && "$BSIM_OUT_PATH/bin/$central_exe" -d=0 -s="$sim_id" \
        "${flash_central[@]+"${flash_central[@]}"}") > "$build_dir/central$suffix.log" 2>&1 &
    central_pid=$!
    (cd "$flash_dir/peripheral" && "$BSIM_OUT_PATH/bin/$peripheral_exe" -d=2 -s="$sim_id" \
        "${flash_peripheral[@]+"${flash_peripheral[@]}"}") > "$build_dir/peripheral$suffix.log" 2>&1 &
    peripheral_pid=$!
    (cd "$flash_dir/host" && "$BSIM_OUT_PATH/bin/$host_exe" -d=3 -s="$sim_id" \
        "${flash_host[@]+"${flash_host[@]}"}") > "$build_dir/host$suffix.log" 2>&1 &
    host_pid=$!

    # phy と handbrake は ../lib/ を相対で参照するので bsim の bin から動かす。
    cd "$BSIM_OUT_PATH/bin"
    ./bs_device_handbrake -s="$sim_id" -d=1 -r=10 > "$build_dir/handbrake$suffix.log" 2>&1 &
    handbrake_pid=$!

    timeout "$PHY_TIMEOUT_SEC" ./bs_2G4_phy_v1 -s="$sim_id" -D=4 \
        -sim_length="$SIM_LENGTH_US" > "$build_dir/phy$suffix.log" 2>&1
    phy_status=$?
    kill "$central_pid" "$handbrake_pid" "$peripheral_pid" "$host_pid" 2>/dev/null
    wait "$central_pid" "$handbrake_pid" "$peripheral_pid" "$host_pid" 2>/dev/null
}

# 1 回分の結果を確かめる。$1 はログの接尾辞、$2 は表示用のラベル。
check_pass() {
    local suffix="$1" label="$2"

    if [ "$phy_status" -eq 124 ]; then
        echo "FAIL: $name ($label シミュレーションがタイムアウト)"
        return 1
    fi

    # 左右が BLE 接続できていなければ、その先の比較には意味がない。
    if ! grep -qE "Discover complete|\[SUBSCRIBED\]" "$build_dir/central$suffix.log"; then
        echo "FAIL: $name ($label 左右が BLE 接続できていません)"
        echo "  セントラル: $build_dir/central$suffix.log"
        echo "  ペリフェラル: $build_dir/peripheral$suffix.log"
        return 1
    fi

    # ホスト役から見て、キーボードが広告を出して接続できているか。
    # 実機で起きた「ホストと BLE 接続できない」はここで落ちる。
    if ! grep -q "HOST: connected" "$build_dir/host$suffix.log"; then
        echo "FAIL: $name ($label ホストが BLE 接続できていません)"
        echo "  ホスト: $build_dir/host$suffix.log"
        return 1
    fi

    # スナップショットは ZMK 内部のログなので、HOG が壊れていても通ってしまう。
    # ホスト側から見た HID の状態を別に確かめる。
    if [ "$CHECK_REPORTS" = 1 ]; then
        if ! grep -q "HOST: report " "$build_dir/host$suffix.log"; then
            echo "FAIL: $name ($label ホストに HID レポートが届いていません)"
            echo "  ホスト: $build_dir/host$suffix.log"
            return 1
        fi
    elif ! grep -q "HOST: found .* report characteristic" "$build_dir/host$suffix.log"; then
        echo "FAIL: $name ($label ホストが HID のレポート特性を見つけられていません)"
        echo "  ホスト: $build_dir/host$suffix.log"
        return 1
    fi

    return 0
}

build_half() {
    local half="$1" build_dir="$2" gen_dir="$3" log="$4"
    shift 4
    # stubs は擬似バッテリーを持ち込む。実機のシールドが立てている
    # CONFIG_ZMK_BATTERY_REPORTING を Tier B でも成立させるために要る。
    (cd "$WORKSPACE" && west build -s "$WORKSPACE/zmk/app" -d "$build_dir/$half" -b "$BOARD" \
        "${pristine_arg[@]+"${pristine_arg[@]}"}" -- \
        -DZMK_CONFIG="$gen_dir" -DZMK_EXTRA_MODULES="$HARNESS_DIR/stubs" "$@") > "$log" 2>&1
}

failed=0
for scenario_dir in "${scenario_dirs[@]}"; do
    name=$(basename "$scenario_dir")
    gen_dir="$WORK_DIR/gen-split/$name"
    build_dir="$WORK_DIR/build-split/$name"
    flash_dir="$build_dir/flash"
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
            -DCONFIG_ZMK_SPLIT_ROLE_CENTRAL=y \
            ${EXTRA_OVERLAY:+-DEXTRA_DTC_OVERLAY_FILE="$EXTRA_OVERLAY"} \
            -DEXTRA_CONF_FILE="$gen_dir/shield_defaults.conf;$gen_dir/central.conf${EXTRA_CONF:+;$EXTRA_CONF}"; then
        echo "FAIL: $name (セントラルのビルド失敗)"
        tail -25 "$WORK_DIR/build-split-$name-central.log"
        failed=1
        continue
    fi
    if ! build_half peripheral "$build_dir" "$gen_dir" "$WORK_DIR/build-split-$name-peripheral.log" \
            -DEXTRA_DTC_OVERLAY_FILE="$gen_dir/peripheral.overlay${EXTRA_OVERLAY:+;$EXTRA_OVERLAY}" \
            -DEXTRA_CONF_FILE="$gen_dir/shield_defaults.conf;$gen_dir/peripheral.conf${EXTRA_CONF:+;$EXTRA_CONF}"; then
        echo "FAIL: $name (ペリフェラルのビルド失敗)"
        tail -25 "$WORK_DIR/build-split-$name-peripheral.log"
        failed=1
        continue
    fi

    central_exe="${sim_id}_central.exe"
    peripheral_exe="${sim_id}_peripheral.exe"
    host_exe="${sim_id}_host.exe"
    cp "$build_dir/central/zephyr/zmk.exe" "$BSIM_OUT_PATH/bin/$central_exe"
    cp "$build_dir/peripheral/zephyr/zmk.exe" "$BSIM_OUT_PATH/bin/$peripheral_exe"
    cp "$host_build_dir/zephyr/zephyr.exe" "$BSIM_OUT_PATH/bin/$host_exe"

    # フラッシュは毎回まっさらから始める。--reboot の 2 回目だけが引き継ぐ。
    rm -rf "$flash_dir"
    mkdir -p "$flash_dir"

    run_simulation ""
    if ! check_pass "" "初回:"; then
        failed=1
        continue
    fi

    # 比較に使うのは最後のパスのログ。
    suffix=""
    if [ $reboot -eq 1 ]; then
        echo "  初回 OK。同じフラッシュのまま電源を入れ直します"
        run_simulation "-2"
        if ! check_pass "-2" "再起動後:"; then
            failed=1
            continue
        fi
        suffix="-2"
    fi

    actual="$build_dir/actual.snapshot"
    sed -n -f "$HARNESS_DIR/events.patterns" "$build_dir/central$suffix.log" > "$actual"

    if [ $show_trace -eq 1 ]; then
        # 左右を同じ時間軸に並べると、BLE 転送にかかった時間がそのまま読める
        python3 "$HARNESS_DIR/trace.py" \
            "左=$build_dir/peripheral$suffix.log" "右=$build_dir/central$suffix.log"
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
