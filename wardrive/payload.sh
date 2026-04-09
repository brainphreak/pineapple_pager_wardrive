#!/bin/sh
# Title: Wardrive
# Description: Wardriving dashboard with GPS, handshake capture, and Wigle upload
# Author: brAinphreAk
# Version: 1.0
# Category: Reconnaissance
# Library: libpagerctl.so (pagerctl)

_PAYLOAD_TITLE="Wardrive"
_PAYLOAD_AUTHOR_NAME="brAinphreAk"
_PAYLOAD_VERSION="1.0"
_PAYLOAD_DESCRIPTION="Wardriving Dashboard - GPS, WiFi scanning, handshake capture"

PAYLOAD_DIR="/root/payloads/user/reconnaissance/wardrive"
DATA_DIR="$PAYLOAD_DIR/data"

cd "$PAYLOAD_DIR" || {
    LOG "red" "ERROR: $PAYLOAD_DIR not found"
    exit 1
}

# Setup pagerctl
PAGERCTL_FOUND=false
for dir in "$PAYLOAD_DIR/lib" "/mmc/root/payloads/user/reconnaissance/wardrive/lib"; do
    if [ -f "$dir/libpagerctl.so" ] && [ -f "$dir/pagerctl.py" ]; then
        PAGERCTL_DIR="$dir"
        PAGERCTL_FOUND=true
        break
    fi
done

if [ "$PAGERCTL_FOUND" = false ]; then
    LOG ""
    LOG "red" "=== MISSING DEPENDENCY ==="
    LOG "red" "libpagerctl.so / pagerctl.py not found!"
    LOG ""
    LOG "Press any button to exit..."
    WAIT_FOR_INPUT >/dev/null 2>&1
    exit 1
fi

# Environment
export PATH="/mmc/usr/bin:$PAYLOAD_DIR/bin:$PATH"
export PYTHONPATH="$PAYLOAD_DIR/lib:$PAYLOAD_DIR:$PYTHONPATH"
export LD_LIBRARY_PATH="/mmc/usr/lib:$PAYLOAD_DIR/lib:$LD_LIBRARY_PATH"

# Check Python3
if ! command -v python3 >/dev/null 2>&1; then
    LOG "red" "Python3 not found"
    LOG "green" "GREEN = Install"
    LOG "red" "RED = Exit"
    while true; do
        BUTTON=$(WAIT_FOR_INPUT 2>/dev/null)
        case "$BUTTON" in
            "GREEN"|"A")
                LOG "Installing Python3..."
                opkg update 2>&1 | while IFS= read -r line; do LOG "  $line"; done
                opkg -d mmc install python3 python3-ctypes 2>&1 | while IFS= read -r line; do LOG "  $line"; done
                if command -v python3 >/dev/null 2>&1; then
                    LOG "green" "Python3 installed!"
                    sleep 1
                    break
                else
                    LOG "red" "Failed"
                    sleep 2
                    exit 1
                fi
                ;;
            "RED"|"B") exit 0 ;;
        esac
    done
fi

# Info screen
LOG ""
LOG "green" "Wardrive v1.0"
LOG "cyan" "Wardriving Dashboard"
LOG ""
LOG "green" "GREEN = Start"
LOG "red" "RED = Exit"
LOG ""

while true; do
    BUTTON=$(WAIT_FOR_INPUT 2>/dev/null)
    case "$BUTTON" in
        "GREEN"|"A") break ;;
        "RED"|"B") LOG "Exiting."; exit 0 ;;
    esac
done

# Cleanup
cleanup() {
    if ! pgrep -x pineapple >/dev/null; then
        /etc/init.d/pineapplepager start 2>/dev/null
    fi
}
trap cleanup EXIT

# Create loot dirs
mkdir -p /mmc/root/loot/wardrive/captures
mkdir -p /mmc/root/loot/wardrive/exports

# Stop pager service
SPINNER_ID=$(START_SPINNER "Starting Wardrive...")
/etc/init.d/pineapplepager stop 2>/dev/null
sleep 0.5
STOP_SPINNER "$SPINNER_ID" 2>/dev/null

# Run
python3 wardrive.py

exit 0
