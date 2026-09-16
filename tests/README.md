# PC 上でキーマップの動作を確認する

実機に書き込まずに、PC 上で torabo-tsuki-lp のファームウェアを動かし、
打鍵に対して何が出力されるかを確認する。

**キーマップもキー配置も実機の定義をそのまま読んでいる**ので、
`config/keymap.keymap` や `boards/shields/` を変更すれば、テスト側も自動的に追従する。

## 2段構え

| | 中身 | 速さ | 使いどころ |
| --- | --- | --- | --- |
| **Tier A** `./tests/run.sh` | セントラル1台(`native_sim`)に両半身の打鍵を流し込む。転送遅延は任意の値で模擬 | 全シナリオで 15 秒 | 普段の確認。キーマップの挙動はこれで足りる |
| **Tier B** `./tests/run-split.sh` | 左右とホスト役(PC 相当)を**別プロセス**で起動し、BabbleSim の仮想2.4GHz電波で実際に BLE 接続させる(`nrf52_bsim`) | 全シナリオ 1〜2 分。キーマップ変更後は2台分のビルドが走り数分〜10分 | BLE 分割の転送そのものや、ホストとの接続性を疑うとき |

シナリオ(打鍵の台本)は両者で共通。同じ操作を両方で流して結果を見比べられる。
実際、遅延を注入していないシナリオでは Tier A と Tier B の出力は一致する
(= Tier A の模擬が実機の分割動作とズレていないことの確認になる)。
違いが出るのは、意図的に大きな転送遅延を入れたシナリオだけ。

## なぜ Tier A で足りるのか

ZMK の分割キーボードでは、ペリフェラル(左)は「押されたキー位置」を
セントラル(右)に送るだけで、レイヤ・コンボ・ホールドタップといった
キーマップの処理はすべてセントラル側で動く。
そのためセントラル 1 台に両半身のキー位置を流し込めば、
キーマップの挙動は実機と同じものが再現できる。

Tier A が再現するもの:

- 66 キー全体の挙動(レイヤ、コンボ、ホールドタップ、マクロ、マウスボタン)
- 左右どちらの半身のキーか(実機と同じマトリクス座標・キー位置番号を使う)
- ペリフェラル → セントラルの転送遅延(`peripheral_latency_ms` で任意に設定)

Tier A が再現しないもの:

- BLE の接続・ペアリング・遅延のゆらぎ(これは Tier B の担当)
- トラックボール / トラックパッドなどのポインティングデバイス
- USB / BLE への実際の HID 送信(ログ上の HID イベントで代替している。
  BLE 側は Tier B のホスト役が実際に受け取って確かめている)
- 電池、ステータス LED、スリープ

`&bt`(Bluetooth ビヘイビア)は PC 上に BLE コントローラが無いため、
Tier A ではどのコマンドが発行されたかをログに出すだけのスタブに差し替えている
(`tests/harness/stubs/`)。Tier B では本物が動く。

## 初回セットアップ

Docker が必要。colima を使っている場合:

```bash
colima start --vm-type=vz --vz-rosetta --cpu 6 --memory 12 --disk 80
```

### Tier A

```bash
./tests/env/setup.sh
```

テスト用コンテナと west ワークスペース(ZMK 本体 + Zephyr)を作る。初回は数十分。
ZMK 本体のリビジョンは `config/west.yml` から自動で取り出すので、
実機ビルドと必ず同じものが使われる。ZMK を更新したらもう一度実行する。

### Tier B (必要になったときだけ)

```bash
./tests/env/setup-split.sh
```

`nrf52_bsim` は 32bit x86 のビルドしか存在しないため、Apple Silicon では
x86_64 コンテナ(Rosetta)＋ QEMU という二重のエミュレーションになる。
そのため Tier A とは**別のワークスペース**が必要で、初回は追加で数 GB / 数十分かかり、
実行も Tier A より大幅に遅い。BabbleSim のビルドもここで行う。

## 使い方

```bash
./tests/run.sh                              # 全シナリオを実行
./tests/run.sh 02-combo-cross-half          # 1 つだけ実行
./tests/run.sh --trace 02-combo-cross-half  # 打鍵と出力の時系列を表示
./tests/run.sh --accept                     # 今の出力を期待値として記録/更新
./tests/run.sh --clean                      # ビルドをやり直す
```

`./tests/run-split.sh` も同じオプションを取る(期待値ファイルだけ別)。

`--trace` の出力例(レイヤタップで左手キーがレイヤ4側に解決される様子):

```
t=   402ms  KEY   R(中央) pos 60 (4,12) 押下  [L0 &lt1 LT_FN ENTER]
t=   603ms  LAYER レイヤ 4 を有効
t=   653ms  KEY   L(周辺) pos 13 (1,1) 押下  [L0 &kp Q]
t=   653ms  HID   press  page 0x07 code 0x56(KEYPAD_MINUS) mods(暗黙 0x00 / 明示 0x00)
t=   765ms  KEY   R(中央) pos 60 (4,12) 離上  [L0 &lt1 LT_FN ENTER]
t=   765ms  LAYER レイヤ 4 を無効
```

`[L0 ...]` はレイヤ0での割当(キーの位置を見分けるための目印)。
実際にどのレイヤで解決されたかは、直前の `LAYER` 行と HID 出力から読む。
上の例では左手の Q の位置がレイヤ4の `KP_MINUS` として出力されている。

Tier B では左右のログが同じシミュレーション時刻で並ぶので、
**ペリフェラルの打鍵がセントラルに届くまでの実際の遅延がそのまま読める**:

```
t=     0ms  左 KEY   L(周辺) pos 17 (1,5) 押下  [L0 &kp T]
t=     6ms  右 SPLIT pos 17 をペリフェラルから受信  [L0 &kp T]
t=     8ms  右 KEY   R(中央) pos 18 (1,5) 押下  [L0 &kp Y]
t=     8ms  右 MOUSE Mouse buttons set to 0x02
```

### ホスト役 (PC 相当)
Tier B は左右の 2 台に加えて、**ホスト役を 1 台**動かしている
(`tests/harness/ble_host/`)。ZMK は使わない素の Zephyr BLE セントラルで、

1. スキャンする
2. HID サービス(0x1812)を広告している相手を見つける
3. 接続する
4. ペアリング(暗号化)まで進める
5. HID レポート特性(0x2A4D)を購読し、届いたレポートを出力する

を行う。各行は `HOST: ` で始まり `/work/build-split/<名前>/host.log` に残る:

```
HOST: advertisement from FD:9E:B2:48:47:39 (random) (rssi -59)
HOST: connected to FD:9E:B2:48:47:39 (random)
HOST: security level 2
HOST: subscribed to 3 report(s)
HOST: report 0x001d (8 bytes): 00 00 14 00 00 00 00 00
```

期待値スナップショットは ZMK 内部のログから作るので、HOG が壊れていても通る。
そのためホスト役については **接続できたか** と **レポートが届いたか** を
別途チェックしており、どちらかが欠けるとシナリオは失敗する。

### 再起動を挟む (`--reboot`)
各機のフラッシュは `/work/build-split/<名前>/flash/{central,peripheral,host}.bin`
に置かれる。`--reboot` を付けると、**同じフラッシュのまま 2 回目を走らせる**:

```bash
./tests/run-split.sh --reboot 01-basic-typing
```

1 回目でペアリングし、2 回目は**ボンドが NVS に残った状態での電源投入**になる。
2 回目のホスト役はスキャンせず、NVS に残った相手へ直接繋ぎにいく
(再起動後のキーボードは指向性広告を出すことがあり、広告データが空なので
スキャンからは見つけられないため)。判定は両方のパスに対して行われ、
スナップショットの比較は 2 回目のログを使う。

NVS に何が残ったかは、フラッシュを直接見れば分かる:

```bash
strings flash/central.bin | grep -E '^(bt|ble)/'
# ble/profiles/0, bt/keys/<相手>, bt/ccc/<相手> など
```

## シナリオの書き方

`tests/scenarios/<名前>/scenario.yaml` を作るだけ。

```yaml
name: 半身をまたぐコンボ(右クリック)
description: |
  何を確かめたいのかを書く。
peripheral_latency_ms: 0   # ペリフェラル(左)側の転送遅延。既定 0 (Tier A のみ)
settle_ms: 400             # 最後の打鍵のあと、出力を待つ時間。既定 400
steps:
  - {at: 0,  press: 17}    # at = ミリ秒(指が動いた時刻)
  - {at: 8,  press: 18}
  - {at: 80, release: 17}
  - {at: 88, release: 18}
```

- `press` / `release` / `tap` のいずれかにキー位置番号を書く
- `tap` は押して離すまでをまとめた書き方(`hold_ms` で長さ指定、既定 30ms)
- キー位置がどちらの半身かは `boards/shields/` の定義から自動判定されるので、
  左右を書く必要はない
- Tier B では転送遅延は実際の BLE 通信が生むため `peripheral_latency_ms` は無視され、
  BLE 接続を待つために起動待ち時間が自動的に長く取られる

新しいシナリオを作ったら `./tests/run.sh --accept <名前>` で期待値ファイル
(`expected.snapshot`)を作り、**その中身が意図通りかを必ず目で確認する**。
以降はその内容と違えば失敗として検出される。

## キー位置番号の調べ方

```bash
python3 tests/harness/show_layout.py     # レイヤ 0
python3 tests/harness/show_layout.py 4   # レイヤ 4
```

左側がペリフェラル(左手)、`|` の右側がセントラル(右手)。

## 構成

| パス | 役割 |
| --- | --- |
| `tests/run.sh` / `tests/run-split.sh` | 実行(ホスト側の入口) |
| `tests/env/` | コンテナと west ワークスペースの用意(`clean.sh` で削除) |
| `tests/harness/layout.py` | シールド定義からキー位置 <-> マトリクス座標を読む |
| `tests/harness/scenario.py` | シナリオ → kscan モックのイベント列(転送遅延・左右分割もここ) |
| `tests/harness/gen_case.py` | Tier A 用のビルド設定を生成 |
| `tests/harness/gen_split_case.py` | Tier B 用(セントラル/ペリフェラル 2台分)を生成 |
| `tests/harness/run_tests.sh` | Tier A のビルド・実行・比較 |
| `tests/harness/run_split_tests.sh` | Tier B のビルド・BabbleSim 実行・比較 |
| `tests/harness/ble_host/` | Tier B のホスト役(PC 相当の最小 BLE セントラル) |
| `/work/build-split/<名前>/flash/` | 各機のフラッシュ(NVS の中身がここに残る) |
| `tests/harness/trace.py` | ログ → 時系列表示 |
| `tests/harness/events.patterns` | ログから期待値比較に使う行を抜き出す規則 |
| `tests/harness/stubs/` | Tier A 専用スタブ(`&bt`) |
| `tests/scenarios/` | シナリオと期待値 |

## 環境を片付ける

ワークスペースは Tier A で約 2.5GB、Tier B で約 3GB を使う。不要になったら:

```bash
./tests/env/clean.sh          # Tier A
./tests/env/clean.sh split    # Tier B
```

## うまくいかないとき

- `docker に接続できません` → colima を起動する
- ビルドエラー → `./tests/env/shell.sh` でコンテナに入り、
  `/work/build-<シナリオ名>.log` (Tier B は `/work/build-split-<名前>-{central,peripheral}.log`) を見る
- 生成されたビルド設定 → `/work/gen/<シナリオ名>/` (Tier B は `/work/gen-split/<名前>/`)
- 実行時のログ全文 → `/work/build/<シナリオ名>/full.log`
  (Tier B は `/work/build-split/<名前>/{central,peripheral,host,phy}.log`)
