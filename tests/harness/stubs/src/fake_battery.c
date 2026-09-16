/*
 * 擬似バッテリー (PC テスト専用)
 *
 * 実機のシールドは Kconfig.defconfig で CONFIG_ZMK_BATTERY_REPORTING=y を
 * 立てているが、Tier B は shield を使わないボードでビルドするため、
 * 電池まわりの機能 (BAS / バッテリー履歴 / 分割のバッテリープロキシ) が
 * まるごと落ちていた。実機との差を消すため、電圧を devicetree で与える
 * だけのセンサーを置いて chosen zmk,battery に繋ぐ。
 *
 * 実機の電圧しきい値による電源断 (zmk-feature-non-lipo-battery-management)
 * は ADC ドライバを要求するので、そちらはまだ載らない。
 *
 * SPDX-License-Identifier: MIT
 */

#define DT_DRV_COMPAT zmk_fake_battery

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/sensor.h>

#include <zephyr/logging/log.h>
LOG_MODULE_DECLARE(zmk, CONFIG_ZMK_LOG_LEVEL);

#if DT_HAS_COMPAT_STATUS_OKAY(DT_DRV_COMPAT)

/* 実機の非 LiPo 設定と同じ換算範囲。0% と 100% の位置を合わせておく。 */
#define FAKE_BATTERY_MIN_MV 1000
#define FAKE_BATTERY_MAX_MV 1300

struct fake_battery_config {
    uint16_t millivolts;
};

static uint8_t fake_battery_mv_to_pct(uint16_t mv) {
    if (mv >= FAKE_BATTERY_MAX_MV) {
        return 100;
    }
    if (mv <= FAKE_BATTERY_MIN_MV) {
        return 0;
    }
    return (100 * (mv - FAKE_BATTERY_MIN_MV)) / (FAKE_BATTERY_MAX_MV - FAKE_BATTERY_MIN_MV);
}

static int fake_battery_sample_fetch(const struct device *dev, enum sensor_channel chan) {
    if (chan != SENSOR_CHAN_GAUGE_VOLTAGE && chan != SENSOR_CHAN_GAUGE_STATE_OF_CHARGE &&
        chan != SENSOR_CHAN_ALL) {
        return -ENOTSUP;
    }
    return 0;
}

static int fake_battery_channel_get(const struct device *dev, enum sensor_channel chan,
                                    struct sensor_value *val) {
    const struct fake_battery_config *cfg = dev->config;

    switch (chan) {
    case SENSOR_CHAN_GAUGE_VOLTAGE:
        val->val1 = cfg->millivolts / 1000;
        val->val2 = (cfg->millivolts % 1000) * 1000;
        return 0;

    case SENSOR_CHAN_GAUGE_STATE_OF_CHARGE:
        val->val1 = fake_battery_mv_to_pct(cfg->millivolts);
        val->val2 = 0;
        return 0;

    default:
        return -ENOTSUP;
    }
}

static const struct sensor_driver_api fake_battery_api = {
    .sample_fetch = fake_battery_sample_fetch,
    .channel_get = fake_battery_channel_get,
};

static int fake_battery_init(const struct device *dev) {
    const struct fake_battery_config *cfg = dev->config;

    LOG_INF("Fake battery: %d mV (%d%%)", cfg->millivolts,
            fake_battery_mv_to_pct(cfg->millivolts));
    return 0;
}

static const struct fake_battery_config fake_battery_cfg = {
    .millivolts = DT_INST_PROP(0, millivolts),
};

DEVICE_DT_INST_DEFINE(0, &fake_battery_init, NULL, NULL, &fake_battery_cfg, POST_KERNEL,
                      CONFIG_SENSOR_INIT_PRIORITY, &fake_battery_api);

#endif /* DT_HAS_COMPAT_STATUS_OKAY(DT_DRV_COMPAT) */
