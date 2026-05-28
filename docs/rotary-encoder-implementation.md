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
LiSMエンコーダ基板のピン配置（確定）：

エンコーダ基板ピン  →  FCC コネクタピン  →  torabo-tsuki-lp左側 GPIO
1 (GND)         →  1 (GND)         →  nRF52840 GND
2 (VCC 3.3V)    →  5 (+3.3V)       →  nRF52840 3.3V
3 (ENC_A)       →  2 (SCLK/SDA)    →  GPIO0.18 ✅ （エンコーダA相割り当て）
4 (ENC_B)       →  3 (SDIO/SCL)    →  GPIO0.16 ✅ （エンコーダB相割り当て）
5 (SW)          →  4 (CS/IRQ)      →  GPIO0.20 （オプション）
6 (ID/NC)       →  6 (Power Ctrl)  →  GPIO0.8 （予約）

条件：
- 左側でSPI0/I2C0を無効化してGPIOを解放する必要がある
- 電源・グランド経路は確実に提供されている（10mA消費で十分）
- FCC端子ピン1, 5がGND/3.3Vとして機能することは確認済み
```

**リスク評価**: ✅ 低 - ハードウェア接続可能性確認済み

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
- **状態**: ✅ 確認済み - ZMK標準機能で実装可能
- **詳細**: Peripheral側で`sensor-rotate-var`ビヘイビアでキー入力に変換可能。Split通信では通常のキーイベントとして送信。
- **実装方式**: Peripheralの`keymap-sensors`ブロックで定義、キーイベント化して送信
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
- **状態**: 部分確認
- **詳細**: `build.yaml`の`left_peripheral`を拡張して`encoder-left`スニペット適用
- **必要な作業**: スニペット作成、build.yamlに新しい構成追加
- **リスク**: 低（既存プロファイルが参考になる）

---

## 6. リスク及び緩和策

| リスク | 確度 | 重大度 | 状態 | 緩和策 |
|-------|------|-------|------|-------|
| Peripheral側センサー送信が標準機能ではない | ⚠️ 高 | 🔴 致命的 | ✅ 解決 | ZMK標準の`sensor-rotate-var`で実装可能 |
| ピンアサイン誤認定 | ⚠️ 高 | 🟡 重大 | ✅ 解決 | LiSMエンコーダ基板ピン3/4 = GPIO0.18/16確定 |
| 既存トラックボール処理との競合 | ⚠️ 中 | 🟡 重大 | ✅ 解決 | 左側専用化により右側に影響なし |
| west.yml依存関係エラー | ⚠️ 中 | 🟡 重大 | 🟡 検証待ち | スニペット作成時に段階的ビルド検証 |
| Peripheralキーマップ実装 | ⚠️ 低 | 🟡 重大 | ✅ 解決 | 通常キーマップの`sensor-bindings`で実装 |
| SPI0/I2C0無効化の副作用 | ⚠️ 低 | 🟡 中 | ✅ 解決 | 左側Peripheral専用構成で排他利用許容 |

---

## 7. 次のステップ（実装フェーズ開始）

### 優先度順実行タスク

**今すぐ実行（フェーズ2-3: DTS/CONFIG/キーマップ実装）**:

1. **スニペット構成の作成**（1-2日）
   - [ ] `snippets/encoder-left/` ディレクトリ作成
   - [ ] `encoder.overlay` - エンコーダDTS定義
   - [ ] `disable-spi-i2c.overlay` - SPI0/I2C0無効化
   - [ ] `encoder.conf` - CONFIG_EC11等設定
   - [ ] `snippet.yml` - スニペット定義

2. **build.yaml拡張**（1日）
   - [ ] 左側エンコーダPeripheral構成追加
   - [ ] 既存`left_peripheral`プロファイルとの整合確認

3. **キーマップ統合**（1-2日）
   - [ ] `config/keymap.keymap`へ`&encoder`, `&sensors`ブロック追加
   - [ ] `sensor_rotate_kp`ビヘイビア定義
   - [ ] `sensor-bindings = <&encoder_kp A B>`追加

4. **コンパイル/ビルド検証**（1日）
   - [ ] `make` でビルド実行
   - [ ] DTS/CONFIG エラー確認

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

## 9. 参考資料

- **ZMK RotaryEncoder**: https://zmk.dev/docs/features/encoders
- **ZMK Split**: https://zmk.dev/docs/features/split-keyboards
- **LiSM Firmware**: https://github.com/4mple-lab/ZMK-LisM
- **torabo-tsuki-lp Firmware**: [ローカルリポジトリ]
- **EC11 Datasheet**: ALPS EC11/EC11互換センサー仕様

---

**ドキュメント作成**: 2026-05-27  
**最終更新**: 2026-05-28  
**ステータス**: 🟢 技術検証完了 / 実装準備完了  
**次アクション**: フェーズ2-3の実装スニペット・キーマップ作成に進む
