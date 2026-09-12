#!/usr/bin/env bash
#
# BLE 分割エミュレーション環境(Tier B: nrf52_bsim + BabbleSim)のセットアップ。
#
# nrf52_bsim は 32bit x86 のビルドしか無いため、Apple Silicon では
# Rosetta 経由の x86_64 コンテナを使う。そのため Tier A とは別の
# ワークスペースになり、初回は追加で数 GB / 数十分かかる。
set -euo pipefail

export ZMK_TEST_PROFILE=split
source "$(dirname "${BASH_SOURCE[0]}")/config.sh"

require_docker
ensure_container

echo "west ワークスペース(x86_64)を準備します"
docker exec "$CONTAINER" bash -euc '
    cd /workspace
    if [ ! -d /workspace/.west ]; then
        python3 /zmk-config/tests/env/gen_manifest.py /workspace/manifest/west.yml
        west init -l manifest
    fi
    # BabbleSim 本体は既定では取得されないグループに入っている
    west config manifest.group-filter -- +babblesim
    west update --fetch-opt=--filter=tree:0
    west zephyr-export
'

echo "BabbleSim をビルドします(並列にすると依存順が崩れるため逐次実行)"
docker exec "$CONTAINER" bash -euc 'cd /workspace/tools/bsim && make everything'

echo
echo "準備完了。BLE 分割エミュレーションを実行するには:"
echo "  ./tests/run-split.sh"
