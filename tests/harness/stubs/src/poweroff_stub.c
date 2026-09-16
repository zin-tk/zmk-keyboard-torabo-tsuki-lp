/*
 * sys_poweroff() の PC テスト用実装
 *
 * Zephyr の sys_poweroff() は SoC 側の z_sys_poweroff() を呼ぶ。
 * native_sim / nrf52_bsim にはこれが無いため CONFIG_HAS_POWEROFF が n になり、
 * CONFIG_ZMK_SLEEP ごとビルドから消えていた。実機ではこの経路が
 * 「USB 給電が無いときだけ寝る」判定を持っているので、テストでも成立させる。
 *
 * シミュレーション上の「電源が切れた」はプロセスの終了で表す。BabbleSim では
 * その機体だけが電波上から消え、残りの機体はそのまま走り続ける。
 *
 * SPDX-License-Identifier: MIT
 */

#include <zephyr/kernel.h>
#include <zephyr/toolchain.h>

#include <zephyr/logging/log.h>
#include <zephyr/logging/log_ctrl.h>
LOG_MODULE_DECLARE(zmk, CONFIG_ZMK_LOG_LEVEL);

#include <posix_board_if.h>

FUNC_NORETURN void z_sys_poweroff(void) {
    LOG_WRN("sys_poweroff: powering off (simulated)");
    LOG_PANIC();
    posix_exit(0);
}
