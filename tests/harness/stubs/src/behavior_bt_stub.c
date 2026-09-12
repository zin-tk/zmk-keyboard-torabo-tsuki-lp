/*
 * &bt ビヘイビアのスタブ (PC テスト専用)
 *
 * ZMK は behavior_bt.c を CONFIG_ZMK_BLE=y のときだけビルドする。
 * native_sim には BLE コントローラが無いため BLE は無効だが、
 * キーマップが &bt を参照している以上 devicetree ノードは実体を必要とする。
 * ここでは実際の BLE 操作の代わりに、どの BT コマンドが発行されたかを
 * ログに出すだけのビヘイビアを提供する。
 *
 * SPDX-License-Identifier: MIT
 */

#define DT_DRV_COMPAT zmk_behavior_bluetooth

#include <zephyr/device.h>
#include <zephyr/devicetree.h>

#include <zephyr/logging/log.h>
LOG_MODULE_DECLARE(zmk, CONFIG_ZMK_LOG_LEVEL);

#include <drivers/behavior.h>
#include <zmk/behavior.h>

#if DT_HAS_COMPAT_STATUS_OKAY(DT_DRV_COMPAT)

static int on_keymap_binding_pressed(struct zmk_behavior_binding *binding,
                                     struct zmk_behavior_binding_event event) {
    LOG_DBG("bt_stub: pressed command %d arg %d", binding->param1, binding->param2);
    return ZMK_BEHAVIOR_OPAQUE;
}

static int on_keymap_binding_released(struct zmk_behavior_binding *binding,
                                      struct zmk_behavior_binding_event event) {
    LOG_DBG("bt_stub: released command %d arg %d", binding->param1, binding->param2);
    return ZMK_BEHAVIOR_OPAQUE;
}

static const struct behavior_driver_api behavior_bt_stub_driver_api = {
    .binding_pressed = on_keymap_binding_pressed,
    .binding_released = on_keymap_binding_released,
};

BEHAVIOR_DT_INST_DEFINE(0, NULL, NULL, NULL, NULL, POST_KERNEL, CONFIG_KERNEL_INIT_PRIORITY_DEFAULT,
                        &behavior_bt_stub_driver_api);

#endif /* DT_HAS_COMPAT_STATUS_OKAY(DT_DRV_COMPAT) */
