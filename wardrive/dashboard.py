"""LCD dashboard rendering for wardriving."""

import os
import subprocess
import time
from config import SCREEN_W, SCREEN_H, FONT_MENU, FONT_TITLE, BG_IMAGE


def get_active_theme_bg():
    """Get background from the active pager theme."""
    try:
        result = subprocess.run(
            ['uci', 'get', 'system.@pager[0].theme_path'],
            capture_output=True, text=True, timeout=5
        )
        theme_path = result.stdout.strip()
        if theme_path:
            bg = os.path.join(theme_path, 'assets', 'alert_dialog_bg_term_blue.png')
            if os.path.isfile(bg):
                return bg
    except Exception:
        pass
    for base in ('/root/themes', '/lib/pager/themes'):
        if not os.path.isdir(base):
            continue
        for name in os.listdir(base):
            bg = os.path.join(base, name, 'assets', 'alert_dialog_bg_term_blue.png')
            if os.path.isfile(bg):
                return bg
    return None


class Dashboard:
    """Renders the wardriving dashboard on the pager LCD."""

    def __init__(self, pager):
        self.pager = pager
        self.font = FONT_MENU
        self.title_font = FONT_TITLE
        # Use custom bg if exists, otherwise active pager theme
        if os.path.isfile(BG_IMAGE):
            self.bg_image = BG_IMAGE
        else:
            self.bg_image = get_active_theme_bg()

        # Colors
        self.WHITE = pager.rgb(255, 255, 255)
        self.GREEN = pager.rgb(0, 255, 0)
        self.CYAN = pager.rgb(100, 200, 255)
        self.YELLOW = pager.rgb(255, 220, 50)
        self.RED = pager.rgb(255, 60, 60)
        self.DIM = pager.rgb(120, 120, 120)
        self.ORANGE = pager.rgb(255, 160, 40)

    def render(self, stats, gps, elapsed, current_channel, interface, bands, scan_mode='active', battery=None, gps_enabled=True):
        """Draw one frame of the dashboard."""
        # Background
        if self.bg_image:
            try:
                self.pager.draw_image_file_scaled(0, 0, SCREEN_W, SCREEN_H, self.bg_image)
            except Exception:
                self.pager.clear(self.pager.BLACK)
        else:
            self.pager.clear(self.pager.BLACK)

        fs = 18  # stat font size

        # Left column — AP stats, values aligned in column
        x_left = 35
        left_val_x = x_left + 70  # Fixed column for values
        y = 30

        wpa_total = stats['wpa2'] + stats['wpa3']
        self._draw_label_value(x_left, left_val_x, y, "APs", str(stats['total']), fs, self.DIM, self.GREEN)
        y += 24
        self._draw_label_value(x_left, left_val_x, y, "Open", str(stats['open']), fs, self.DIM, self.RED)
        y += 24
        self._draw_label_value(x_left, left_val_x, y, "WEP", str(stats['wep']), fs, self.DIM, self.ORANGE)
        y += 24
        self._draw_label_value(x_left, left_val_x, y, "WPA", str(wpa_total), fs, self.DIM, self.CYAN)
        y += 24
        self._draw_label_value(x_left, left_val_x, y, "HS", str(stats['handshakes']), fs, self.DIM, self.YELLOW)

        # Right column — GPS and session
        x_right = 260
        y = 30

        # GPS info — always show all fields, values aligned in column
        if not gps_enabled:
            fix_text, fix_color = "OFF", self.DIM
        elif gps.fix_mode >= 3:
            fix_text, fix_color = "3D Fix", self.GREEN
        elif gps.fix_mode >= 2:
            fix_text, fix_color = "2D Fix", self.YELLOW
        else:
            fix_text, fix_color = "No Fix", self.RED

        val_x = x_right + 70  # Fixed column for values

        self._draw_label_value(x_right, val_x, y, "GPS", fix_text, fs, self.DIM, fix_color)
        y += 24
        self._draw_label_value(x_right, val_x, y, "Lat", f"{gps.lat:.4f}", fs, self.DIM, self.WHITE)
        y += 24
        self._draw_label_value(x_right, val_x, y, "Lon", f"{gps.lon:.4f}", fs, self.DIM, self.WHITE)
        y += 24
        speed_mph = gps.speed * 2.237 if gps.has_fix else 0
        self._draw_label_value(x_right, val_x, y, "Spd", f"{speed_mph:.0f}mph", fs, self.DIM, self.WHITE)
        y += 24
        self._draw_label_value(x_right, val_x, y, "Sats", str(gps.satellites), fs, self.DIM, self.CYAN)

        # Bottom row — channel, mode, elapsed (center), battery (right)
        bot_y = 174
        bot_fs = 16
        ch_str = f"CH:{current_channel}" if current_channel else "CH:--"
        mode_label = "STL" if scan_mode == 'stealth' else "ACT"
        elapsed_str = self._format_elapsed(elapsed)

        # Left: channel + mode + scan status
        self.pager.draw_ttf(35, bot_y, ch_str, self.DIM, self.font, bot_fs)
        self.pager.draw_ttf(100, bot_y, mode_label, self.DIM, self.font, bot_fs)

        # Center: elapsed time
        ew = self.pager.ttf_width(elapsed_str, self.font, bot_fs)
        self.pager.draw_ttf((SCREEN_W - ew) // 2, bot_y, elapsed_str, self.DIM, self.font, bot_fs)

        # Right: battery
        if battery is not None:
            bat_str = f"{battery}%"
            bw = self.pager.ttf_width(bat_str, self.font, bot_fs)
            bat_color = self.GREEN if battery > 50 else self.YELLOW if battery > 20 else self.RED
            self.pager.draw_ttf(SCREEN_W - bw - 35, bot_y, bat_str, bat_color, self.font, bot_fs)

        self.pager.flip()

    def _draw_stat(self, x, y, label, value, fs, label_color, value_color):
        """Draw a label: value pair (staggered)."""
        self.pager.draw_ttf(x, y, f"{label}:", label_color, self.font, fs)
        lw = self.pager.ttf_width(f"{label}: ", self.font, fs)
        self.pager.draw_ttf(x + lw, y, value, value_color, self.font, fs + 2)

    def _draw_label_value(self, label_x, val_x, y, label, value, fs, label_color, value_color):
        """Draw label and value at fixed column positions."""
        self.pager.draw_ttf(label_x, y, f"{label}:", label_color, self.font, fs)
        self.pager.draw_ttf(val_x, y, value, value_color, self.font, fs)

    def _band_string(self, bands):
        """Format active bands."""
        parts = []
        if bands.get('2.4'):
            parts.append('2.4')
        if bands.get('5'):
            parts.append('5')
        if bands.get('6'):
            parts.append('6')
        return '+'.join(parts) + 'GHz' if parts else 'No band'

    def _format_elapsed(self, seconds):
        """Format elapsed seconds as HH:MM:SS."""
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{h:02d}:{m:02d}:{s:02d}"
