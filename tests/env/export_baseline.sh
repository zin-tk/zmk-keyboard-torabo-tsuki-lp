#!/usr/bin/env bash
#
# 比較用のベースライン(過去のリビジョン)をディレクトリに展開する。
#
#   ./tests/env/export_baseline.sh <git ref> <展開先>
#
# Tier B で「このリビジョンなら動いていたのか」を試すために使う。
# git worktree ではなく git archive を使うのは、共有される worktree/stash の
# 状態に触らないため。展開先は消しても構わない。
set -euo pipefail

if [ $# -ne 2 ]; then
    echo "使い方: $0 <git ref> <展開先>" >&2
    exit 2
fi

ref=$1
out=$2
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)

# ディレクトリごと作り直すとコンテナの bind マウントが古い inode を指したままに
# なるので、入れ物は残して中身だけ入れ替える。
mkdir -p "$out"
find "$out" -mindepth 1 -delete
git -C "$repo_root" archive "$ref" | tar -x -C "$out"

echo "展開しました: $ref -> $out"
echo "  ZMK: $(grep -A2 'name: zmk$' "$out/config/west.yml" | grep revision: | head -1 | sed 's/.*revision: //')"
