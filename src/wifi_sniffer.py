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
        self._calibration_thread = None
        self._calibrating = False
        self._mac_history = defaultdict(list)
        self._history_window = cfg.get("wifi_sniffer", {}).get("history_window", 3600)
        self._ssid_map = {}
        self._calibration_sessions = []
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
            print(f"[wifi] Device not found: {self.device}")
            return

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

        def try_read_serial():
            import serial
            ser = None
            try:
                ser = serial.Serial(self.device, 9600, timeout=0.5)
                lines_read = 0
                while lines_read < 10:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if not line:
                        break
                    lines_read += 1
                    if not line.startswith('{'):
                        continue
                    try:
                        data = json.loads(line)
                        mac = try_parse_mac(data)
                        if mac:
                            if mac not in self.station_macs:
                                self.station_macs.add(mac)
                                self._mac_history[mac] = []
                            ssid = data.get("ssid", "")
                            if mac not in self._ssid_map:
                                self._ssid_map[mac] = ssid
                            print(f"[wifi] Found MAC: {mac}")
                    except json.JSONDecodeError:
                        pass
            finally:
                if ser:
                    ser.close()

        def try_read_file():
            with open(self.device, encoding='utf-8', errors='ignore') as f:
                lines_read = 0
                while lines_read < 10:
                    readable, _, _ = select.select([f], [], [], 0.5)
                    if not readable:
                        break
                    line = f.readline().strip()
                    lines_read += 1
                    if not line.startswith('{'):
                        continue
                    try:
                        data = json.loads(line)
                        mac = try_parse_mac(data)
                        if mac:
                            if mac not in self.station_macs:
                                self.station_macs.add(mac)
                                self._mac_history[mac] = []
                            ssid = data.get("ssid", "")
                            if mac not in self._ssid_map:
                                self._ssid_map[mac] = ssid
                            print(f"[wifi] Found MAC: {mac}")
                    except json.JSONDecodeError:
                        pass

        try:
            try_read_serial()
        except ImportError:
            try_read_file()
        except Exception as e:
            print(f"[wifi] Read error: {e}")

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
        reported_macs = set()
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
                        if mac not in reported_macs:
                            event = {
                                "mac": mac,
                                "type": "station",
                                "is_static": mac in self.static_macs,
                                "ssid": self._ssid_map.get(mac, ""),
                                "timestamp": now,
                            }
                            self.dashboard.add_wifi_event(event)
                            reported_macs.add(mac)

                time.sleep(1)
            except Exception as e:
                print(f"[wifi] Loop error: {e}")

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

    def start_calibration(self, duration_seconds=40):
        """Start MAC calibration process in background."""
        if self._calibrating:
            print("[wifi] Calibration already in progress")
            return
        
        self._calibrating = True
        self._calibration_sessions.append((time.time(), set()))
        print(f"[wifi] Starting MAC calibration for {duration_seconds}s")
        
        def calibrate():
            first_session = time.time()
            first_macs = set()
            
            for _ in range(duration_seconds // 2):
                self._parse_sniffer_output()
                first_macs.update(self.station_macs)
                time.sleep(2)
            
            print(f"[wifi] First session: {len(first_macs)} MACs")
            
            time.sleep(60)
            
            second_macs = set()
            for _ in range(duration_seconds // 2):
                self._parse_sniffer_output()
                second_macs.update(self.station_macs)
                time.sleep(2)
            
            print(f"[wifi] Second session: {len(second_macs)} MACs")
            
            static = first_macs & second_macs
            self.static_macs.update(static)
            print(f"[wifi] Identified {len(static)} static MACs: {static}")
            
            self._calibrating = False
            print("[wifi] Calibration complete")
        
        self._calibration_thread = threading.Thread(target=calibrate, daemon=True)
        self._calibration_thread.start()

    def is_calibrating(self):
        """Check if calibration is in progress."""
        return self._calibrating

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