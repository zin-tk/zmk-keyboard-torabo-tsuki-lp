[torabo-tsuki LP](https://github.com/sekigon-gonnoc/torabo-tsuki-lp)用のZMKファームウェア

* `_central` がついている uf2 をトラックボールがついている方に、`_peripheral` を反対側に書き込んでください
* キーマップは keymap-editor および [DYA Studio](https://studio.dya.cormoran.works) で編集できます

## DYA Studio

ZMK Studio 互換の Web UI で、キーマップに加えてマクロ・コンボ・トラックボール・
BLE 接続・各種設定を実機に書き込まずに変更できます。
Chrome / Edge で USB (Web Serial) または Bluetooth (Web Bluetooth) 接続します。

ロック (`CONFIG_ZMK_STUDIO_LOCKING`) は無効にしてあるので、接続すればそのまま編集できます。
ただし BLE 接続時は、BT レイヤーの `&studio_unlock` を押してキーボードを
ダイレクトアドバタイジング状態にしないとブラウザから見つけられません。

有効にしているタブと機能:

| タブ | 使えること |
| --- | --- |
| Keymap | キー割り当て・レイヤー編集、押下キーのリアルタイム表示、初期キーマップとの差分 |
| Macro / Combo | マクロとコンボの作成・編集。キーマップの既定コンボもここから編集できる |
| Trackball | ポインタ感度・回転・スクロール・軸スナップ・有効レイヤー・自動マウスレイヤー |
| Connection | BLE プロファイルの命名・切替・解除 |
| Settings | アイドル / ディープスリープ時間、詳細設定 |
| Troubleshooting | バッテリ、ファームウェア情報、稼働時間、再起動要因 (Watchdog) |

既定のコンボは `config/keymap.keymap` の `runtime_combo_defaults` に書いてあり、
書き込み直後から有効です。Web で変更するとそちらが優先され、Reset で初期値に戻ります。

トラックボールのセンサーは PAW3222 で、DYA の PMW3610 用ドライバ RPC には対応しません。
そのため CPI などセンサー固有の設定は Web からは変更できず、
`zmk-module-runtime-input-processor` が扱う感度・回転・スクロール側で調整します。

構成の詳細は [DYA Studio 開発者ガイド](https://dya-studio-dev.cormoran707.workers.dev/developer-guide) を参照してください。

## ビルド構成

| artifact | 用途 |
| --- | --- |
| `right_central` / `left_peripheral` | 標準構成 (右トラックボール) |
| `right_central_trackpad` / `left_peripheral_trackpad` | 左に mini トラックパッドを付ける構成 |
| `settings_reset` | 設定消去用 |

`_trackpad` 付きは**左右セットで書き込んでください**。

## トラックパッド

左ペリフェラルの J101 に sekigon 氏の mini トラックパッド (IQS7211E) を接続する構成です。
ドライバの scroller-mode を使い、指の移動をそのままホイールとして送ります。

* 縦スクロール専用です (横スクロール帯は無効にしてある)
* どのレイヤーでもスクロールします。キーマップの設定は不要です
* 1 本指タップで左クリックになります。2 本指タップは無効です
* スクロール速度は DYA Studio の Trackball タブの `trackpad` で変更できます (既定 1/6)
* Windows (WIN レイヤー = BT1/BT2) のときだけ、さらに `tp_win` の倍率が掛かります (既定は等倍)
* スクロールの向きは DYA Studio からは変更できません。
  逆なら `snippets/input-trackpad-mini/input-trackpad-mini.overlay` に `v-invert;` を足して再ビルドします

## PC でのキーマップ確認

実機に書き込まずに打鍵結果を確認できます。詳細は [tests/README.md](tests/README.md)。

```bash
./tests/env/setup.sh   # 初回のみ
./tests/run.sh
```
