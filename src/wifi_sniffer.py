"""WiFi MAC sniffer for vehicle correlation."""

import json
import os
import select
import subprocess
import threading
import time
from collections import defaultdict

from .config import load_config


class WiFiSniffer:
    """Captures WiFi MAC addresses from USB sniffer device."""

    def __init__(self, dashboard=None):
        cfg = load_config()
        self.enabled = cfg.get("wifi_sniffer", {}).get("enabled", False)
        self.device = cfg.get("wifi_sniffer", {}).get("device", "/dev/ttyUSB0")
        self.bssid_list = set()
        self.station_macs = set()
        self.static_macs = set()
        self._running = False
        self._thread = None
        self._mac_history = defaultdict(list)
        self._history_window = cfg.get("wifi_sniffer", {}).get("history_window", 3600)
        self.dashboard = dashboard

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
            import serial
            ser = None
            try:
                ser = serial.Serial(self.device, 9600, timeout=0.5)
                while True:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if not line:
                        break
                    try:
                        data = json.loads(line)
                        if data.get("type") == "wifi" and "bssid" in data:
                            mac = data["bssid"].lower()
                            if mac not in self.bssid_list:
                                self.station_macs.add(mac)
                    except json.JSONDecodeError:
                        pass
            finally:
                if ser:
                    ser.close()
        except ImportError:
            try:
                with open(self.device, 'r', encoding='utf-8', errors='ignore') as f:
                    while True:
                        readable, _, _ = select.select([f], [], [], 0.5)
                        if not readable:
                            break
                        line = f.readline().strip()
                        try:
                            data = json.loads(line)
                            if data.get("type") == "wifi" and "bssid" in data:
                                mac = data["bssid"].lower()
                                if mac not in self.bssid_list:
                                    self.station_macs.add(mac)
                        except json.JSONDecodeError:
                            pass
            except Exception as e:
                print(f"[wifi] Sniffer error: {e}")
        except Exception as e:
            print(f"[wifi] Serial error: {e}")

    def _detect_static_macs(self):
        """Detect static MACs from history."""
        for mac, timestamps in self._mac_history.items():
            if len(timestamps) > 3:
                self.static_macs.add(mac)

    def start(self):
        """Start the WiFi sniffer."""
        if not self.enabled:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        print("[wifi] Sniffer started")

    def stop(self):
        """Stop the WiFi sniffer."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        print("[wifi] Sniffer stopped")

    def _run(self):
        """Main sniffer loop."""
        while self._running:
            try:
                self._parse_sniffer_output()

                now = time.time()
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
                        event = {
                            "mac": mac,
                            "type": "station",
                            "is_static": mac in self.static_macs,
                            "timestamp": now,
                        }
                        self.dashboard.add_wifi_event(event)

                time.sleep(1)
            except Exception as e:
                print(f"[wifi] Loop error: {e}")

    def get_dynamic_macs(self):
        """Return MACs that are not static."""
        return self.station_macs - self.static_macs

    def get_static_macs(self):
        """Return MACs identified as static."""
        return self.static_macs.copy()

    @property
    def stats(self):
        return {
            "enabled": self.enabled,
            "bssids": len(self.bssid_list),
            "stations": len(self.station_macs),
            "static_macs": len(self.static_macs),
            "dynamic_macs": len(self.get_dynamic_macs()),
        }