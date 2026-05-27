#!/usr/bin/env sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

mkdir -p "$REPO_ROOT/keymap-drawer"

keymap parse -z "$REPO_ROOT/config/keymap.keymap" > "$REPO_ROOT/keymap-drawer/torabo-tsuki-lp.yaml"

REPO_ROOT="$REPO_ROOT" python3 <<'PY'
import json, os, re
from pathlib import Path

repo_root = Path(os.environ['REPO_ROOT'])

# Build the S physical layout JSON from the DTS coordinates.
text = (repo_root / 'boards/shields/torabo_tsuki_lp/torabo_tsuki_lp_layouts.dtsi').read_text()
start = text.index('physical_layout_s: physical_layout_0')
start = text.index('keys', start)
end = text.index('};', start)
block = text[start:end]
coords_raw = []
for m in re.finditer(r'<&key_physical_attrs\s+\d+\s+\d+\s+(-?\d+)\s+(-?\d+)', block):
    x, y = map(int, m.groups())
    coords_raw.append({
        'row': int(round(y / 100.0)),
        'col': int(round(x / 100.0)),
        'x': x / 100.0,
        'y': y / 100.0,
    })
coords = coords_raw

# Parse the original keymap YAML
parsed = (repo_root / 'keymap-drawer/torabo-tsuki-lp.yaml').read_text()
start = parsed.index('layers:')
lines = parsed[start:].splitlines()
current = None
layers = {}
for line in lines:
    if line.startswith('  ') and not line.startswith('  - ') and line.strip().endswith(':'):
        current = line.strip()[:-1]
        layers[current] = []
    elif line.startswith('  - '):
        layers[current].append(line.strip()[2:].strip())

mac_values = layers.get('mac') or layers.get('MAC') or layers.get('Mac')
if mac_values is None:
    raise SystemExit('mac layer not found in parsed YAML')

# positions mapping from DTS
def find_last_positions(name):
    blocks = []
    for m in re.finditer(r'%s\s*{[^}]*positions\s*=\s*<([^>]+)>' % re.escape(name), text, re.S):
        blocks.append([int(x) for x in re.findall(r'-?\d+', m.group(1))])
    if not blocks:
        raise SystemExit(f'{name} positions not found')
    return blocks[-1]

s_positions = find_last_positions('position_map_s_1')
l_positions = find_last_positions('position_map_l_1')
if len(s_positions) != len(l_positions):
    raise SystemExit('position_map_s_1 and position_map_l_1 lengths differ')

ordered_indices = [None] * len(coords_raw)
for complete_pos, s_index in enumerate(s_positions):
    if 0 <= s_index < len(coords_raw):
        if ordered_indices[s_index] is not None:
            raise SystemExit(f'duplicate S index {s_index} in position_map_s_1')
        ordered_indices[s_index] = l_positions[complete_pos]
if any(i is None for i in ordered_indices):
    missing = [idx for idx, v in enumerate(ordered_indices) if v is None]
    raise SystemExit(f'Missing S mapping for indices: {missing}')
coords = coords_raw

json_path = repo_root / 'keymap-drawer/torabo-tsuki-lp-s.json'
json_path.write_text(json.dumps({
    'id': 'torabo-tsuki-lp-s',
    'name': 'torabo-tsuki-lp S',
    'layouts': {'LAYOUT_S': {'layout': coords}},
}, indent=2))

# sanity check
max_index = max(ordered_indices)
for layer, values in layers.items():
    if len(values) <= max_index:
        raise SystemExit(f'layer {layer} has {len(values)} entries, need index {max_index} available')

out_path = repo_root / 'keymap-drawer/torabo-tsuki-lp-s.yaml'
with out_path.open('w') as out:
    out.write('layout: {qmk_keyboard: torabo-tsuki-lp-s}\n')
    out.write('layers:\n')
    for layer, values in layers.items():
        out.write(f'  {layer}:\n')
        for i in ordered_indices:
            out.write(f'  - {values[i]}\n')
PY

keymap draw -j "$REPO_ROOT/keymap-drawer/torabo-tsuki-lp-s.json" -l LAYOUT_S "$REPO_ROOT/keymap-drawer/torabo-tsuki-lp-s.yaml" > "$REPO_ROOT/keymap-drawer/torabo-tsuki-lp-s.svg"

echo "Generated: $REPO_ROOT/keymap-drawer/torabo-tsuki-lp-s.svg"
