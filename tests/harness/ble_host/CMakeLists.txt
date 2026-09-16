# Tier B のホスト役(4台目)。nrf52_bsim 上で動く最小の BLE セントラル。
cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(tier_b_ble_host)

target_sources(app PRIVATE src/main.c)
