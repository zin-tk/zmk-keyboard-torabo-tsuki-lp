#!/usr/bin/env sh

# Generate a keymap-drawer YAML and SVG for torabo-tsuki-lp.
# Run this from the repository root or from this directory.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

mkdir -p "$REPO_ROOT/keymap-drawer"

keymap parse -z "$REPO_ROOT/config/keymap.keymap" > "$REPO_ROOT/keymap-drawer/torabo-tsuki-lp.yaml"
keymap draw -j "$REPO_ROOT/config/info.json" -l LAYOUT "$REPO_ROOT/keymap-drawer/torabo-tsuki-lp.yaml" > "$REPO_ROOT/keymap-drawer/torabo-tsuki-lp.svg"

echo "Generated: $REPO_ROOT/keymap-drawer/torabo-tsuki-lp.svg"