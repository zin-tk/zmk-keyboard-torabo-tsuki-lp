/*
 * Tier B のホスト役(4 台目)。PC やスマホの代わりに、キーボードの
 * セントラル(右)へ BLE で繋ぎにいく。
 *
 * ここが見たいのは「実機で起きた『ホストと接続できない』を bsim で再現できるか」
 * だけなので、HID ホストとして完全に振る舞う必要はない。
 *
 *   1. スキャンする
 *   2. HID サービス(0x1812)を広告している相手を見つける
 *   3. 接続する
 *   4. ペアリング(暗号化)まで進める
 *
 * 各段階で "HOST: " 付きの行を出す。run_split_tests.sh がこれを見て判定する。
 * HOG の購読とキー入力の受信はまだ実装していない。
 */

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/gap.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/byteorder.h>
#include <zephyr/sys/printk.h>

/* 判定に使う接頭辞。変えるときは run_split_tests.sh も合わせること。 */
#define HOST_TAG "HOST: "

/* 見つけてから接続要求を出すまでの猶予。bsim なので実時間ではない。 */
#define CONNECT_TIMEOUT_MS 5000

static struct bt_conn *default_conn;
/* 広告は繰り返し届くので、接続要求は 1 回だけに絞る。 */
static atomic_t connect_started;

static bool ad_has_hid_service(struct bt_data *data, void *user_data) {
    bool *found = user_data;

    if (data->type != BT_DATA_UUID16_SOME && data->type != BT_DATA_UUID16_ALL) {
        return true;
    }

    for (size_t i = 0; i + 1 < data->data_len; i += 2) {
        if (sys_get_le16(&data->data[i]) == BT_UUID_HIDS_VAL) {
            *found = true;
            return false;
        }
    }
    return true;
}

static void device_found(const bt_addr_le_t *addr, int8_t rssi, uint8_t adv_type,
                         struct net_buf_simple *ad) {
    char addr_str[BT_ADDR_LE_STR_LEN];
    bool is_hid = false;
    int err;

    /* 接続できない広告は用が無い。 */
    if (adv_type != BT_GAP_ADV_TYPE_ADV_IND && adv_type != BT_GAP_ADV_TYPE_ADV_DIRECT_IND) {
        return;
    }

    bt_data_parse(ad, ad_has_hid_service, &is_hid);
    if (!is_hid) {
        return;
    }

    bt_addr_le_to_str(addr, addr_str, sizeof(addr_str));
    printk(HOST_TAG "advertisement from %s (rssi %d)\n", addr_str, rssi);

    if (atomic_set(&connect_started, 1) == 1) {
        return;
    }

    err = bt_le_scan_stop();
    if (err) {
        printk(HOST_TAG "scan stop failed (err %d)\n", err);
        return;
    }

    err = bt_conn_le_create(addr, BT_CONN_LE_CREATE_CONN, BT_LE_CONN_PARAM_DEFAULT, &default_conn);
    if (err) {
        printk(HOST_TAG "connect request failed (err %d)\n", err);
        atomic_set(&connect_started, 0);
        return;
    }
    printk(HOST_TAG "connect requested to %s\n", addr_str);
}

static void connected(struct bt_conn *conn, uint8_t err) {
    char addr_str[BT_ADDR_LE_STR_LEN];
    int sec_err;

    bt_addr_le_to_str(bt_conn_get_dst(conn), addr_str, sizeof(addr_str));

    if (err) {
        printk(HOST_TAG "connect failed to %s (err %u)\n", addr_str, err);
        bt_conn_unref(default_conn);
        default_conn = NULL;
        return;
    }

    printk(HOST_TAG "connected to %s\n", addr_str);

    /* 実機のホストと同じく、接続後すぐ暗号化を要求する。 */
    sec_err = bt_conn_set_security(conn, BT_SECURITY_L2);
    if (sec_err) {
        printk(HOST_TAG "security request failed (err %d)\n", sec_err);
    }
}

static void disconnected(struct bt_conn *conn, uint8_t reason) {
    char addr_str[BT_ADDR_LE_STR_LEN];

    bt_addr_le_to_str(bt_conn_get_dst(conn), addr_str, sizeof(addr_str));
    printk(HOST_TAG "disconnected from %s (reason 0x%02x)\n", addr_str, reason);

    if (default_conn) {
        bt_conn_unref(default_conn);
        default_conn = NULL;
    }
}

static void security_changed(struct bt_conn *conn, bt_security_t level, enum bt_security_err err) {
    if (err) {
        printk(HOST_TAG "security failed (level %u, err %d)\n", level, err);
        return;
    }
    printk(HOST_TAG "security level %u\n", level);
}

BT_CONN_CB_DEFINE(conn_callbacks) = {
    .connected = connected,
    .disconnected = disconnected,
    .security_changed = security_changed,
};

static void pairing_complete(struct bt_conn *conn, bool bonded) {
    printk(HOST_TAG "paired (bonded %s)\n", bonded ? "yes" : "no");
}

static void pairing_failed(struct bt_conn *conn, enum bt_security_err reason) {
    printk(HOST_TAG "pairing failed (reason %d)\n", reason);
}

static struct bt_conn_auth_info_cb auth_info_cb = {
    .pairing_complete = pairing_complete,
    .pairing_failed = pairing_failed,
};

int main(void) {
    int err;

    err = bt_enable(NULL);
    if (err) {
        printk(HOST_TAG "bt_enable failed (err %d)\n", err);
        return 0;
    }
    printk(HOST_TAG "bluetooth ready\n");

    err = bt_conn_auth_info_cb_register(&auth_info_cb);
    if (err) {
        printk(HOST_TAG "auth info cb register failed (err %d)\n", err);
    }

    /* 広告に載った名前も見たいので active スキャンにする。 */
    err = bt_le_scan_start(BT_LE_SCAN_ACTIVE, device_found);
    if (err) {
        printk(HOST_TAG "scan start failed (err %d)\n", err);
        return 0;
    }
    printk(HOST_TAG "scanning\n");

    /* 何も見つからないまま終わったことをログに残す。 */
    k_sleep(K_MSEC(CONNECT_TIMEOUT_MS));
    if (!atomic_get(&connect_started)) {
        printk(HOST_TAG "no HID advertiser found within %d ms\n", CONNECT_TIMEOUT_MS);
    }
    return 0;
}
