# torabo-tsuki-lp 水平ロータリーエンコーダ実装計画

**作成日**: 2026年5月27日  
**最終更新**: 2026年5月28日  
**ステータス**: 🟢 技術検証完了 / 実装フェーズ開始準備完了  
**目的**: 左側(Peripheral) FCC端子に接続した水平ロータリーエンコーダ（EC11互換、LiSM基板）をfirmwareで認識し、キー入力に変換する

---

## 0. 追加方針と前提

- 左側Peripheralは**エンコーダ専用**とする。トラックボール/トラックパッドは左側では不要であり、SPI0/I2C0の排他利用は許容する。
- 右側Centralは従来通りトラックボールを動作させるため、SPI0実装は維持する。
- 左側ではSPI0/I2C0を利用しない構成とし、必要であればこれらを無効化してGPIOをエンコーダに再割り当てする。
- `build.yaml`の`left_peripheral`ビルド構成は、左側Peripheralに余計なpointing deviceを含まない基礎構成として活用できる。

---

## 1. 技術課題の検討

### 1.1 ハードウェア・ピンアサイン課題

**課題**：
- 左側(Peripheral)のFCC端子にエンコーダを接続するが、FCC端子のピン配置が不明確
- ユーザーが指定したピンアサイン情報（GPIO 18, 16, 20）は、左側がトラックボール/トラックパッド未使用ならばエンコーダ用に再利用可能である

**詳細分析**：
```
LiSMエンコーダ基板のピン配置（実測確認済み）：
※ エンコーダ基板はJ101コネクタに対してピン順が逆向きに接続されている

エンコーダ基板ピン  →  J101 コネクタピン  →  torabo-tsuki-lp左側 GPIO
1 (GND)         →  6 (VCC)         →  ※ 要確認
2 (VCC 3.3V)    →  5 (CS)          →  GPIO0.20 ✅ （ENC_A 動作確認済み）
3 (ENC_A)       →  4 (MOTION)      →  GPIO0.19 ✅ （ENC_B 動作確認済み）
4 (ENC_B)       →  3 (SDIO)        →  GPIO0.16 （SW候補）
5 (SW)          →  2 (SCLK)        →  GPIO0.18 （SW候補）
6 (ID/NC)       →  1 (GND)         →  nRF52840 GND

実装上の注意：
- J101コネクタへの接続が逆向きのため、A/BはCS/MOTIONピン（GPIO0.20/0.19）に接続
- SPI0/I2C0はencoder-left.overlayで無効化済み
- SWのGPIOはGPIO0.16またはGPIO0.18（未確定、動作確認中）
```

**リスク評価**: ✅ 解決済み - 実機動作確認済み

---

### 1.2 Peripheral → Central への入力送信課題

**課題**：
- LiSmではセンサーフレームワーク（`zmk,keymap-sensors`）を使用
- torabo-tsuki-lpはトラックボール/タッチパッド入力を`input-split`で送信
- Peripheral側でのエンコーダイベント送信メカニズムが確立していない

**詳細分析**：
```
torabo-tsuki-lpの入力送信メカニズム（現在）：

Left（Peripheral）          Right（Central）
─────────────────────────────────────────────
キーマトリクス          →  BLE分割キーボード
（GPIO matrix）             フレームワーク
   ↓                       ↑
トラックパッド          →  input-split
(I2C IQS7211E)             仮想デバイス
                           (pointing_device_split)

課題：
- セッサーフレームワーク（エンコーダ）にはZMKの標準`input-split`サポートがない
  可能性が高い
- トラックボール（pointing device）とエンコーダ（sensor）は異なる入力カテゴリー
- Peripheralで生成されたセンサーイベント→Centralへの送信が未実装

Peripheral側実装上の課題：
- Peripheral設定では通常`CONFIG_ZMK_SPLIT_ROLE_PERIPHERAL=y`のみ
- Peripheralでセッサーを処理してイベント送信する仕組みが必要
- または、Peripheralの生センサー信号をCentralへ送信する仕組みが必要
```

**リスク評価**: ⚠️⚠️ 非常に高 - ZMK split対応が標準機能ではない可能性

---

### 1.3 入力フレームワークの統合課題

**課題**：
- torabo-tsuki-lpは`input-listener`パイプライン（Input Processor）でトラックボール/タッチパッド入力を処理
- エンコーダはZMKセンサーフレームワークで処理される異なるシステム
- 2つのシステムを共存させる方法を検討が必要

**詳細分析**：
```
torabo-tsuki-lpのInput Processor パイプライン：

pointing_device(PAW3222 SPI)
  └─→ input-processors
       ├─ zip_xy_transform
       ├─ zip_xy_scaler
       └─ zip_xy_to_scroll_mapper (Layer5時)

vs.

LisMのセンサーフレームワーク：

GPIO(EC11)
  └─→ EC11ドライバ
       └─→ zmk,behavior-sensor-rotate-var
            └─→ keymap-sensors binding

統合課題：
1. エンコーダはInput Processorパイプラインには適さない
   （motion vectorではなくpulse event）
2. Peripheralでセンサーイベント生成→Central送信が必要
3. キーマップレベルでの統合（レイヤー別バインディング）
```

**リスク評価**: ⚠️⚠️ 高 - フレームワーク統合設計が必要

---

### 1.4 キーマップ拡張課題

**課題**：
- torabo-tsuki-lpのキーマップ（`config/keymap.keymap`）にはエンコーダ定義がない
- エンコーダセンサーバインディングを追加する必要がある

**詳細分析**：
```
torabo-tsuki-lpのキーマップ現状：
- 8レイヤー構成（mac, win, mouse, symbol, 3, scroll, function, BT）
- エンコーダ関連定義なし（`compatible = "zmk,behavior-sensor-rotate"`なし）
- セッサー定義なし（`keymap-sensors`ブロックなし）

必要な拡張：
1. エンコーダ用ビヘイビア定義
   - LisMの`sensor_rotate_var`を参考に実装
   - または標準`sensor_rotate`を使用

2. センサーバインディング定義
   - `&sensors`ブロックにバインディング追加
   - レイヤーごとに異なる動作を割り当て

3. レイヤー別バインディング
   例：
   - Layer 0/1: キー入力（UP→"A", DOWN→"B"）
   - Layer 2（mouse）: スクロール
   - Layer 3（symbol）: 音量制御
```

**リスク評価**: ⚠️ 中 - 相対的にシンプル（LiSMの実装を参考可）

---

### 1.5 モジュール実装スタイル差異課題

**課題**：
- LiSMはDTSベースの標準ZMK実装
- torabo-tsuki-lpはカスタムドライバ（Input Processor）中心
- 単純なポーティングでは問題が発生する可能性

**詳細分析**：
```
実装スタイル比較：

LiSM実装:
├─ DTS: lism.dtsi で encoder デバイス定義
├─ CONFIG: non_trackball.conf で CONFIG_EC11=y
├─ キーマップ: sensor_rotate-var ビヘイビア定義
└─ west.yml: 標準ZMKのみ

torabo-tsuki-lp実装:
├─ DTS: torabo_tsuki_lp.dtsi でmtrix/pointing_listener定義
├─ Custom Drivers: zmk-driver-paw3222, zmk-driver-iqs7211e
├─ Custom Input Processors: scroll-inertia等
├─ Custom Behaviors: mini_trackpad用初期化
└─ west.yml: カスタムモジュール依存

ポーティング時の留意点：
1. DTSでのエンコーダ定義は直接追加可能（標準準拠）
2. 左側Peripheralでの実装は標準split機能の限界に直面
3. カスタム入力処理パイプラインとの共存検証が必要
4. board.c（Central専用のBT/電力管理）の影響範囲確認
```

**リスク評価**: ⚠️ 中 - 既存アーキテクチャへの影響有り

---

### 1.6 Peripheral CONFIG設定課題

**課題**：
- Peripheralではセンサー処理が実装されているか不明確
- CONFIG設定の最小化/最適化が必要

**詳細分析**：
```
Peripheral設定の状況：
- 現在: torabo_tsuki_lp_left.conf は左側Peripheral向けで、input-trackball/input-splitを含まない
- 左側を専用Peripheral化する場合、SPI0/I2C0は無効化可能な状態
- left_peripheralビルドプロファイルは、まさに追加デバイス無しの基礎構成

Peripheral側でエンコーダを動作させるための最小CONFIG：
1. エンコーダドライバ有効化:
   - CONFIG_EC11=y
   - CONFIG_EC11_TRIGGER_GLOBAL_THREAD=y
   - CONFIG_SENSOR=y

2. Split BLE通信:
   - CONFIG_ZMK_SPLIT_BLE_CENTRAL_BATTERY_LEVEL_PROXY=y
   - CONFIG_ZMK_SPLIT_BLE_CENTRAL_BATTERY_LEVEL_FETCHING=y

3. 左側専用化（SPI/I2C競合回避）:
   - &spi0 { status = "disabled"; }  
   - &i2c0 { status = "disabled"; }

この構成でPeripheral側がセンサー入力をキー入力に変換し、
標準Splitのキーイベント通信を使って送信する形式が現実的である。
```

**リスク評価**: ✅ 低 - Peripheral側センサー処理は標準機能

---

### 1.7 ダブルトラックボール実装との相違課題

**課題**：
- 既存のダブルトラックボール実装（右SPI + 左I2C）が参考になるが、
  エンコーダ（センサー）は異なる仕組みのため単純な流用不可

**詳細分析**：
```
ダブルトラックボール実装:
- 右側（Central）: PAW3222 SPI → pointing_device直結
- 左側（Peripheral）: IQS7211E I2C → input-split仮想デバイス
- 統合: input-listener パイプラインで両者を統一

エンコーダ実装（提案）:
- 右側（Central）: N/A（トラックボール優先）
- 左側（Peripheral）: EC11 GPIO → ??? 
- 統合方法: センサー送信メカニズムの確立が必須

相違点：
1. pointing_deviceは標準ZMKで`input-split`サポートあり
2. センサーの`input-split`サポートは不明確
3. ダブルトラックボール実装はtouch/motionデータ送信
4. エンコーダは離散イベント（pulse）送信が必要

単純なすげ替えでは、Peripheral→Central通信メカニズムが
構築されないリスク
```

**リスク評価**: ⚠️ 高 - 相互参考は可だが、新規実装が必要

---

## 2. 対応方針（推奨）

### 実現可能性評価

- **可能性は高い**: 左側を専用Peripheralとして扱い、SPI0/I2C0を無効化してGPIOをエンコーダに再割り当てする方向は、現在のtorabo-tsuki-lp構成と整合する。
- **最大の不確定要素**: エンコーダ基板の実際のピン割り当てと、A/B信号がどのコネクタピンに出るか。
- **ポイント**: `build.yaml`の`left_peripheral`構成は、エンコーダ専用Peripheralの出発点として適切。
- **中央側への影響**: 中央側は`split-central`構成を維持し、トラックボール実装をそのまま継続できる。

### 方針1: **Peripheral側でセンサーイベント→キー入力に変換してからCentralへ送信**（推奨）

```
実装フロー：
┌─────────────────────────────────────────────────────────┐
│ Left（Peripheral）                                      │
├─────────────────────────────────────────────────────────┤
│ GPIO(EC11) → EC11ドライバ → Pulse Event               │
│              ↓                                          │
│         Peripheral側で                                  │
│         sensor-rotate-varビヘイビア                      │
│              ↓                                          │
│         キー入力(A, B等)生成                             │
│              ↓                                          │
│         標準ZMK Splitキー送信                           │
└─────────────────────────────────────────────────────────┘
                      ↓ BLE
┌─────────────────────────────────────────────────────────┐
│ Right（Central）                                        │
├─────────────────────────────────────────────────────────┤
│ Splitキーボード受信 → キーマップ処理 → 出力             │
└─────────────────────────────────────────────────────────┘
```

**メリット**：
- ✅ 既存のSplit通信機構をそのまま使用可能
- ✅ Centralでの追加実装が最小限
- ✅ LiSMのキーマップ定義をほぼそのまま流用

**デメリット**：
- ⚠️ Peripheral側で完全なセンサー処理を実装する必要
- ⚠️ Peripheral設定の複雑化（CONFIG_EC11, CONFIG_SENSOR等）

**実装難度**: ★★★★☆ (高)

---

### 方針2: **Peripheral側でセンサーイベントを生データのまま送信（仮想input-split対応）**

```
実装フロー：
┌─────────────────────────────────────────────────────────┐
│ Left（Peripheral）                                      │
├─────────────────────────────────────────────────────────┤
│ GPIO(EC11) → EC11ドライバ → Pulse Event               │
│              ↓                                          │
│         カスタムモジュールで                             │
│         Pulseイベント → Split送信パケット               │
│              ↓                                          │
│         BLE送信                                         │
└─────────────────────────────────────────────────────────┘
                      ↓ BLE
┌─────────────────────────────────────────────────────────┐
│ Right（Central）                                        │
├─────────────────────────────────────────────────────────┤
│ Splitパケット受信 → 仮想センサーデバイス                │
│              ↓                                          │
│         sensor-rotate-var処理                         │
│              ↓                                          │
│         キー入力生成 → 出力                              │
└─────────────────────────────────────────────────────────┘
```

**メリット**：
- ✅ Peripheral実装がシンプル
- ✅ Central側で柔軟なセンサー処理が可能

**デメリット**：
- ⚠️ カスタムSplit通信モジュールが必要
- ⚠️ Central側の仮想センサーデバイス実装が必要（非標準）
- ⚠️ west.yml に新規カスタムモジュール追加

**実装難度**: ★★★★★ (非常に高)

---

### 方針3: **右側（Central）にのみエンコーダを実装（シンプル）**

```
実装フロー：
┌─────────────────────────────────────────────────────────┐
│ Right（Central）                                        │
├─────────────────────────────────────────────────────────┤
│ GPIO(EC11) → EC11ドライバ → Pulse Event               │
│              ↓                                          │
│         sensor-rotate-var処理                         │
│              ↓                                          │
│         キー入力生成 → 出力                              │
└─────────────────────────────────────────────────────────┘

※ 左側（Peripheral）: 何もしない
```

**メリット**：
- ✅ 実装がシンプル（LiSMのDTS+キーマップで十分）
- ✅ 標準ZMKのみで完結
- ✅ 右側トラックボールの処理に集中

**デメリット**：
- ❌ ユーザー要件「左側のトラックボール接続端子に接続」に不適合
- ❌ ハードウェア構成の変更が必要
- ❌ 今回の要件では採用不可

**実装難度**: ★☆☆☆☆ (低)

---

## 3. 推奨対応方針の決定

### **採用方針: 方針1 - Peripheral側でセンサーイベント→キー入力に変換**

**理由**：
1. ✅ 既存のSplit通信機構をそのまま使用できる
2. ✅ torabo-tsuki-lpの既存設計に最も親和的
3. ✅ LiSMの標準実装（DTS + キーマップ）を大部分流用可能
4. ✅ カスタムモジュール追加が不要
5. ⚠️ 実装難度は高いが、検証とイテレーション可能な範囲

---

## 4. 実装フェーズと具体的タスク

### フェーズ1: ハードウェア・ピンアサイン確認（予備調査）

**タスク1-1**: FCC端子の物理接続確認
- [ ] FCC端子のピン配置図を作成/取得
- [ ] 左側Peripheral基板のレイアウト図確認
- [ ] トラックボール接続端子 ← エンコーダ接続の可否判定

**タスク1-2**: GPIO割り当て確認
- [ ] 左側Peripheralで使用可能な未割り当てGPIOを確認
- [ ] エンコーダA相、B相に割り当て可能なGPIOペアを特定
- [ ] 既存マトリックス/センサー端子と競合がないことを確認

**リスク**: ⚠️ ハードウェアドキュメント不足のため、実装前の確認が必須

---

### フェーズ2: Peripheral側 - DTS & CONFIG設定

**タスク2-1**: エンコーダデバイスツリー定義（DTS）

- [ ] 新規スニペット作成: `snippets/encoder-left/encoder.overlay`
- [ ] 左側Peripheralに対応したエンコーダ定義を追加：
  ```devicetree
  &encoder {
      compatible = "alps,ec11";
      a-gpios = <&gpio0 18 (GPIO_ACTIVE_HIGH | GPIO_PULL_UP)>;
      b-gpios = <&gpio0 16 (GPIO_ACTIVE_HIGH | GPIO_PULL_UP)>;
      steps = <12>;
      status = "okay";
  };
  
  &sensors {
      compatible = "zmk,keymap-sensors";
      sensors = <&encoder>;
      triggers-per-rotation = <6>;
  };
  ```

- [ ] SPI0/I2C0無効化用overlay: `snippets/encoder-left/disable-spi-i2c.overlay`
  ```devicetree
  &spi0 {
      status = "disabled";
  };
  
  &i2c0 {
      status = "disabled";
  };
  ```

**タスク2-2**: CONFIG設定

- [ ] 新規スニペット設定: `snippets/encoder-left/encoder.conf`
  ```
  # エンコーダドライバ
  CONFIG_EC11=y
  CONFIG_EC11_TRIGGER_GLOBAL_THREAD=y
  
  # センサーフレームワーク
  CONFIG_SENSOR=y
  CONFIG_SENSOR_GENERIC_THREAD_STACK_SIZE=1024
  ```

- [ ] `build.yaml` に左側エンコーダPeripheral構成を追加:
  ```yaml
  - board: bmp_boost
    shield: torabo_tsuki_lp_left
    snippet: "studio-rpc-usb-uart encoder-left"
    artifact-name: left_peripheral_encoder
  ```

**タスク2-3**: Pinctrl設定確認

- [ ] GPIO0.18/16をPull-Upで設定（既存pinctrl設定を確認）
- [ ] SPI0/I2C0を無効化する際のpinctrl干渉を確認

---

### フェーズ3: キーマップ統合 - Sensor Binding定義

**タスク3-1**: Peripheralキーマップでセンサーバインディング定義

Peripheral側では標準ZMKの`keymap-sensors`フレームワークを使用し、エンコーダイベントをキー入力に変換します。

- [ ] `config/keymap.keymap`へエンコーダ定義を追加:
  ```
  &encoder {
      status = "okay";
  };
  
  &sensors {
      status = "okay";
  };
  
  behaviors {
      encoder_kp: sensor_rotate_kp {
          compatible = "zmk,behavior-sensor-rotate-var";
          #sensor-binding-cells = <2>;
          bindings = <&kp>, <&kp>;
      };
  };
  
  keymap {
      compatible = "zmk,keymap";
      
      default_layer {
          sensor-bindings = <&encoder_kp A B>;
          // A = CW回転で送信するキー
          // B = CCW回転で送信するキー
      };
  };
  ```

**タスク3-2**: キー割り当ての検討

- [ ] 要件確認: エンコーダUP→"A", DOWN→"B"
- [ ] キーコード確定:
  ```
  CW回転 (UP) → &kp A
  CCW回転 (DOWN) → &kp B
  ```

**タスク3-3**: ビルド設定更新

- [ ] `build.yaml`のエンコーダPeripheral構成でキーマップが正しく読み込まれるか確認
- [ ] Peripheral専用のキーマップセクションが必要な場合は別途対応

---

### フェーズ4: 動作検証

**タスク4-1**: コンパイル/ビルド
- [ ] `make`でPeripheral/Central両FWをビルド
- [ ] CONFIG/DTS エラーがないことを確認

**タスク4-2**: Peripheral側の単体動作確認
- [ ] USB接続でPeripheral FWをflash
- [ ] UARTログでEC11デバイスが認識されているか確認
- [ ] エンコーダ回転時にセンサーイベントがログに出力されるか確認

**タスク4-3**: Split統合動作確認
- [ ] Central FW + Peripheral FWで分割キーボード通常運用
- [ ] 左側エンコーダ回転 → キー入力がCentralで受け取られるか確認
- [ ] 右側トラックボール操作と重複しないか確認

**タスク4-4**: キー入力確認
- [ ] エンコーダ回転UP → "A"キー入力確認
- [ ] エンコーダ回転DOWN → "B"キー入力確認

**リスク**: ⚠️ Split通信レベルでのイベント送信失敗が想定

---

### フェーズ5: キーマップ拡張（オプション）

**タスク5-1**: Central側キーマップ統合
- [ ] `config/keymap.keymap`にエンコーダバインディング追加
- [ ] レイヤー別の異なる動作割り当て
- [ ] 例:
  ```
  Layer0 (mac): UP→PageUp, DOWN→PageDown  
  Layer2 (mouse): UP→ScrollUp, DOWN→ScrollDown
  Layer6 (function): UP→Volume+, DOWN→Volume-
  ```

**タスク5-2**: ドキュメント更新
- [ ] README.md: エンコーダ機能説明追加
- [ ] キーマップ図の更新

---

## 5. 技術的な未解決課題（ブロッカー）

### 課題A: Peripheralセンサー送信メカニズム
- **状態**: ⚠️ 要修正 - Central側に `zmk,keymap-sensors` ノードが必要
- **詳細**: ZMKソース（`cormoran/zmk` `v0.3-branch+custom-studio-protocol+ble`）を調査した結果、以下が判明。

  `app/include/zmk/sensors.h` の定義：
  ```c
  #define ZMK_KEYMAP_SENSORS_NODE DT_INST(0, zmk_keymap_sensors)
  #define ZMK_KEYMAP_HAS_SENSORS DT_NODE_HAS_STATUS(ZMK_KEYMAP_SENSORS_NODE, okay)
  ```

  `app/src/split/bluetooth/central.c` の `split_central_sensor_notify_func` は `#if ZMK_KEYMAP_HAS_SENSORS` で囲まれており、Central側に `zmk,keymap-sensors` ノード（`status = "okay"`）が存在しない場合：
  1. Central は Peripheral からのセンサー GATT 通知への **BLE購読自体を行わない**
  2. `app/src/keymap.c` の `ZMK_SUBSCRIPTION(keymap, zmk_sensor_event)` も無効化され、keymap の `sensor-bindings` が処理されない

  つまり、エンコーダハードウェアが左側（Peripheral）にしかなくても、**Central側のデバイスツリーに `zmk,keymap-sensors` ノードが必要**。

- **現状の問題**: `right_central` ビルドにはエンコーダ関連のスニペットが含まれておらず、Central側に `zmk,keymap-sensors` ノードが存在しないため、エンコーダ入力が完全に無視されている。
- **対応方針**: スニペットを以下の構成に整理する。

  ```
  snippets/encoder/          ← 共通（新規）
    encoder.overlay          - EC11プレースホルダー(status=disabled) + zmk,keymap-sensors
    encoder.conf             - CONFIG_EC11, CONFIG_SENSOR, CONFIG_EC11_TRIGGER_GLOBAL_THREAD
    snippet.yml

  snippets/encoder-left/     ← Peripheral追加分のみ（既存を整理）
    encoder-left.overlay     - &encoderを実GPIOで上書き(status=okay) + SPI0/I2C0無効化
    snippet.yml              ※ .conf は encoder 共通側に移動するため不要
  ```

  ビルド構成：
  - `left_peripheral_encoder`: `snippet: "... encoder encoder-left"`
  - `right_central_encoder`:   `snippet: "... encoder"`

- **リスク**: 低

### 課題B: ハードウェア・GPIO割り当て
- **状態**: ✅ 確定 - LiSMエンコーダ基板ピンアサイン確認
  - ENC_A (ピン3) → GPIO0.18
  - ENC_B (ピン4) → GPIO0.16
  - 電源/GND: FCC端子ピン1/5から供給
- **実装方法**: DTS定義時にこれらGPIOを明示
- **リスク**: 低

### 課題C: SPI0/I2C0との競合回避
- **状態**: ✅ 確認済み - 左側では無効化可能
- **詳細**: 左側Peripheral専用化により、右側のトラックボール実装に影響なし
- **実装**: SPI0/I2C0を無効化するoverlay追加
- **リスク**: 低（左側と右側が独立）

### 課題D: ビルドプロファイル
- **状態**: 🟡 要更新
- **詳細**: スニペット構成整理に伴い `build.yaml` も更新が必要
  - `left_peripheral_encoder`: `encoder encoder-left` の2スニペット指定
  - `right_central_encoder` を新規追加: `encoder` スニペットのみ
- **リスク**: 低

---

## 6. リスク及び緩和策

| リスク | 確度 | 重大度 | 状態 | 緩和策 |
|-------|------|-------|------|-------|
| Peripheral側センサー送信が標準機能ではない | ⚠️ 高 | 🔴 致命的 | ⚠️ 要修正 | ZMKソース確認の結果、Central側にも`zmk,keymap-sensors`ノードが必要（課題A参照） |
| ピンアサイン誤認定 | ⚠️ 高 | 🟡 重大 | ✅ 解決 | LiSMエンコーダ基板ピン3/4 = GPIO0.18/16確定 |
| 既存トラックボール処理との競合 | ⚠️ 中 | 🟡 重大 | ✅ 解決 | 左側専用化により右側に影響なし |
| west.yml依存関係エラー | ⚠️ 中 | 🟡 重大 | 🟡 検証待ち | スニペット作成時に段階的ビルド検証 |
| Peripheralキーマップ実装 | ⚠️ 低 | 🟡 重大 | ✅ 解決 | 通常キーマップの`sensor-bindings`で実装 |
| SPI0/I2C0無効化の副作用 | ⚠️ 低 | 🟡 中 | ✅ 解決 | 左側Peripheral専用構成で排他利用許容 |

---

## 7. 次のステップ（実装フェーズ開始）

### 優先度順実行タスク

**実装タスク（課題A対応）**:

1. **スニペット構成の整理**
   - [ ] `snippets/encoder/` 新規作成（共通）
     - `encoder.overlay`: EC11プレースホルダー(status=disabled) + `zmk,keymap-sensors`
     - `encoder.conf`: CONFIG_EC11, CONFIG_SENSOR, CONFIG_EC11_TRIGGER_GLOBAL_THREAD
     - `snippet.yml`
   - [ ] `snippets/encoder-left/` を整理（Peripheral追加分のみに変更）
     - `encoder-left.overlay`: `&encoder` を実GPIO(status=okay)で上書き + SPI0/I2C0無効化
     - `snippet.yml` のみ（`.conf` は `encoder` 共通側に移動）
     - 既存 `encoder.conf` は削除

2. **`build.yaml` 更新**
   - [ ] `left_peripheral_encoder`: snippet を `"... encoder encoder-left"` に変更
   - [ ] `right_central_encoder` を新規追加: `"... split-central input-trackball input-listener encoder"`

3. **コンパイル/ビルド検証**
   - [ ] GitHub Actions でビルドエラーがないことを確認

### 実装フェーズの検証ゲート

**各フェーズ完了時に確認する事項**：

| フェーズ | ゲート | 成功基準 |
|--------|-------|--------|
| 2 (DTS/CONFIG) | ビルド完了 | コンパイルエラーなし、警告最小化 |
| 3 (キーマップ) | ビルド完了 | センサーバインディング認識確認 |
| 4 (検証) | Peripheral単体 | UARTログでEC11認識、パルスイベント確認 |
| 4 (検証) | Split統合 | 左側回転UP→A、DOWN→B キー入力確認 |

---

## 8. 実装に使用するコンポーネント・リファレンス

### LiSMエンコーダ基板ピン定義

```
ピン番号  信号         説明
1        GND          基板グランド
2        VCC (3.3V)   電源ライン
3        ENC_A        エンコーダA相（→ GPIO0.18）
4        ENC_B        エンコーダB相（→ GPIO0.16）
5        SW           タクトスイッチ信号ライン（未使用）
6        ID/NC        モジュール識別/未使用（GPIO0.8予約）
```

### torabo-tsuki-lpハードウェアマッピング

```
FCC端子ピン  →  信号         →  左側GPIO
1           →  GND         →  nRF52840 GND
2           →  ENC_A       →  GPIO0.18
3           →  ENC_B       →  GPIO0.16
4           →  (reserved)  →  GPIO0.20
5           →  VCC (3.3V)  →  nRF52840 3.3V
6           →  (reserved)  →  GPIO0.8
```

---

## 10. スニペット整理実装後の問題調査

### 現象

実装後、以下のビルド組み合わせでハングアップが発生：

| 組み合わせ | 状態 |
|----------|------|
| `left_peripheral_encoder` + `right_central_encoder` | 🔴 **ハング** |
| `right_central_encoder` 単体 | ✅ 正常 |
| `left_peripheral_encoder` 単体 | ✅ 正常（推定） |
| `left_peripheral` + `right_central` | ✅ 正常 |

**詳細**：`left_peripheral_encoder` が接続すると `right_central` 側（Central）が無応答になる

### 調査結果

#### 仮説1: GPIO 競合（❌ 否定）

**根拠**：
- ZMK センサー code（`sensors.c`）の `DEVICE_DT_GET_OR_NULL` は disabled ノードに対して NULL を返す
- `zmk_sensors_init_item` は NULL デバイスを check で早期リターン → GPIO アクセスなし
- Central の pinctrl（SPI0）と disabled EC11 node の GPIO 定義は compile-time での重複だが、実行時には SPI0 ドライバのみ使用

**結論**：GPIO 競合は発生していない

#### 仮説2: Keymap センサーバインディングの二重処理（❌ 否定）

- LisM では同一キーマップを Peripheral/Central で区別せず使用（確認済み）
- 他の分割キーボード ZMK FW でも同様の実装が標準（確認済み）
- 二重処理が根本原因ではない

---

### 根本原因: `ZMK_KEYMAP_SENSORS_LEN = 0` による零長配列越境アクセス（✅ 特定済み）

#### 証拠

GitHub Actions ビルドログ（最新 enc ブランチ）の `right_central_encoder` ビルドに以下の警告が存在する：

```
/zmk/app/src/behaviors/behavior_sensor_rotate_common.c:32:56: warning:
  array subscript 'sensor_index' is outside the bounds of an interior
  zero-length array 'struct sensor_value[0][9]' [-Wzero-length-bounds]
     struct sensor_value remainder[ZMK_KEYMAP_SENSORS_LEN][ZMK_KEYMAP_LAYERS_LEN];
```

- **`ZMK_KEYMAP_SENSORS_LEN = 0`**、`ZMK_KEYMAP_LAYERS_LEN = 9`（9レイヤー）
- **同じ警告は `left_peripheral_encoder` ビルドには存在しない**（左側では `ZMK_KEYMAP_SENSORS_LEN = 1`）

#### 原因メカニズム

`sensors.h` より：
```c
#define ZMK_KEYMAP_SENSORS_LEN DT_PROP_LEN(ZMK_KEYMAP_SENSORS_NODE, sensors)
```

`sensors = <&encoder>` の `phandles` 型プロパティで参照先ノード (`encoder`) が `status = "disabled"` の場合、Zephyr の DT コンパイラが `_LEN = 0` を生成する。

| ビルド | encoder node | ZMK_KEYMAP_SENSORS_LEN |
|--------|-------------|----------------------|
| `left_peripheral_encoder` | `status = "okay"`（encoder-left スニペットが上書き） | **1** |
| `right_central_encoder` | `status = "disabled"`（placeholder のまま） | **0** |

#### クラッシュループのフロー

```
[Peripheral]
EC11回転 → raise_zmk_sensor_event() → BLE GATT通知送信
                                             ↓
[Central]
split_central_sensor_notify_func() → raise_zmk_sensor_event()
  → keymap.c sensor event listener
    → zmk_behavior_sensor_rotate_common_accept_data()
      → data->remainder[sensor_index][event.layer]
           ↑
      remainder は [0][9] 零長配列 → 範囲外メモリアクセス
           ↓
      nRF52840 HardFault → デバイスリセット
           ↓
      Peripheral 再接続 → センサーイベント再送 → 再クラッシュ
           ↓
      【クラッシュループ = 外側から"ハング"に見える】
```

#### `right_central_encoder` 単体が正常な理由

Peripheral 未接続 → センサーイベントが届かない → クラッシュしない。ビルドは通るが実行時に踏む地雷が存在する状態。

---

### 対策（✅ 実施済み 2026-06-03）

#### 方針

ZMK の標準パターン（LisM 実装で確認）では、エンコーダのハードウェアが Peripheral 側にしかない場合でも、`ZMK_KEYMAP_SENSORS_LEN` を正しく設定するために **Central 側でもエンコーダノードを `status = "okay"` にする** 必要がある。

Central 側で GPIO0.18/16 をそのまま有効化すると SPI0（トラックボール）と競合するため、BMP Boost 上で**意図的に未使用のピン**（P0.24/P0.25）を placeholder として使用する。EC11 ドライバはこれらを pull-up 入力として初期化するが、ピンは未接続で安定 High のため疑似イベントは発生しない。

#### 変更内容: `snippets/encoder/encoder.overlay`

```devicetree
// 変更前
encoder: encoder {
    a-gpios = <&gpio0 18 (GPIO_ACTIVE_HIGH | GPIO_PULL_UP)>;
    b-gpios = <&gpio0 16 (GPIO_ACTIVE_HIGH | GPIO_PULL_UP)>;
    status = "disabled";  // ← DT_PROP_LEN が 0 を返す原因
};

// 変更後
// GPIO P0.24/P0.25 は BMP Boost の gpio-map に含まれない未接続ピンを意図的に使用
encoder: encoder {
    a-gpios = <&gpio0 24 (GPIO_ACTIVE_HIGH | GPIO_PULL_UP)>;
    b-gpios = <&gpio0 25 (GPIO_ACTIVE_HIGH | GPIO_PULL_UP)>;
    status = "okay";  // ZMK_KEYMAP_SENSORS_LEN = 1 になる
};
```

`encoder-left.overlay` が Peripheral 側で GPIO0.18/16 に上書きするため、実機の動作は変わらない。

#### 修正後の状態

| ビルド | encoder GPIO | status | ZMK_KEYMAP_SENSORS_LEN |
|--------|-------------|--------|----------------------|
| `left_peripheral_encoder` | 0.18/16（encoder-left で上書き） | okay | **1** |
| `right_central_encoder` | 0.24/25（未使用ピン・placeholder） | okay | **1** ✅（0 → 1）|

---

## 11. BLE ペアリング後のハング問題（継続調査中）

### 現象

`encoder.overlay` を `status = "okay"` + GPIO0.24/25 に修正後、ビルドは成功した。しかし実機テストで新たな問題が判明：

| 組み合わせ | 状態 |
|----------|------|
| `left_peripheral` + `right_central_encoder` | ✅ 正常 |
| `left_peripheral_encoder` + `right_central` | ✅ 正常 |
| `left_peripheral_encoder` + `right_central_encoder` | 🔴 **BLE接続直後にハング** |

エンコーダ回転前に、BLE ペアリング（GATT サービス購読）の段階でハングが発生する。

---

### 根本原因: `peripheral_slot` の `sub_discover_params` 共有による GATT CCC 発見処理の競合

#### `peripheral_slot` 構造体（cormoran/zmk `central.c`）

```c
struct peripheral_slot {
    ...
    struct bt_gatt_subscribe_params subscribe_params;              // キーポジション
    struct bt_gatt_subscribe_params sensor_subscribe_params;       // センサー
    struct bt_gatt_subscribe_params relay_event_subscribe_params;  // リレーイベント
    struct bt_gatt_discover_params  sub_discover_params;           // ← 全購読で共有
    ...
    struct bt_gatt_subscribe_params batt_lvl_subscribe_params;     // バッテリー
};
```

**すべての GATT 購読が 1 つの `sub_discover_params` を共有している**。

#### 競合メカニズム

`CONFIG_BT_GATT_AUTO_DISCOVER_CCC=y`（設定済み）の場合、`ccc_handle = 0` の購読では `bt_gatt_subscribe` → `gatt_ccc_discover` が呼ばれる。

`gatt_ccc_discover` は：
1. `memset(disc_params, 0)` で disc_params を**ゼロクリア**
2. CCC 検索用の情報を書き込んで ATT リクエスト送信

4 つの購読（key / sensor / relay / battery）が連続して開始されると：

```
key subscription   → disc_params に key 用情報をセット → ATT request 送信
sensor subscription → disc_params を上書き
relay subscription  → disc_params を上書き
battery subscription → disc_params を上書き（最終状態）
```

ATT layer はリクエストをキューイングし、応答が順番に届く。最初の ATT レスポンス（key CCC 検索結果）が届いたとき：

- `disc_params` の内容は battery 用に書き換わっている
- `gatt_ccc_discover_cb` が呼ばれ、内部で `memset(disc_params, 0)` を実行
- `disc_params->func = NULL` になる

以降のレスポンス（sensor / relay / battery CCC）が届いたとき：

- `gatt_find_info_rsp` または `gatt_discover_next` が `params->func(conn, NULL, params)` を呼び出す
- **`params->func = NULL` → NULL ポインタ呼び出し → HardFault → デバイスリセット → ペアリングループ**

#### なぜ 3 購読では正常か

| 組み合わせ | 実際の GATT 購読数 | 結果 |
|----------|-----------------|------|
| `left_peripheral` + `right_central_encoder` | key + relay + battery = **3** | ✅ センサーChar が Peripheral に存在しない → sensor 購読スキップ |
| `left_peripheral_encoder` + `right_central` | key + relay + battery = **3** | ✅ Central が `ZMK_KEYMAP_HAS_SENSORS=0` → sensor 購読コード無効化 |
| `left_peripheral_encoder` + `right_central_encoder` | key + **sensor** + relay + battery = **4** | 🔴 sensor 購読が追加され競合発生 |

input-split 関連の購読（`input_slot`）は `ccc_handle` を直接設定する（`gatt_ccc_discover` を経由しない）ため、この問題に寄与しない。

---

### 修正方針

**cormoran/zmk `app/src/split/bluetooth/central.c` の修正が必要**。

`peripheral_slot` 構造体に sensor 用の独立した discover_params を追加する：

```c
// peripheral_slot 構造体に追加（1行）
struct bt_gatt_discover_params sensor_sub_discover_params;
```

sensor 購読設定箇所で、共有 disc_params の代わりに専用 disc_params を使用：

```c
// 変更前
slot->sensor_subscribe_params.disc_params = &slot->sub_discover_params;

// 変更後
slot->sensor_subscribe_params.disc_params = &slot->sensor_sub_discover_params;
```

この 2 行の変更により、sensor の CCC 発見処理が他の購読の disc_params を破壊しなくなる。

---

### 修正に必要な作業

1. `cormoran/zmk` を自分の GitHub アカウントに fork する
2. `app/src/split/bluetooth/central.c` に上記 2 行の変更を適用する
3. `config/west.yml` の ZMK 参照先を fork したリポジトリに変更する：
   ```yaml
   # 変更前
   - name: zmk
     remote: cormoran
     revision: v0.3-branch+custom-studio-protocol+ble
   
   # 変更後
   - name: zmk
     remote: <自分のGitHubユーザー名>
     revision: v0.3-branch+custom-studio-protocol+ble+encoder-fix
   ```

---

### 現在の状態

- ✅ **修正済み** (2026-06-04)
- fork リポジトリ: `zin-tk/zmk`
- 修正ブランチ: `v0.3-branch+custom-studio-protocol+ble+encoder-fix`
- 修正コミット: `80214b10f61833ded27f1d5e024802794dc51369`
- `config/west.yml` 更新済み: zmk 参照先を `zin-tk` fork に変更
- ビルド確認: GitHub Actions 全ジョブ成功 ✅

---

## 12. EC11 SW プッシュスイッチ実装調査（進行中）

### ハードウェア仕様

- J101 コネクタは逆向き実装: Pin2=VCC(3.3V), Pin3=ENC_A, Pin4=ENC_B, Pin5=SW, Pin6=GND
- GPIO マッピング（逆向き後）: A=GPIO0.16(SDIO), B=GPIO0.19(MOTION), SW=GPIO0.18(SCLK)
- SW のもう一端（共通端子）: GPIO0.20(CS) に接続
- SPI0 / I2C0 を `status = "disabled"` にして GPIO0.16/0.18/0.20 を解放

---

### 試みた対策と結果

#### ① kscan-gpio-matrix（ACTIVE_HIGH col、interrupt モード）【取りこぼし多発】

```dts
kscan_enc_sw: kscan_enc_sw {
    compatible = "zmk,kscan-gpio-matrix";
    col-gpios = <&gpio0 20 GPIO_ACTIVE_HIGH>;
    row-gpios = <&gpio0 18 (GPIO_ACTIVE_HIGH | GPIO_PULL_DOWN)>;
};
```

**結果**: SW 取りこぼしが頻発。10 回押下で 2 回程度しか検出されない。

**根本原因（ログで確定）**: interrupt モードでは idle 時に col = LOW。SW 押下時に row が LOW→LOW のまま変化なし → 割り込み発生なし → スキャン未実行 → 未検出。エンコーダ回転時に偶然スキャンが走ったときのみ検出できる。

左ペリフェラルログで確認: 10 回押下 → `position: 41` イベントは 4 件のみ（2 回分）。

---

#### ② BLE 送信バッファ増量（CONFIG_BT_CONN_TX_MAX=10）【効果なし】

```
CONFIG_BT_CONN_TX_MAX=10
CONFIG_BT_BUF_ACL_TX_COUNT=10
```

右 central ログでエンコーダのジッター通知（`triggers:0` の sensor notification）が BLE を占有している可能性を疑い実施。

**結果**: 改善なし。原因が BLE 層でなく kscan 検出層（peripheral 側）にあることを左ペリフェラルログで確認したため。

---

#### ③ gpio-hog + kscan-gpio-direct（古いビルドで誤検証）【効果なし扱い→実は有効】

```dts
&gpio0 {
    enc_sw_drive: enc_sw_drive {
        gpio-hog;
        gpios = <20 0>;
        output-high;
    };
};

kscan_enc_sw: kscan_enc_sw {
    compatible = "zmk,kscan-gpio-direct";
    input-gpios = <&gpio0 18 (GPIO_ACTIVE_HIGH | GPIO_PULL_DOWN)>;
    wakeup-source;
};
```

GPIO0.20 を gpio-hog で常時 OUTPUT HIGH にし、GPIO0.18 を kscan-gpio-direct で検出。

**初回確認時の結果**: 「一部改善」と報告。→ **実際は古いビルド（kscan-gpio-matrix）を書き込んでいたことが後に判明。** ログに `kscan_matrix_init_output_inst: pin 20` が出ており、overlay の変更が反映されていなかった。

**正しいビルドで再確認**: ログに `kscan_direct_init_input_inst: pin 18` が出るようになり、5回押下テストで14回検出（以前は2回）と大幅改善。

**しかし依然として取りこぼし継続**（5回押下でCは1出力）。

---

#### ④ BLE peripheral latency スリープが原因と特定

5回押下テストのログで決定的なパターンを確認：

```
24.223s: kscan_direct_read: SW pressed   ← 1回目 検出
24.401s: kscan_direct_read: SW released
24.981s: le_param_updated: interval 6 latency 30  ← ここでスリープ移行
25.255s: split_peripheral_listener（最後のイベント）
（以降 沈黙。残り4回のSW押下は一切検出されない）
30.344s: le_param_updated: interval 12 latency 15
```

**根本原因**: `le_param_updated: interval 6, latency 30` 適用後、peripheral が BLE 省電力スリープに入り、GPIO 割り込み（SW 検出）が機能しなくなる。`latency 30` は最大 225ms（30 × 7.5ms）スリープ可能を意味する。Zephyr PM がこのスリープ中に GPIO 割り込みを無効化していると推定。

encoder のイベント（split_peripheral_listener）も同タイミングで停止しており、SW だけでなく全 GPIO 割り込みが止まっている。

---

#### ⑤ CONFIG_PM=n【確認中】

```
# encoder-left.conf に追加
CONFIG_PM=n
```

Zephyr の Power Management を無効化することで、BLE peripheral latency によるスリープが GPIO 割り込みを無効化するのを防ぐ試み。

**結果**: 確認中

---

### 現在の状態（2026-06-07）

| 対策 | 結果 |
|------|------|
| kscan-gpio-matrix interrupt mode | ❌ 取りこぼし多発（根本原因: idle 時 col=LOW） |
| BLE バッファ増量（CONFIG_BT_CONN_TX_MAX=10） | ❌ 効果なし（原因が kscan 検出層のため） |
| gpio-hog + kscan-gpio-direct（古いビルド誤適用） | ❌ 誤確認（古いビルドを書き込んでいた） |
| gpio-hog + kscan-gpio-direct（正しいビルド） | ⚠️ 大幅改善するが取りこぼし継続 |
| CONFIG_PM=n | 🔄 確認中 |

**根本原因（確定）**: `le_param_updated: interval 6, latency 30` による Zephyr PM スリープが GPIO 割り込みを無効化する。

**次の調査方向**:
- `CONFIG_PM=n` で全 GPIO 割り込みが復活するか確認
- 効果なければ `wakeup-source` の正しい設定方法を調査（`CONFIG_PM_DEVICE=y` + GPIO wakeup source 設定）
- または BLE peripheral latency を 0 に固定する ZMK 設定を調査

---

## 9. 参考資料

- **ZMK RotaryEncoder**: https://zmk.dev/docs/features/encoders
- **ZMK Split**: https://zmk.dev/docs/features/split-keyboards
- **LiSM Firmware**: https://github.com/4mple-lab/ZMK-LisM
- **torabo-tsuki-lp Firmware**: [ローカルリポジトリ]
- **EC11 Datasheet**: ALPS EC11/EC11互換センサー仕様

---

**ドキュメント作成**: 2026-05-27  
**最終更新**: 2026-06-04  
**ステータス**: ✅ BLE ハング問題修正済み - `zin-tk/zmk` fork の `central.c` に `sensor_sub_discover_params` 追加完了  
**次アクション**: 実機テスト - `left_peripheral_encoder` + `right_central_encoder` の組み合わせでBLE接続 → エンコーダ回転確認
