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
| `right_central_encoder` / `left_peripheral_encoder` | 左にロータリーエンコーダを付ける構成 |
| `torabo_tsuki_lp_double_ball_*` | 左右両方にトラックボールを付ける構成 |
| `settings_reset` | 設定消去用 |

`_encoder` 付きは**左右セットで書き込んでください**。
セントラル側にもセンサーノードが必要で、片側だけだとセンサー通知を受けた瞬間に
リセットループになります。

## ロータリーエンコーダ

左ペリフェラルの J101 (トラックボール / トラックパッド用端子) に EC11 互換
エンコーダを接続する構成です。SPI0 と I2C0 を止めて GPIO を使うため、
この構成では左側にトラックボール / トラックパッドは載せられません。

| 信号 | ピン |
| --- | --- |
| ENC_A | P0.16 (SDIO) |
| ENC_B | P0.19 (MOTION) |
| SW | P0.18 (SCLK)、共通端子は P0.20 (CS) |

* 回転の割り当ては DYA Studio からレイヤーごとに変更できます (既定は音量 +/-)
* 押し込みスイッチはキー位置 62 (最下段の右から 4 番目) に載っているので、
  普通のキーと同じように DYA Studio から割り当てられます

## PC でのキーマップ確認

実機に書き込まずに打鍵結果を確認できます。詳細は [tests/README.md](tests/README.md)。

```bash
./tests/env/setup.sh   # 初回のみ
./tests/run.sh
```
