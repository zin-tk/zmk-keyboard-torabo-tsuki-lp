# Tier B (BLE 分割エミュレーション) 整備 — 引き継ぎ

作成: 2026-09-16 / 対象: 別セッションで継続する人

## なぜこの作業が要るのか

2026-09-15〜16 に「ZMK v0.4 移行後、ホストと BLE 接続できない」不具合を調査した。
原因究明のたびに実機へ uf2 を焼いてもらう必要が生じ、10 回近く書き込みを依頼して
しまった。根本原因は **Tier B がこの種の問題を一切再現できない構成だったこと**。

Tier B は「キーマップの打鍵結果を確認する」目的で作られており、
BLE の接続性・安定性・設定永続化を検証する作りになっていない。
ここを埋めれば、以降この手の問題は実機に焼かずに切り分けられる。

## このセッションでやったこと (完了)

### 1. watchdog モジュールを Tier B に追加
- `tests/env/gen_manifest.py` の `KEYMAP_MODULE_NAMES` に `zmk-feature-watchdog` を追加
- `tests/harness/gen_split_case.py` の共通 conf に `CONFIG_ZMK_WATCHDOG=y`
- 結果: 起動ログに `Watchdog freeze monitor armed: queue='sysworkq' / 'lowprio_workq'` が出るようになった。
  ただし実機で多発した「起動10秒のフリーズ」は **再現しなかった**

### 2. NVS settings を有効化
- 同 `CONF_TEMPLATE` に `CONFIG_FLASH=y / FLASH_MAP=y / NVS=y / SETTINGS=y / SETTINGS_NVS=y`
  と `SYSTEM_WORKQUEUE_STACK_SIZE=2048` を追加
- それまでは `CONFIG_SETTINGS_NONE=y` で **settings_save_one() が黙って捨てられていた**
- 確認: `CONFIG_SETTINGS_NONE is not set` / `SETTINGS_NVS_SECTOR_COUNT=8` (実機と同数)
- 既存シナリオ `01-basic-typing` は PASS のまま (回帰なし)

## 調査で判明した、整備に使える事実

| 事実 | 出典 |
| --- | --- |
| `nrf52_bsim.dts` は `flash0` と `storage_partition`(512K) を**既に持っている**。Kconfig を立てるだけで NVS が動く | `/workspace/zephyr/boards/native/nrf_bsim/nrf52_bsim.dts:88-100` |
| Zephyr 自身の bsim テストに settings を使う前例が複数ある | `zephyr/tests/bsim/bluetooth/host/gatt/ccc_store/prj.conf`, `host/id/settings/prj.conf` |
| bsim は `-flash=<file> -flash_rm` で**フラッシュ内容をファイルで指定・永続化できる** | 同 `ccc_store/test_scripts/*.sh` |
| 現行 Tier B は既に `-D=3` の 3 台構成 (central / handbrake / peripheral) | `tests/harness/run_split_tests.sh:116-120` |
| Zephyr に bsim 用の BLE central/peripheral 実装が揃っている | `zephyr/tests/bsim/bluetooth/host/{central,adv,gatt,security,privacy,scan}` |

## 残作業 (優先順)

### 1. ホスト役 (4 台目) の追加 ← 最重要

**なぜ**: 現行は左右の分割接続しか見ていない。今回の症状「**ホスト**に BLE 接続できない」を
再現する手段が無い。これが無いと BLE 接続性の問題は永久に実機頼りになる。

**方法**:
- `run_split_tests.sh` の `-D=3` を `-D=4` にし、`-d=3` でホスト役を起動
- ホスト役は Zephyr の `tests/bsim/bluetooth/host/central` 相当を流用するか、
  最小の GATT クライアントを自作する
- 検証したいのは「広告が見えるか → 接続できるか → ペアリングできるか →
  HOG を購読してキー入力が届くか」

**注意**: HID ホストとして完全に振る舞う必要はない。まず「広告を見つけて接続する」だけで
今回の症状は再現できる。

### 2. フラッシュ状態の注入機構

**なぜ**: 「NVS に残った値が原因か」を検証できるようになる。今回の調査では
`ble/active_profile` が範囲外という仮説を立てたが、実機の Studio 画面を見るまで
検証できなかった。

**方法**: `-flash=<file>` でバッキングファイルを与え、既知の状態を作って起動する。
シナリオ側から「この設定が NVS に入っている状態で起動」を指定できるようにする。

### 3. 実機と同じモジュール構成

**現状**: `gen_manifest.py` の `KEYMAP_MODULE_NAMES` は 4 つだけ
(custom-settings / runtime-macro / runtime-combo / watchdog)。

**実機**: 上記 + fast-keymap / input-stream / physical-layout /
runtime-input-processor / settings-rpc / ble-management / device-info /
battery-history / sensor-rotate

モジュールが増えると取得量とビルド時間が増えるので、
「キーマップ用」と「実機フル構成」をプロファイルで切り替えられるようにするのが望ましい。

### 4. 実機 conf との同期

**現状**: `gen_split_case.py` が独自の最小 conf を持ち、実機の
`boards/shields/torabo_tsuki_lp/*.conf` や `snippets/split-central/split-central.conf`
とは別物。**実機と Kconfig がズレると問題が再現しない**(今回まさにそれが起きた)。

理想は実機の conf をそのまま読み込み、bsim で成立しない項目だけを上書きする形。

## 環境の使い方

```bash
# 前提: colima 起動 (サンドボックスからは起動できないので手元で実行してもらう)
colima start --vm-type=vz --vz-rosetta --cpu 6 --memory 12 --disk 80

# DYA 構成のコンテナ/ボリュームを使う場合
export ZMK_TEST_CONTAINER=torabo-tsuki-pc-test-split-dya
export ZMK_TEST_WORKSPACE_VOLUME=torabo-tsuki-zmk-workspace-x86-dya
export ZMK_TEST_WORK_VOLUME=torabo-tsuki-zmk-work-x86-dya

./tests/run-split.sh 01-basic-typing
./tests/run-split.sh --trace 01-basic-typing
```

- ワークスペース: コンテナ内 `/workspace` (zmk, zephyr, BabbleSim, 取得済みモジュール)
- 生成物: `/work/gen-split/<シナリオ>/`、`/work/build-split/<シナリオ>/{central,peripheral,phy}.log`
- リポジトリは `/zmk-config` に bind される

## 既知の罠

1. **`update_workspace()` は `.west` があると manifest を再生成しない**
   (`tests/env/config.sh`)。`gen_manifest.py` を変えたら
   `python3 /zmk-config/tests/env/gen_manifest.py /workspace/manifest/west.yml` を
   手動実行してから `west update` すること。
2. **コンテナのマウント先は作成時に固定される**。別のワークツリーから使うときは
   コンテナを作り直す (`ensure_container` は running なら何もしない)。
3. **スクラッチパッド (`/private/tmp/...`) は colima の VM にマウントされていない**。
   `-v` で渡せないので `docker cp` を使う。
4. **`docker exec` をバックグラウンド実行すると中身が失敗しても成功扱いになる**。
   必ずログに `EXIT=$?` を書かせて確認する。
5. Tier B 固有の 2 点 (`CONFIG_BT_SETTINGS=y` 必須、`zmk_behavior_local_id_map` の
   const 外し) は `tests/README.md` と `tests/env/patch-zmk-native.sh` を参照。

## 本体の不具合について (未解決・参考情報)

整備が目的なので詳細は追わなくてよいが、同じ仮説を再検証して時間を溶かさないために
記録しておく。

### 症状
- v0.3 では BLE で使えていた。v0.4 移行後、**ホストと BLE 接続できない**
- USB 給電中は BLE のペアリングも接続も正常にできる
- USB 給電が無い状態 (電源投入のみ含む) では繋がらない。ホストの一覧にも出ない
- 左右の分割接続は成立している (両半身とも入力できる)
- 右の電池を新品に交換しても変化なし

### 反証済みの仮説 (再検証不要)

| 仮説 | 反証根拠 |
| --- | --- |
| 電圧/電池 | non-lipo モジュールが v0.3 と **md5 完全一致**、DTS もバイト同一、実機のバッテリー残量は 0% でない |
| activity の sleep_ms 永続化 | 実機 Studio の Settings が既定値 (アイドル30秒/スリープ150分) |
| `ble/active_profile` 範囲外 | 実機 Studio の Connection タブでアクティブ=0 を確認 |
| ペアリング拒否 (`profile_is_open`) | USB 中はペアリングできている |
| 起動時フラッシュ占有 | 起動時の NVS 消去は 0〜1 回。10 秒に必要な量の 1/37 |
| `zmk_pm_suspend_devices()` ハング | 呼び出し元 4 箇所、起動 5 秒以内に到達する経路なし |
| `BT_CTLR_PERIPHERAL_RESERVE_MAX` | 接続確立の機序を作れない (不安定化の要因止まり) |
| input-stream の Known issue | Studio 切断時限定。電源投入時を説明できない |
| `usb.c` / `hog.c` | v0.3 と **差分ゼロ** |
| `endpoints.c` | 既定 transport が BLE→USB に逆転しているが、フォールバック実装は正常 |
| 広告オプション変更 | `BT_LE_ADV_OPT_CONNECTABLE|ONE_TIME` → `BT_LE_ADV_OPT_CONN` は**ビット値まで等価** |
| HFCLK/HFXO の起動差 | 定数・クロック設定・DTS が v0.3/v0.4 で完全同一 |
| DCDC 無効化 | v0.4 も devicetree 経由で有効 (`soc.c:35-37`) |

### 確認済みの重要事実
- **USB/VBUS 状態で BLE の広告・スキャン・ペアリングを分岐させるコードは、ZMK 本体にも
  全 DYA モジュールにも 1 行も存在しない** (全 grep 済み)
- `ble.c` の v0.3→v0.4 差分は 3 箇所のみで、すべて等価
- v0.4 で増えた常時消費電流は µA オーダー (無線時の mA に対し 0.1% 未満)
- `CONFIG_BT_CTLR_TX_PWR_PLUS_8=y` は v0.3/v0.4 同一 (ピーク電流は増えていない)

### 次にやるべき測定 (実機、費用ゼロ)
1. **電池のみで電源投入し、右半身のステータス LED を 30 秒観察**。
   `ZMK_STATUS_LED_ADVERTISING=y` / `ADVERTISING_INTERVAL_MS=3000` は
   v0.3/v0.4 同一で、未接続かつ広告中なら 3 秒周期で 2 回点滅する。
   点滅しないなら広告状態に到達していない。
2. **スマホの BLE スキャナ (nRF Connect 等) で、電池のみの右半身が見えるか**。
   USB 給電時との RSSI 比較が最も情報量が多い。
3. **Studio のバッテリー履歴で小さい timestamp のエントリ数を数える**。
   timestamp は起動からの秒数で、毎起動 1 エントリが強制記録されるため、
   **本数 = 再起動回数**になる。

### 未解決の矛盾
ソフト側に「USB 給電の有無で BLE の可否が変わる」を説明できる候補が 1 つも残っていない。
残る可能性は (a) v0.3 でも同じだった (電池単体での検証が不十分だった)、
(b) ファーム以外が並行して変わった (電池ホルダ接触・昇圧モジュール・はんだ)、
(c) v0.4 が既存のハードマージンを食い潰した (定量できず不明)。
**上記 1〜3 の測定でここを切り分けるのが先**。

## 現在の未コミット変更

```
tests/env/gen_manifest.py        +3行  (watchdog を取得対象に追加)
tests/harness/gen_split_case.py +21行  (CONFIG_ZMK_WATCHDOG=y と NVS settings 一式)
```

どちらも `01-basic-typing` が PASS することを確認済み。
