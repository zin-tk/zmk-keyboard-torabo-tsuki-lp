#!/usr/bin/env sh

# Generate a keymap-drawer YAML and SVG for torabo-tsuki-lp.
# Run this from the repository root or from this directory.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

mkdir -p "$REPO_ROOT/keymap-drawer"

# keymap-drawer は ZMK 標準の zmk,combos しか読まないため、runtime combo の
# 既定値ノードを一時的に読み替えてから解析させる (出力は移行前と同じになる)
# keymap-drawer は解析元のファイル名をキーボード名に使うので、
# 一時ディレクトリを作って中身は keymap.keymap のまま置く
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/torabo-tsuki-drawer.XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT
TMP_KEYMAP="$TMP_DIR/keymap.keymap"
sed -e 's/runtime_combo_defaults {/combos {/' \
    -e 's/"cormoran,runtime-combo-defaults"/"zmk,combos"/' \
    "$REPO_ROOT/config/keymap.keymap" > "$TMP_KEYMAP"

keymap parse -z "$TMP_KEYMAP" > "$REPO_ROOT/keymap-drawer/torabo-tsuki-lp.yaml"
keymap draw -j "$REPO_ROOT/config/info.json" -l LAYOUT "$REPO_ROOT/keymap-drawer/torabo-tsuki-lp.yaml" > "$REPO_ROOT/keymap-drawer/torabo-tsuki-lp.svg"

echo "Generated: $REPO_ROOT/keymap-drawer/torabo-tsuki-lp.svg"