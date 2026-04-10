#!/usr/bin/env python3
"""Wardrive — Wardriving dashboard for WiFi Pineapple Pager."""

import os
import sys
import time
import queue
import threading

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lib'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pagerctl import Pager
from config import (load_config, save_config, ensure_dirs, DB_PATH, EXPORT_DIR,
                    CHANNELS_2_4, CHANNELS_5, CHANNELS_6)
from database import Database
from scanner import Scanner, PassiveScanner
from gps_module import GpsReader, GpsState
from capture import Capture
from dashboard import Dashboard
from settings_menu import SettingsMenu
from wigle_export import export_csv, upload_to_wigle, WigleWriter
from web_server import WebServer


class Wardrive:
    def __init__(self):
        self.config = load_config()
        ensure_dirs()

        # Pager display
        self.pager = Pager()
        self.pager.init()
        self.pager.set_rotation(270)
        try:
            self.pager.set_brightness(self.config.get('brightness', 80))
        except Exception:
            pass

        # Database
        self.db = Database(DB_PATH)

        # Shared state
        self.gps_state = GpsState()
        self.stop_event = threading.Event()
        self.scan_queue = queue.Queue()
        self.capture_queue = queue.Queue()

        # Threads (created on start)
        self.scanner = None
        self.gps_reader = None
        self.capture_thread = None

        # UI
        self.dashboard = Dashboard(self.pager)
        self.start_time = time.time()
        self.last_scan_time = ""
        self.current_channel = 0
        self.new_ap_count = 0  # New APs in last scan (for geiger sound)
        self.scan_state = 'stopped'  # 'scanning', 'paused', 'stopped'
        self.paused_elapsed = 0  # Accumulated time before pause
        self.wigle_writer = WigleWriter(EXPORT_DIR)

        # Screen timeout
        self.last_activity = time.time()
        self.screen_off = False

        # Web server for downloading loot
        self.web_server = None
        if self.config.get('web_server', True):
            self.web_server = WebServer(port=self.config.get('web_port', 8080))
            self.web_server.start()

    def _get_channels(self):
        """Build channel list from config."""
        channels = []
        if self.config['scan_2_4ghz']:
            channels.extend(CHANNELS_2_4)
        if self.config['scan_5ghz']:
            channels.extend(CHANNELS_5)
        if self.config['scan_6ghz']:
            channels.extend(CHANNELS_6)
        return channels or CHANNELS_2_4

    def _start_threads(self):
        """Start scanner, GPS, and capture threads."""
        # Scanner — active uses managed interface, stealth uses monitor
        channels = self._get_channels()
        if self.config.get('scan_mode', 'active') == 'stealth':
            self.scanner = PassiveScanner(
                self.config['capture_interface'],  # monitor interface for passive
                channels,
                self.config.get('hop_speed', 0.5),
                self.scan_queue,
                self.stop_event
            )
        else:
            self.scanner = Scanner(
                self.config['scan_interface'],
                channels,
                self.config['scan_interval'],
                self.scan_queue,
                self.stop_event
            )
        self.scanner.start()

        # GPS
        if self.config['gps_enabled']:
            self.gps_reader = GpsReader(
                self.config['gps_device'],
                self.config['gps_baud'],
                self.gps_state,
                self.stop_event
            )
            self.gps_reader.start()

        # Capture — uses monitor interface (for handshakes)
        if self.config['capture_enabled']:
            from config import CAPTURE_DIR
            self.capture_thread = Capture(
                self.config['capture_interface'],
                CAPTURE_DIR,
                self.capture_queue,
                self.stop_event
            )
            self.capture_thread.start()

    def _stop_threads(self):
        """Stop all background threads."""
        self.stop_event.set()
        if self.scanner:
            self.scanner.join(timeout=3)
        if self.gps_reader:
            self.gps_reader.stop()
            self.gps_reader.join(timeout=3)
        if self.capture_thread:
            self.capture_thread.stop()
            self.capture_thread.join(timeout=3)

    def _process_scan_results(self):
        """Drain scan queue and update database."""
        new_count = 0
        gps = self.gps_state.copy()

        while not self.scan_queue.empty():
            try:
                aps = self.scan_queue.get_nowait()
            except queue.Empty:
                break

            before = self.db.get_stats()['total']
            for ap in aps:
                self.db.upsert_ap(ap, gps)
                if ap.get('channel'):
                    self.current_channel = ap['channel']
            after = self.db.get_stats()['total']
            new_count += after - before

        self.new_ap_count = new_count
        return new_count

    def _process_captures(self):
        """Drain capture queue and mark handshakes."""
        while not self.capture_queue.empty():
            try:
                bssid = self.capture_queue.get_nowait()
                self.db.mark_handshake(bssid)
                # Handshake captured sound — distinct from geiger
                self._handshake_sound()
            except queue.Empty:
                break

    def _handshake_sound(self):
        """Play a distinct sound when a handshake is captured."""
        if not self.config.get('geiger_sound', True):
            return
        try:
            # Rising tone — clearly different from geiger clicks
            for freq in [800, 1000, 1200, 1500]:
                self.pager.beep(freq, 50)
                time.sleep(0.05)
        except Exception:
            pass

    def _show_scan_menu(self):
        """Show scan control popup with pause/stop/resume."""
        from config import SCREEN_W, SCREEN_H, FONT_TITLE, FONT_MENU
        selected = 0

        while True:
            # Build menu items based on current state
            if self.scan_state == 'scanning':
                items = ["Pause Scan", "Stop Scan", "Cancel"]
                status = "Scanning"
            elif self.scan_state == 'paused':
                items = ["Resume Scan", "Stop Scan", "Cancel"]
                status = "Paused"
            else:
                items = ["Start Scan", "Cancel"]
                status = "Stopped"

            if selected >= len(items):
                selected = 0

            # Draw
            if self.dashboard.bg_image:
                try:
                    self.pager.draw_image_file_scaled(0, 0, SCREEN_W, SCREEN_H, self.dashboard.bg_image)
                except Exception:
                    self.pager.clear(self.pager.BLACK)
            else:
                self.pager.clear(self.pager.BLACK)

            title_color = self.pager.rgb(100, 200, 255)
            sel_color = self.pager.rgb(0, 255, 0)
            unsel_color = self.pager.rgb(255, 255, 255)

            tw = self.pager.ttf_width(status, FONT_TITLE, 28)
            self.pager.draw_ttf((SCREEN_W - tw) // 2, 40, status, title_color, FONT_TITLE, 28)

            for i, item in enumerate(items):
                y = 85 + i * 24
                color = sel_color if i == selected else unsel_color
                tw = self.pager.ttf_width(item, FONT_MENU, 18)
                self.pager.draw_ttf((SCREEN_W - tw) // 2, y, item, color, FONT_MENU, 18)

            self.pager.flip()

            button = self.pager.wait_button()
            if button & self.pager.BTN_UP:
                if selected > 0:
                    selected -= 1
            elif button & self.pager.BTN_DOWN:
                if selected < len(items) - 1:
                    selected += 1
            elif button & self.pager.BTN_A:
                action = items[selected]
                if action == "Pause Scan":
                    self.scan_state = 'paused'
                    # Freeze timer — save elapsed so far
                    self.paused_elapsed += int(time.time() - self.start_time)
                    self._stop_threads()
                    try:
                        self.pager.beep(600, 150)
                    except Exception:
                        pass
                    return
                elif action == "Resume Scan":
                    self.scan_state = 'scanning'
                    # Resume timer from where we paused
                    self.start_time = time.time()
                    self.stop_event.clear()
                    self._start_threads()
                    try:
                        self.pager.beep(1000, 150)
                    except Exception:
                        pass
                    return
                elif action == "Stop Scan":
                    self.scan_state = 'stopped'
                    self._stop_threads()
                    self._archive_session()
                    # Reset timer
                    self.start_time = time.time()
                    self.paused_elapsed = 0
                    try:
                        self.pager.beep(400, 200)
                    except Exception:
                        pass
                    return
                elif action == "Start Scan":
                    self.scan_state = 'scanning'
                    self.wigle_writer.start_session()
                    self.stop_event.clear()
                    self._start_threads()
                    # Fresh timer
                    self.start_time = time.time()
                    self.paused_elapsed = 0
                    try:
                        self.pager.beep(1000, 200)
                    except Exception:
                        pass
                    return
                elif action == "Cancel":
                    return
            elif button & self.pager.BTN_B:
                return

    def _get_battery(self):
        """Read battery percentage (0-100) or None."""
        import glob as _glob
        try:
            for bat_path in _glob.glob('/sys/class/power_supply/*/capacity'):
                with open(bat_path, 'r') as f:
                    return int(f.read().strip())
        except Exception:
            pass
        try:
            result = subprocess.run(['ubus', 'call', 'battery', 'info'],
                                    capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                import json as _json
                data = _json.loads(result.stdout)
                return int(data.get('percent', data.get('capacity', -1)))
        except Exception:
            pass
        return None

    def _geiger_sound(self, new_count):
        """Play geiger counter clicks based on new AP count."""
        if not self.config.get('geiger_sound', True):
            return
        if new_count <= 0:
            return

        # More new APs = more rapid clicks
        clicks = min(new_count, 10)  # Cap at 10 clicks
        for i in range(clicks):
            try:
                freq = 600 + (i * 50)  # Slightly varying pitch
                self.pager.beep(freq, 15)  # Very short click
                time.sleep(0.05)
            except Exception:
                break

    def _export_callback(self):
        """Export to Wigle CSV."""
        try:
            filepath = export_csv(self.db, EXPORT_DIR)
            return f"Exported: {os.path.basename(filepath)}"
        except Exception as e:
            return f"Export failed: {e}"

    def _upload_callback(self):
        """Upload latest export to Wigle."""
        key = self.config.get('wigle_api_key', '')
        if not key:
            return "No API key set"
        # Find latest export
        try:
            exports = sorted([f for f in os.listdir(EXPORT_DIR) if f.endswith('.csv')])
            if not exports:
                return "No exports found"
            filepath = os.path.join(EXPORT_DIR, exports[-1])
            success, msg = upload_to_wigle(filepath, key)
            return msg
        except Exception as e:
            return f"Upload failed: {e}"

    def _ask_session(self):
        """Ask user to start new session or continue previous."""
        # Check if there's existing data
        existing = 0
        try:
            existing = self.db.get_stats()['total']
        except Exception:
            pass

        if existing == 0:
            return  # No existing data, just start fresh

        from config import SCREEN_W, SCREEN_H
        selected = 0  # 0=Continue, 1=New Session
        items = [f"Continue ({existing} APs)", "New Session"]

        while True:
            # Draw
            if self.dashboard.bg_image:
                try:
                    self.pager.draw_image_file_scaled(0, 0, SCREEN_W, SCREEN_H, self.dashboard.bg_image)
                except Exception:
                    self.pager.clear(self.pager.BLACK)
            else:
                self.pager.clear(self.pager.BLACK)

            from config import FONT_TITLE, FONT_MENU
            title_color = self.pager.rgb(100, 200, 255)
            sel_color = self.pager.rgb(0, 255, 0)
            unsel_color = self.pager.rgb(255, 255, 255)

            tw = self.pager.ttf_width("Wardrive", FONT_TITLE, 28)
            self.pager.draw_ttf((SCREEN_W - tw) // 2, 28, "Wardrive", title_color, FONT_TITLE, 28)

            for i, item in enumerate(items):
                y = 80 + i * 24
                color = sel_color if i == selected else unsel_color
                tw = self.pager.ttf_width(item, FONT_MENU, 18)
                self.pager.draw_ttf((SCREEN_W - tw) // 2, y, item, color, FONT_MENU, 18)

            self.pager.flip()

            button = self.pager.wait_button()
            if button & self.pager.BTN_UP or button & self.pager.BTN_DOWN:
                selected = 1 - selected
            elif button & self.pager.BTN_A:
                if selected == 1:
                    # New session — archive DB, start new wigle file
                    self._archive_session()
                    self.wigle_writer.start_session()
                else:
                    # Continue — resume existing wigle file
                    latest = self.wigle_writer.get_latest_file()
                    if latest:
                        self.wigle_writer.resume_session(latest)
                    else:
                        self.wigle_writer.start_session()
                return

    def _archive_session(self):
        """Archive current DB and exports, start fresh."""
        from datetime import datetime
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')

        # Close current DB
        self.db.close()

        # Rename DB
        if os.path.isfile(DB_PATH):
            archive_path = DB_PATH.replace('.db', f'_{timestamp}.db')
            os.rename(DB_PATH, archive_path)

        # Rename latest CSV
        latest_csv = os.path.join(EXPORT_DIR, 'wardrive_latest.csv')
        if os.path.isfile(latest_csv):
            os.rename(latest_csv, os.path.join(EXPORT_DIR, f'wardrive_{timestamp}.csv'))

        # Reopen fresh DB
        self.db = Database(DB_PATH)

    def run(self):
        """Main run loop."""
        self._ask_session()

        # If no wigle file started yet (first run with empty DB), start one
        if not self.wigle_writer.filepath:
            self.wigle_writer.start_session()

        # Start scanning immediately
        self.scan_state = 'scanning'
        self._start_threads()

        try:
            while True:
                if self.scan_state == 'scanning':
                    # Process background data
                    new_aps = self._process_scan_results()
                    self._process_captures()
                    self.db.correlate_open_bssids()

                    # Append new APs to wigle CSV in real-time
                    if new_aps > 0:
                        all_aps = self.db.get_all_aps()
                        self.wigle_writer.append_aps(all_aps)

                    # Geiger counter sound
                    self._geiger_sound(new_aps)

                # Get stats for dashboard
                stats = self.db.get_stats()
                gps = self.gps_state.copy()
                if self.scan_state == 'paused':
                    elapsed = self.paused_elapsed
                else:
                    elapsed = self.paused_elapsed + int(time.time() - self.start_time)
                bands = {
                    '2.4': self.config['scan_2_4ghz'],
                    '5': self.config['scan_5ghz'],
                    '6': self.config['scan_6ghz'],
                }

                # Render dashboard
                scan_mode = self.config.get('scan_mode', 'active')
                iface = self.config['capture_interface'] if scan_mode == 'stealth' else self.config['scan_interface']
                battery = self._get_battery()
                self.dashboard.render(
                    stats, gps, elapsed,
                    self.current_channel,
                    iface, bands, scan_mode, battery
                )

                # Screen timeout
                screen_timeout = self.config.get('screen_timeout', 60)
                if screen_timeout > 0 and time.time() - self.last_activity > screen_timeout and not self.screen_off:
                    self.pager.set_brightness(0)
                    self.screen_off = True

                # Check for input — poll rapidly to catch button presses
                pressed = 0
                for _ in range(5):
                    _, p, _ = self.pager.poll_input()
                    pressed |= p
                    if pressed:
                        break
                    time.sleep(0.02)

                if pressed:
                    # Any button wakes screen
                    if self.screen_off:
                        self.pager.set_brightness(self.config.get('brightness', 80))
                        self.screen_off = False
                        self.last_activity = time.time()
                    else:
                        self.last_activity = time.time()
                        if pressed & self.pager.BTN_A:
                            self._show_scan_menu()
                        elif pressed & self.pager.BTN_B:
                            # Scan keeps running in background
                            settings = SettingsMenu(self.pager, self.config, self.gps_reader)
                            result = settings.show(
                                export_callback=self._export_callback,
                                upload_callback=self._upload_callback
                            )
                            if result == '__exit__':
                                break
                            self.config = result
                            for _ in range(3):
                                self.pager.poll_input()
                                time.sleep(0.05)

        except KeyboardInterrupt:
            pass
        finally:
            self._stop_threads()
            if self.web_server:
                self.web_server.stop()
            self.db.close()
            self.pager.clear(self.pager.BLACK)
            self.pager.flip()
            self.pager.cleanup()


def main():
    app = Wardrive()
    app.run()


if __name__ == '__main__':
    main()
