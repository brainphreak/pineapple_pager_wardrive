"""Settings persistence and constants for Wardrive."""

import json
import os

PAYLOAD_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(PAYLOAD_DIR, 'settings.json')
LOOT_DIR = '/mmc/root/loot/wardrive'
DB_PATH = os.path.join(LOOT_DIR, 'wardrive.db')
CAPTURE_DIR = os.path.join(LOOT_DIR, 'captures')
EXPORT_DIR = os.path.join(LOOT_DIR, 'exports')

# Screen
SCREEN_W = 480
SCREEN_H = 222

# Fonts
FONT_TITLE = os.path.join(PAYLOAD_DIR, 'fonts', 'title.TTF')
FONT_MENU = os.path.join(PAYLOAD_DIR, 'fonts', 'menu.ttf')

# Images
BG_IMAGE = os.path.join(PAYLOAD_DIR, 'images', 'wardriving_bg.png')

# WiFi channels by band
CHANNELS_2_4 = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
CHANNELS_5 = [36, 40, 44, 48, 52, 56, 60, 64, 100, 104, 108, 112, 116, 120, 124, 128, 132, 136, 140, 149, 153, 157, 161, 165]
CHANNELS_6 = [1, 5, 9, 13, 17, 21, 25, 29, 33, 37, 41, 45, 49, 53, 57, 61, 65, 69, 73, 77, 81, 85, 89, 93]

DEFAULTS = {
    'gps_enabled': True,
    'gps_device': '',  # Auto-detected on first run
    'gps_baud': 'auto',
    'scan_2_4ghz': True,
    'scan_5ghz': True,
    'scan_6ghz': False,
    'scan_mode': 'stealth',  # 'stealth' (passive, all bands) or 'active' (iw scan, 2.4GHz only w/o dongle)
    'hop_speed': 0.5,  # seconds per channel in stealth mode
    'capture_enabled': False,
    'scan_interface': 'wlan0',
    'capture_interface': 'wlan1mon',
    'wigle_api_name': '',
    'wigle_api_token': '',
    'scan_interval': 5,
    'geiger_sound': True,
    'brightness': 80,
    'screen_timeout': 60,  # seconds, 0 = never
    'web_server': True,
    'web_port': 8080,
}


def load_config():
    """Load settings from disk, with defaults for missing keys."""
    config = dict(DEFAULTS)
    if os.path.isfile(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                saved = json.load(f)
            config.update(saved)
        except Exception:
            pass
    return config


def save_config(config):
    """Save settings to disk."""
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(config, f, indent=2)
    except Exception:
        pass


def ensure_dirs():
    """Create loot directories if they don't exist."""
    for d in [LOOT_DIR, CAPTURE_DIR, EXPORT_DIR]:
        os.makedirs(d, exist_ok=True)
