"""WiFi MAC sniffer for vehicle correlation."""

import json
import os
import select
import subprocess
import threading
import time
from collections import defaultdict
from pathlib import Path

from .config import load_config, PROJECT_ROOT


IGNORE_PATH = PROJECT_ROOT / "config" / "static_ignore.json"


def load_ignore_list():
    if IGNORE_PATH.exists():
        with open(IGNORE_PATH, "r") as f:
            data = json.load(f)
            return {m.strip().upper() for m in data.get("ignore_macs", [])}
    return set()


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

    BAUD_RATE = 115200

    def __init__(self, dashboard=None):
        cfg = load_config()
        self.enabled = cfg.get("wifi_sniffer", {}).get("enabled", False)
        self.device = cfg.get("wifi_sniffer", {}).get("device", "/dev/ttyUSB0")
        self.baud_rate = 115200
        self.dwell_time = cfg.get("wifi_sniffer", {}).get("dwell_time", 10)
        self.bssid_list = set()
        self.station_macs = set()
        self.static_macs = set()
        self._ignore_macs = load_ignore_list()
        self._mac_history = defaultdict(list)
        self._history_window = cfg.get("wifi_sniffer", {}).get("history_window", 3600)
        self._ssid_map = {}
        self._calibration_start = None
        self._calibration_state = "idle"
        self._calibration_macs = {"first": set(), "second": set()}
        self._calibration_duration = 30
        self._running = False
        self._thread = None
        self._reported_macs = set()
        self._display_timestamps = {}
        self._overlay_enabled = True
        self._calibration_running = False
        self.dashboard = dashboard

        if self.enabled:
            print(f"[wifi] WiFi sniffer enabled (device: {self.device})")
        else:
            print("[wifi] WiFi sniffer disabled")

    def is_ignored(self, mac):
        return mac.upper() in self._ignore_macs

    def reload_ignore_list(self):
        self._ignore_macs = load_ignore_list()
        print(f"[wifi] Reloaded ignore list: {len(self._ignore_macs)} MACs")

    def get_dynamic_macs(self):
        return self.station_macs - self.static_macs - self._ignore_macs

    def get_static_macs(self):
        return self.static_macs.copy()

    def get_dynamic_macs_with_ssid(self):
        dynamic = []
        for mac in self.get_dynamic_macs():
            ssid = self._ssid_map.get(mac, "")
            dynamic.append((mac, ssid))
        return dynamic

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
        """Parse WiFi sniffer JSONL output for MAC addresses.
        
        ESP32 in promiscuous mode outputs JSONL lines with raw packet data.
        Garbage outside of {} delimiters is ignored.
        """
        import base64
        import struct
        
        if not os.path.exists(self.device):
            return

        try:
            import serial
            ser = None
            try:
                ser = serial.Serial(self.device, self.baud_rate, timeout=0.1)
            except Exception as e:
                if ser:
                    ser.close()
                raise

            lines_read = 0
            try:
                while lines_read < 100:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if not line:
                        break
                    lines_read += 1
                    
                    if not line.startswith('{'):
                        continue
                    
                    try:
                        data = json.loads(line)
                        if data.get("type") != "wifi":
                            continue
                            
                        frame_b64 = str(data.get("frame_b64") or "")
                        bssid = data.get("bssid", "")
                        ssid = data.get("ssid", "")
                        
                        if not bssid or not is_valid_mac(bssid.lower()):
                            if frame_b64:
                                try:
                                    raw = base64.b64decode(frame_b64)
                                    if len(raw) >= 16:
                                        src = ":".join(f"{x:02X}" for x in raw[10:16])
                                        if not is_valid_mac(src.lower()):
                                            continue
                                        bssid = src
                                except Exception:
                                    continue
                        
                        mac = bssid.lower()
                        if not is_valid_mac(mac):
                            continue
                        
                        if mac not in self.station_macs:
                            self.station_macs.add(mac)
                        if mac not in self._ssid_map:
                            self._ssid_map[mac] = ssid if ssid else ""
                    except json.JSONDecodeError:
                        continue
            finally:
                if ser:
                    ser.close()
        except ImportError:
            self._parse_sniffer_file()
        except Exception as e:
            print(f"[wifi] Serial error: {e}")

    def _parse_sniffer_file(self):
        """Parse WiFi sniffer output from device file (fallback mode)."""
        if not os.path.exists(self.device):
            return
            
        import select
        
        try:
            fd = os.open(self.device, os.O_RDONLY | os.O_NONBLOCK)
            buf = b""
            lines_read = 0
            
            try:
                while lines_read < 100:
                    r, _, _ = select.select([fd], [], [], 0.05)
                    if not r:
                        break
                    
                    chunk = os.read(fd, 8192)
                    if not chunk:
                        continue
                    
                    buf += chunk
                    
                    while b'\n' in buf:
                        ln, buf = buf.split(b'\n', 1)
                        lines_read += 1
                        
                        s = ln.decode('utf-8', errors='ignore').strip()
                        if not s.startswith('{'):
                            continue
                            
                        try:
                            data = json.loads(s)
                            if data.get("type") != "wifi":
                                continue
                            
                            bssid = data.get("bssid", "")
                            ssid = data.get("ssid", "")
                            
                            if not bssid or not is_valid_mac(bssid.lower()):
                                frame_b64 = str(data.get("frame_b64") or "")
                                if frame_b64:
                                    import base64
                                    raw = base64.b64decode(frame_b64)
                                    if len(raw) >= 16:
                                        bssid = ":".join(f"{x:02X}" for x in raw[10:16])
                            
                            mac = bssid.lower()
                            if is_valid_mac(mac):
                                if mac not in self.station_macs:
                                    self.station_macs.add(mac)
                                if mac not in self._ssid_map:
                                    self._ssid_map[mac] = ssid if ssid else ""
                        except json.JSONDecodeError:
                            continue
            finally:
                os.close(fd)
        except Exception as e:
            print(f"[wifi] File read error: {e}")

    def _detect_static_macs(self):
        """Detect static MACs from history."""
        for mac, timestamps in self._mac_history.items():
            if len(timestamps) > 3:
                self.static_macs.add(mac)

    def start(self):
        """Start the WiFi sniffer thread."""
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
        """Main sniffer loop running in background thread."""
        time.sleep(0.5)  # Give Flask time to start
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
                        if mac not in self.static_macs and not self.is_ignored(mac):
                            if mac not in self._display_timestamps:
                                self._display_timestamps[mac] = now
                            if mac not in self._reported_macs:
                                self._reported_macs.add(mac)
                                event = {
                                    "mac": mac,
                                    "type": "station",
                                    "is_static": False,
                                    "ssid": self._ssid_map.get(mac, ""),
                                    "timestamp": now,
                                }
                                self.dashboard.add_wifi_event(event)
                    
                    for mac in list(self._display_timestamps.keys()):
                        if now - self._display_timestamps[mac] >= self.dwell_time:
                            if mac in self._reported_macs:
                                self._reported_macs.discard(mac)
                            del self._display_timestamps[mac]

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

                time.sleep(0.5)
            except Exception as e:
                print(f"[wifi] Loop error: {e}")

    def start_calibration(self, duration_seconds=30):
        """Start MAC calibration process: duration_seconds + 30s wait + duration_seconds."""
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
            "ignored_macs": len(self._ignore_macs),
            "calibrating": self.is_calibrating(),
        }