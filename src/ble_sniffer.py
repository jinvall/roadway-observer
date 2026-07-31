"""BLE device sniffer for device correlation."""

import asyncio
import threading
import time
from collections import defaultdict
from pathlib import Path


class BleSniffer:
    """Captures BLE device advertisements using bleak library."""

    def __init__(self, dashboard=None):
        from .config import load_config
        from .wifi_sniffer import load_ignore_list
        
        cfg = load_config()
        self.enabled = cfg.get("ble_sniffer", {}).get("enabled", False)
        self.dwell_time = cfg.get("ble_sniffer", {}).get("dwell_time", 10)
        self._ignore_macs = load_ignore_list() or set()
        self.discovered_macs = set()
        self._mac_names = {}
        self._mac_history = defaultdict(list)
        self._history_window = cfg.get("ble_sniffer", {}).get("history_window", 3600)
        self._running = False
        self._thread = None
        self._loop = None
        self._reported_macs = set()
        self._display_timestamps = {}
        self._scan_result = None
        self.dashboard = dashboard
        self.duty_cycle = cfg.get("ble_sniffer", {}).get("duty_cycle", 10.0)

        if self.enabled:
            print(f"[ble] BLE sniffer enabled")
        else:
            print("[ble] BLE sniffer disabled")

    def is_ignored(self, mac: str) -> bool:
        """Check if MAC is in ignore list."""
        return mac.upper() in self._ignore_macs

    def reload_ignore_list(self) -> None:
        """Reload ignore list from disk."""
        try:
            from .wifi_sniffer import load_ignore_list
            self._ignore_macs = load_ignore_list() or set()
            print(f"[ble] Reloaded ignore list: {len(self._ignore_macs)} MACs")
        except Exception as e:
            print(f"[ble] Reload ignore list error: {e}")

    def get_discovered_devices(self):
        """Return list of non-ignored discovered devices."""
        return [m for m in self.discovered_macs if not self.is_ignored(m)]

    def get_device_name(self, mac: str) -> str:
        """Get the name/SSID-like name for a BLE device."""
        return self._mac_names.get(mac, "")

    async def _scan_ble_devices(self, bleak_scanner):
        """Scan for BLE devices for a short interval."""
        devices = []
        try:
            devices = await bleak_scanner.discover(timeout=2.0)
        except Exception as e:
            print(f"[ble] Scan error: {e}")
        return devices

    def start(self):
        """Start the BLE sniffer thread."""
        if not self.enabled:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        print("[ble] BLE scanner started")

    def stop(self):
        """Stop the BLE sniffer."""
        self._running = False
        if self._thread:
            try:
                self._thread.join(timeout=3)
            except Exception:
                pass
        print("[ble] BLE scanner stopped")

    def _run(self):
        """Main sniffer loop running in background thread."""
        import bleak
        
        time.sleep(0.5)
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        
        try:
            scanner = bleak.BleakScanner()
            while self._running:
                try:
                    devices = loop.run_until_complete(self._scan_ble_devices(scanner))
                    now = time.time()
                    
                    for dev in devices:
                        if not dev.address:
                            continue
                        
                        mac = dev.address.lower()
                        name = dev.name or ""
                        
                        if mac not in self.discovered_macs:
                            self.discovered_macs.add(mac)
                        if mac not in self._mac_names:
                            self._mac_names[mac] = name
                        
                        for key in list(self._mac_history.keys()):
                            self._mac_history[key] = [
                                t for t in self._mac_history[key]
                                if now - t < self._history_window
                            ]
                    
                    if self.dashboard:
                        for mac in self.discovered_macs:
                            if mac not in self._mac_history or len(self._mac_history[mac]) == 0:
                                self._mac_history[mac] = []
                            self._mac_history[mac].append(now)
                            
                            if mac not in self._display_timestamps:
                                self._display_timestamps[mac] = now
                            
                            if mac not in self._reported_macs and not self.is_ignored(mac):
                                self._reported_macs.add(mac)
                                event = {
                                    "mac": mac,
                                    "type": "ble",
                                    "is_static": False,
                                    "name": self._mac_names.get(mac, ""),
                                    "timestamp": now,
                                }
                                self.dashboard.add_ble_event(event)
                        
                        for mac in list(self._display_timestamps.keys()):
                            if now - self._display_timestamps[mac] >= self.dwell_time:
                                if mac in self._reported_macs:
                                    self._reported_macs.discard(mac)
                                del self._display_timestamps[mac]
                    
                    time.sleep(self.duty_cycle)
                except Exception as e:
                    print(f"[ble] Loop error: {e}")
                    time.sleep(1)
        except ImportError:
            print("[ble] bleak library not installed, BLE scanning disabled")
            self.enabled = False
        except Exception as e:
            print(f"[ble] Error: {e}")
        finally:
            try:
                loop.close()
            except Exception:
                pass
            scanner = None
            loop = None

    def get_dynamic_devices(self):
        """Return list of dynamically seen BLE devices."""
        return [(m, self._mac_names.get(m, "")) for m in self.get_discovered_devices()]

    @property
    def stats(self):
        return {
            "enabled": self.enabled,
            "devices": len(self.discovered_macs),
            "dynamic_devices": len(self.get_dynamic_devices()),
            "dwell_time": self.dwell_time,
            "duty_cycle": self.duty_cycle,
        }