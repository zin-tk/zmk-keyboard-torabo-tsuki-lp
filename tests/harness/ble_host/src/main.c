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
 *   5. HID レポート特性(0x2A4D)を購読し、届いたレポートを出力する
 *
 * 各段階で "HOST: " 付きの行を出す。run_split_tests.sh がこれを見て判定する。
 */

#include <string.h>

#include <zephyr/bluetooth/att.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/gap.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/byteorder.h>
#include <zephyr/sys/printk.h>

/* 判定に使う接頭辞。変えるときは run_split_tests.sh も合わせること。 */
#define HOST_TAG "HOST: "

/* 見つけてから接続要求を出すまでの猶予。bsim なので実時間ではない。 */
#define CONNECT_TIMEOUT_MS 5000

/* ZMK が出すレポート特性はキーボード/コンシューマ/マウスで、多くても数本。 */
#define MAX_REPORTS 4

/* レポート 1 本の長さは HKRO で 8 バイト程度。余裕を見てこの長さまで表示する。 */
#define MAX_REPORT_LEN 16

static struct bt_conn *default_conn;
/* 広告は繰り返し届くので、接続要求は 1 回だけに絞る。 */
static atomic_t connect_started;

/* HID サービスの探索と購読で使う状態。接続は 1 本だけなので静的に持つ。 */
static struct bt_gatt_discover_params discover_params;
static struct bt_uuid_16 discover_uuid = BT_UUID_INIT_16(0);
static uint16_t hids_end_handle;
static uint16_t report_handles[MAX_REPORTS];
static uint8_t report_count;
static uint8_t subscribe_index;
static struct bt_gatt_subscribe_params subscribe_params[MAX_REPORTS];
static struct bt_gatt_discover_params ccc_discover_params[MAX_REPORTS];

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

static void subscribe_next(struct bt_conn *conn);

static uint8_t report_received(struct bt_conn *conn, struct bt_gatt_subscribe_params *params,
                               const void *data, uint16_t length) {
    const uint8_t *bytes = data;
    /* "%02x " が 1 バイトあたり 3 文字。 */
    char hex[MAX_REPORT_LEN * 3 + 1];
    size_t shown = MIN(length, MAX_REPORT_LEN);
    size_t pos = 0;

    if (!data) {
        printk(HOST_TAG "unsubscribed from 0x%04x\n", params->value_handle);
        return BT_GATT_ITER_STOP;
    }

    for (size_t i = 0; i < shown; i++) {
        pos += snprintk(&hex[pos], sizeof(hex) - pos, "%02x ", bytes[i]);
    }
    if (pos > 0) {
        hex[pos - 1] = '\0';
    } else {
        hex[0] = '\0';
    }

    printk(HOST_TAG "report 0x%04x (%u bytes): %s\n", params->value_handle, length, hex);
    return BT_GATT_ITER_CONTINUE;
}

static void subscribe_done(struct bt_conn *conn, uint8_t err,
                           struct bt_gatt_subscribe_params *params) {
    if (err) {
        printk(HOST_TAG "subscribe to 0x%04x failed (att err 0x%02x)\n", params->value_handle,
               err);
    } else {
        printk(HOST_TAG "subscribed to report 0x%04x\n", params->value_handle);
    }
    subscribe_index++;
    subscribe_next(conn);
}

/* ATT のやり取りは 1 本ずつ進める。完了コールバックから次を呼ぶ。 */
static void subscribe_next(struct bt_conn *conn) {
    struct bt_gatt_subscribe_params *params;
    uint8_t i = subscribe_index;
    int err;

    if (i >= report_count) {
        printk(HOST_TAG "subscribed to %u report(s)\n", report_count);
        return;
    }

    params = &subscribe_params[i];
    params->notify = report_received;
    params->subscribe = subscribe_done;
    params->value_handle = report_handles[i];
    /* CCC のハンドルは Zephyr に探させる (CONFIG_BT_GATT_AUTO_DISCOVER_CCC)。 */
    params->ccc_handle = BT_GATT_AUTO_DISCOVER_CCC_HANDLE;
    params->end_handle = hids_end_handle;
    params->disc_params = &ccc_discover_params[i];
    params->value = BT_GATT_CCC_NOTIFY;
    params->min_security = BT_SECURITY_L2;

    err = bt_gatt_subscribe(conn, params);
    if (err && err != -EALREADY) {
        printk(HOST_TAG "subscribe to 0x%04x failed (err %d)\n", report_handles[i], err);
        subscribe_index++;
        subscribe_next(conn);
    }
}

static uint8_t discover_report(struct bt_conn *conn, const struct bt_gatt_attr *attr,
                               struct bt_gatt_discover_params *params) {
    struct bt_gatt_chrc *chrc;

    if (!attr) {
        if (report_count == 0) {
            printk(HOST_TAG "no notifiable report characteristic found\n");
            return BT_GATT_ITER_STOP;
        }
        printk(HOST_TAG "found %u report characteristic(s)\n", report_count);
        subscribe_next(conn);
        return BT_GATT_ITER_STOP;
    }

    chrc = attr->user_data;
    if ((chrc->properties & BT_GATT_CHRC_NOTIFY) && report_count < MAX_REPORTS) {
        report_handles[report_count++] = chrc->value_handle;
    }
    return BT_GATT_ITER_CONTINUE;
}

static uint8_t discover_hids(struct bt_conn *conn, const struct bt_gatt_attr *attr,
                             struct bt_gatt_discover_params *params) {
    struct bt_gatt_service_val *service;
    int err;

    if (!attr) {
        printk(HOST_TAG "HID service not found\n");
        return BT_GATT_ITER_STOP;
    }

    service = attr->user_data;
    hids_end_handle = service->end_handle;
    printk(HOST_TAG "HID service at 0x%04x-0x%04x\n", attr->handle, service->end_handle);

    memcpy(&discover_uuid, BT_UUID_HIDS_REPORT, sizeof(discover_uuid));
    discover_params.uuid = &discover_uuid.uuid;
    discover_params.start_handle = attr->handle + 1;
    discover_params.end_handle = service->end_handle;
    discover_params.type = BT_GATT_DISCOVER_CHARACTERISTIC;
    discover_params.func = discover_report;

    err = bt_gatt_discover(conn, &discover_params);
    if (err) {
        printk(HOST_TAG "report discovery failed (err %d)\n", err);
    }
    return BT_GATT_ITER_STOP;
}

static void start_discovery(struct bt_conn *conn) {
    int err;

    memcpy(&discover_uuid, BT_UUID_HIDS, sizeof(discover_uuid));
    discover_params.uuid = &discover_uuid.uuid;
    discover_params.start_handle = BT_ATT_FIRST_ATTRIBUTE_HANDLE;
    discover_params.end_handle = BT_ATT_LAST_ATTRIBUTE_HANDLE;
    discover_params.type = BT_GATT_DISCOVER_PRIMARY;
    discover_params.func = discover_hids;

    err = bt_gatt_discover(conn, &discover_params);
    if (err) {
        printk(HOST_TAG "service discovery failed (err %d)\n", err);
    }
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

    /* HID の特性は暗号化必須なので、ここまで来てから探索を始める。 */
    if (level >= BT_SECURITY_L2 && report_count == 0) {
        start_discovery(conn);
    }
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
