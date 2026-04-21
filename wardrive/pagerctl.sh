#!/bin/sh
# Title: Wardrive
# Description: Wardriving dashboard with GPS, handshake capture, and Wigle upload
# Author: brAinphreAk
# Version: 1.0
# Category: Reconnaissance
# Library: libpagerctl.so (pagerctl)
#
# Pagerctl-native launcher. pagerctl_home has already torn the pager
# down and stopped pineapplepager — we own the screen directly via
# libpagerctl.so. Skips the duckyscript splash/install flow from
# payload.sh; dependency failures exit quietly back to pagerctl_home.

PAYLOAD_DIR="/root/payloads/user/reconnaissance/wardrive"
DATA_DIR="$PAYLOAD_DIR/data"

cd "$PAYLOAD_DIR" || exit 1

export PATH="/mmc/usr/bin:$PAYLOAD_DIR/bin:$PATH"
export PYTHONPATH="$PAYLOAD_DIR/lib:$PAYLOAD_DIR:$PYTHONPATH"
export LD_LIBRARY_PATH="/mmc/usr/lib:$PAYLOAD_DIR/lib:$LD_LIBRARY_PATH"

command -v python3 >/dev/null 2>&1 || exit 1
python3 -c "import ctypes" 2>/dev/null || exit 1
python3 -c "import sqlite3" 2>/dev/null || exit 1

mkdir -p /mmc/root/loot/wardrive/captures 2>/dev/null
mkdir -p /mmc/root/loot/wardrive/exports 2>/dev/null
mkdir -p "$DATA_DIR" 2>/dev/null

python3 wardrive.py
exit 0
