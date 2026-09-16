/*
 * bsim の機体に固定の BLE アドレスを与える (PC テスト専用)
 *
 * 実機の nRF52 は FICR に工場書き込みのデバイスアドレスを持っていて、
 * Zephyr はそれを identity として使う。だから電源を入れ直しても
 * BLE アドレスは変わらず、ホストや相方とのボンドが生き続ける。
 *
 * nrf52_bsim の FICR モデルは DEVICEADDRTYPE を 0 (public) にしているため
 * この経路が成立せず、Zephyr は起動のたびに乱数で identity を作る。
 * その結果 --reboot の 2 回目で左右のアドレスが変わってしまい、
 * 「電源を入れ直した」ではなく「別の個体になった」状態を試すことになる。
 *
 * DEVICEADDRTYPE の最下位ビットを立てるだけで、FICR の値が
 * random static アドレスとして使われる (hci_vendor_read_static_addr)。
 * FICR の乱数は機体番号から決まる種で初期化されるので、
 * 機体ごとに違い、かつ起動をまたいで同じ値になる。
 *
 * SPDX-License-Identifier: MIT
 */

#include <zephyr/init.h>

#include <soc.h>

static int bsim_use_ficr_static_addr(void) {
    NRF_FICR->DEVICEADDRTYPE |= 0x01;
    return 0;
}

/* bt_enable() より前であればよい。PRE_KERNEL_1 が最も早い。 */
SYS_INIT(bsim_use_ficr_static_addr, PRE_KERNEL_1, 0);
