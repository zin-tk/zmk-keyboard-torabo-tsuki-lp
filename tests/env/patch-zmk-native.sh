#!/usr/bin/env bash
#
# PC テスト用ワークスペースの ZMK に、ネイティブビルド固有の不具合修正を当てる。
# コンテナ内で実行する。west update のたびに上書きされるので、
# setup スクリプトから毎回呼ぶ (適用済みなら何もしない)。
#
# 実機ビルドには一切影響しない。config/west.yml の ZMK リビジョンは変えていない。
set -euo pipefail

WORKSPACE=${ZMK_WORKSPACE:-/workspace}
HEADER="$WORKSPACE/zmk/app/include/drivers/behavior.h"

# --- zmk_behavior_local_id_map が読み取り専用セクションに置かれる問題 ---
#
# エントリが const 付きで定義されているため .rodata 相当に入るが、ZMK は
# behavior_local_id_init() でここへ書き込む。実機(ARM)ではリンカスクリプトの
# ITERABLE_SECTION_RAM が RAM へ配置するので問題にならないが、
# native_sim / nrf52_bsim では読み取り専用セグメントのままになり SIGSEGV する。
#
# 上流の修正 (未マージ):
#   https://github.com/cormoran/zmk/tree/fix/local-id-map-writable-section
#   "fix: place behavior local-id map entries in a writable section"
#
# CONFIG_ZMK_BEHAVIOR_LOCAL_IDS は runtime combo / macro が select するため、
# キーマップがこれらを使う以上この経路は必ず通る。
if grep -q 'static const STRUCT_SECTION_ITERABLE(zmk_behavior_local_id_map' "$HEADER"; then
    sed -i 's/static const STRUCT_SECTION_ITERABLE(zmk_behavior_local_id_map/static STRUCT_SECTION_ITERABLE(zmk_behavior_local_id_map/' "$HEADER"
    echo "patched: behavior local-id map を書き込み可能なセクションへ ($HEADER)"
else
    echo "skip: behavior local-id map の修正は適用済み"
fi
