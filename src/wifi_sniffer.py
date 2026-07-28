"""WiFi MAC sniffer for vehicle correlation."""

import json
import os
import select
import subprocess
import time
from collections import defaultdict

from .config import load_config


def is_valid_mac(mac):
    parts = mac.split(':')
    if len(parts) != 6:
        return False
    try:
        [int(p, 16) for p in parts]
        return True
    except ValueError:
        return False


def try_parse_mac(data):
    mac = data.get("bssid", "")
    if mac and is_valid_mac(mac.lower()):
        return mac.lower()
    return None


class WiFiSniffer:
    """Captures WiFi MAC addresses from USB sniffer device."""

    def __init__(self, dashboard=None):
        cfg = load_config()
        self.enabled = cfg.get("wifi_sniffer", {}).get("enabled", False)
        self.device = cfg.get("wifi_sniffer", {}).get("device", "/dev/ttyUSB0")
        self.bssid_list = set()
        self.station_macs = set()
        self.static_macs = set()
        self._mac_history = defaultdict(list)
        self._history_window = cfg.get("wifi_sniffer", {}).get("history_window", 3600)
        self._ssid_map = {}
        self._calibration_start = None
        self._calibration_state = "idle"
        self._calibration_macs = {"first": set(), "second": set()}
        self._running = False
        self._reported_macs = set()
        self._last_read = 0
        self._read_interval = 1.0
        self.dashboard = dashboard
        self._buffer = ""

        if self.enabled:
            print(f"[wifi] WiFi sniffer enabled (device: {self.device})")
        else:
            print("[wifi] WiFi sniffer disabled")

    def _scan_networks(self):
        """Scan for WiFi networks and get BSSIDs."""
        try:
            result = subprocess.run(
                ["iwlist", "wlan0", "scan"],
                capture_output=True, text=True, timeout=10
            )
            lines = result.stdout.split('\n')
            for line in lines:
                if line.strip().startswith('Address:'):
                    bssid = line.split(':')[1].strip()
                    self.bssid_list.add(bssid.lower())
        except Exception as e:
            print(f"[wifi] Scan error: {e}")

    def _parse_sniffer_output(self):
        """Parse WiFi sniffer JSON output for MAC addresses."""
        if not os.path.exists(self.device):
            return

        try:
            with open(self.device, encoding='utf-8', errors='ignore') as f:
                for _ in range(10):
                    readable, _, _ = select.select([f], [], [], 0.1)
                    if not readable:
                        break
                    try:
                        chunk = f.read(1024)
                        if not chunk:
                            continue
                        self._buffer += chunk
                    except:
                        continue
                
                while '\n' in self._buffer:
                    line, self._buffer = self._buffer.split('\n', 1)
                    line = line.strip()
                    if not line or not line.startswith('{'):
                        continue
                    try:
                        data = json.loads(line)
                        mac = try_parse_mac(data)
                        if mac:
                            if mac not in self.station_macs:
                                self.station_macs.add(mac)
                            ssid = data.get("ssid", "")
                            if mac not in self._ssid_map:
                                self._ssid_map[mac] = ssid
                    except json.JSONDecodeError:
                        pass
        except Exception as e:
            print(f"[wifi] Read error: {e}")

    def _detect_static_macs(self):
        """Detect static MACs from history."""
        for mac, timestamps in self._mac_history.items():
            if len(timestamps) > 3:
                self.static_macs.add(mac)

    def update(self):
        """Update WiFi sniffer state - call this from main loop."""
        if not self.enabled:
            return

        now = time.time()
        
        if now - self._last_read >= self._read_interval:
            self._last_read = now
            self._running = True
            self._parse_sniffer_output()

            for mac in list(self.station_macs):
                if mac not in self._mac_history:
                    self._mac_history[mac] = []
                self._mac_history[mac].append(now)

            self._detect_static_macs()

            for mac in list(self._mac_history.keys()):
                self._mac_history[mac] = [
                    t for t in self._mac_history[mac]
                    if now - t < self._history_window
                ]

        if self.dashboard:
            for mac in self.station_macs:
                if mac not in self.static_macs and mac not in self._reported_macs:
                    self._reported_macs.add(mac)
                    event = {
                        "mac": mac,
                        "type": "station",
                        "is_static": False,
                        "ssid": self._ssid_map.get(mac, ""),
                        "timestamp": now,
                    }
                    self.dashboard.add_wifi_event(event)

        if self._calibration_start is not None:
            elapsed = time.time() - self._calibration_start
            if self._calibration_state == "first_session":
                if elapsed >= self._calibration_duration:
                    self._calibration_macs["first"] = set(self.station_macs)
                    self._calibration_state = "waiting"
                    self._calibration_start = time.time()
                    print(f"[wifi] First session: {len(self._calibration_macs['first'])} MACs")
            elif self._calibration_state == "waiting":
                if elapsed >= 30:
                    self._calibration_state = "second_session"
                    self._calibration_start = time.time()
            elif self._calibration_state == "second_session":
                if elapsed >= self._calibration_duration:
                    self._calibration_macs["second"] = set(self.station_macs)
                    static = self._calibration_macs["first"] & self._calibration_macs["second"]
                    self.static_macs.update(static)
                    self._calibration_state = "idle"
                    self._calibration_start = None
                    print(f"[wifi] Calibration complete: {len(static)} static MACs")

    def get_dynamic_macs(self):
        """Return MACs that are not static."""
        return self.station_macs - self.static_macs

    def get_static_macs(self):
        """Return MACs identified as static."""
        return self.static_macs.copy()

    def get_dynamic_macs_with_ssid(self):
        """Return dynamic MACs with their SSIDs."""
        dynamic = []
        for mac in self.get_dynamic_macs():
            ssid = self._ssid_map.get(mac, "")
            dynamic.append((mac, ssid))
        return dynamic

    def start_calibration(self, duration_seconds=30):
        """Start MAC calibration process: duration_seconds, wait, duration_seconds."""
        if self._calibration_start is not None:
            print("[wifi] Calibration already in progress")
            return
        
        self._calibration_state = "first_session"
        self._calibration_start = time.time()
        self._calibration_macs = {"first": set(), "second": set()}
        self._calibration_duration = duration_seconds
        print(f"[wifi] Starting calibration: {duration_seconds}s + 30s wait + {duration_seconds}s")

    def is_calibrating(self):
        """Check if calibration is in progress."""
        return self._calibration_start is not None

    @property
    def stats(self):
        return {
            "enabled": self.enabled,
            "bssids": len(self.bssid_list),
            "stations": len(self.station_macs),
            "static_macs": len(self.static_macs),
            "dynamic_macs": len(self.get_dynamic_macs()),
            "calibrating": self.is_calibrating(),
        }