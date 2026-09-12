#!/usr/bin/env bash
#
# コンテナ内で動くテスト本体。
#   1. シナリオ -> ZMK_CONFIG 一式を生成
#   2. native_sim 向けにビルド
#   3. 実行してログを採取
#   4. 期待値(expected.snapshot)と比較
#
# 通常はホスト側の tests/run.sh から呼ばれる。
set -uo pipefail

REPO_ROOT=${ZMK_CONFIG_ROOT:-/zmk-config}
WORKSPACE=${ZMK_WORKSPACE:-/workspace}
WORK_DIR=${ZMK_TEST_WORK:-/work}
HARNESS_DIR="$REPO_ROOT/tests/harness"
SCENARIOS_DIR="$REPO_ROOT/tests/scenarios"
BOARD=native_sim//zmk_test_mock
RUN_TIMEOUT_SEC=120

export PYTHONPATH="$HARNESS_DIR"
# トレース表示でキー名を引くため(見つからなければ名前なしで続行)
export ZMK_APP_DIR="$WORKSPACE/zmk/app"

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

if [ ${#scenario_dirs[@]} -eq 0 ]; then
    echo "シナリオが1つもありません: $SCENARIOS_DIR" >&2
    exit 2
fi

failed=0
for scenario_dir in "${scenario_dirs[@]}"; do
    name=$(basename "$scenario_dir")
    gen_dir="$WORK_DIR/gen/$name"
    build_dir="$WORK_DIR/build/$name"
    expected="$scenario_dir/expected.snapshot"

    printf '\n=== %s ===\n' "$name"

    [ $clean -eq 1 ] && rm -rf "$gen_dir"
    if ! python3 "$HARNESS_DIR/gen_case.py" "$scenario_dir/scenario.yaml" "$gen_dir"; then
        echo "FAIL: $name (シナリオの生成に失敗)"
        failed=1
        continue
    fi

    build_log="$WORK_DIR/build-$name.log"
    if ! (cd "$WORKSPACE" && west build -s "$WORKSPACE/zmk/app" -d "$build_dir" -b "$BOARD" \
            "${pristine_arg[@]+"${pristine_arg[@]}"}" -- \
            -DZMK_CONFIG="$gen_dir" \
            -DZMK_EXTRA_MODULES="$HARNESS_DIR/stubs" \
            -DCONFIG_ASSERT=y) > "$build_log" 2>&1; then
        echo "FAIL: $name (ビルド失敗)"
        tail -30 "$build_log"
        failed=1
        continue
    fi

    executable="$build_dir/zephyr/zmk.exe"
    if [ ! -x "$executable" ]; then
        echo "FAIL: $name (実行ファイルが生成されていません: $executable)"
        failed=1
        continue
    fi

    full_log="$build_dir/full.log"
    timeout "$RUN_TIMEOUT_SEC" "$executable" > "$full_log" 2>&1
    run_status=$?
    if [ $run_status -eq 124 ]; then
        echo "FAIL: $name (${RUN_TIMEOUT_SEC}秒でタイムアウト。settle_ms が長すぎないか確認)"
        failed=1
        continue
    fi

    actual="$build_dir/actual.snapshot"
    sed -e 's/.*> //' "$full_log" | sed -n -f "$HARNESS_DIR/events.patterns" > "$actual"

    if [ $show_trace -eq 1 ]; then
        python3 "$HARNESS_DIR/trace.py" "$full_log"
        echo
    fi

    if [ ! -f "$expected" ]; then
        if [ $accept -eq 1 ]; then
            cp "$actual" "$expected"
            echo "NEW:  $name (expected.snapshot を作成)"
            cat "$expected"
            continue
        fi
        echo "FAIL: $name (expected.snapshot がありません。--accept で作成できます)"
        echo "--- 今回の出力 ---"
        cat "$actual"
        failed=1
        continue
    fi

    if diff -u "$expected" "$actual"; then
        echo "PASS: $name"
    elif [ $accept -eq 1 ]; then
        cp "$actual" "$expected"
        echo "UPDATED: $name (expected.snapshot を更新)"
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
