#!/usr/bin/env python3
"""Simple MAC sieve: run 180s, classify static vs transient by presence duration."""
import json, os, select, signal, sys, time
from collections import defaultdict
from pathlib import Path

RUNNING = True
def _sig(*_):
    global RUNNING
    RUNNING = False
signal.signal(signal.SIGINT, _sig)
signal.signal(signal.SIGTERM, _sig)

DEVICE = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
DURATION = int(sys.argv[2]) if len(sys.argv) > 2 else 180
STABILIZE_DELAY = 1.0  # seconds to wait after opening device

def mac_norm(m):
    return (m or "").strip().upper()

def parse_src(frame_b64):
    try:
        b = __import__('base64').b64decode(frame_b64)
        if len(b) >= 16:
            return ":".join(f"{x:02X}" for x in b[10:16])
    except Exception:
        pass
    return None

macs = {}
total_lines = 0

fd = os.open(DEVICE, os.O_RDONLY | os.O_NONBLOCK)
print(f"[SIEVE] Reading {DEVICE} for {DURATION}s...")
time.sleep(STABILIZE_DELAY)  # Wait for device to stabilize
start = time.time()
buf = b""

try:
    while RUNNING and (time.time() - start) < DURATION:
        r, _, _ = select.select([fd], [], [], 0.25)
        if r:
            chunk = os.read(fd, 8192)
            if chunk:
                buf += chunk
                while b"\n" in buf:
                    ln, buf = buf.split(b"\n", 1)
                    total_lines += 1
                    s = ln.decode("utf-8", errors="replace").strip()
                    if not s.startswith("{"):
                        continue
                    try:
                        obj = json.loads(s)
                    except Exception:
                        continue
                    if obj.get("type") != "wifi":
                        continue
                    src = parse_src(str(obj.get("frame_b64") or ""))
                    if not src:
                        src = mac_norm(obj.get("bssid"))
                    if not src or src == "FF:FF:FF:FF:FF:FF":
                        continue
                    now = time.time()
                    if src not in macs:
                        macs[src] = {"first": now, "last": now, "samples": 0, "ssids": set(), "bssids": set(), "rssis": []}
                    macs[src]["last"] = now
                    macs[src]["samples"] += 1
                    ssid = str(obj.get("ssid") or "").strip()
                    if ssid and ssid != "(hidden)":
                        macs[src]["ssids"].add(ssid)
                    bssid = mac_norm(obj.get("bssid"))
                    if bssid and bssid != "FF:FF:FF:FF:FF:FF":
                        macs[src]["bssids"].add(bssid)
                    rssi = obj.get("rssi")
                    if isinstance(rssi, int):
                        macs[src]["rssis"].append(rssi)

        elapsed = time.time() - start
        if int(elapsed) % 5 == 0 and int(elapsed) > 0:
            sys.stdout.write(f"\r[SIEVE] {elapsed:.0f}s | lines={total_lines} unique_macs={len(macs)}")
            sys.stdout.flush()
            time.sleep(0.5)
except KeyboardInterrupt:
    print("\n[SIEVE] Interrupted")
finally:
    os.close(fd)

elapsed = time.time() - start
print(f"\n[SIEVE] Done. Ran {elapsed:.1f}s, {total_lines} lines, {len(macs)} unique MACs")

def classify(pct):
    if pct >= 75: return "STATIC"
    if pct <= 25: return "TRANSIENT"
    return "MIDDLE"

# Build sorted lists
results = []
for mac, info in macs.items():
    duration = info["last"] - info["first"]
    pct = (duration / elapsed) * 100
    cls = classify(pct)
    mean_rssi = round(sum(info["rssis"]) / len(info["rssis"]), 1) if info["rssis"] else None
    ssid_str = ", ".join(sorted(info["ssids"])[:5]) if info["ssids"] else "(none)"
    bssid_str = ", ".join(sorted(info["bssids"])[:3]) if info["bssids"] else "(none)"
    results.append((cls, pct, mac, mean_rssi, info["samples"], ssid_str, bssid_str))

results.sort(key=lambda x: (0 if x[0]=="STATIC" else 1 if x[0]=="MIDDLE" else 2, -x[1]))

print(f"\n{'='*80}")
print(f"{'CLS':<10} {'%TIME':<7} {'MAC':<20} {'RSSI':<7} {'SAMPLES':<8} {'SSID':<30} {'BSSID':<20}")
print(f"{'='*80}")
for cls, pct, mac, rssi, samples, ssid, bssid in results:
    rssi_s = f"{rssi}" if rssi else "?"
    print(f"{cls:<10} {pct:5.1f}%  {mac:<20} {rssi_s:<7} {samples:<8} {ssid:<30} {bssid:<20}")

print(f"\n{'='*80}")
print(f"STATIC count: {sum(1 for r in results if r[0]=='STATIC')}")
print(f"MIDDLE count: {sum(1 for r in results if r[0]=='MIDDLE')}")
print(f"TRANSIENT count: {sum(1 for r in results if r[0]=='TRANSIENT')}")

# Save
PROJECT_ROOT = Path(__file__).resolve().parent.parent
out = PROJECT_ROOT / "data" / "rf_mac_sieve.ndjson"
out.parent.mkdir(parents=True, exist_ok=True)
with out.open("w", encoding="utf-8") as f:
    for cls, pct, mac, rssi, samples, ssid, bssid in results:
        f.write(json.dumps({
            "mac": mac, "classification": cls, "pct": round(pct, 1),
            "samples": samples, "ssid": ssid, "bssid": bssid,
            "rssi_mean": rssi,
        }) + "\n")
print(f"\n[SAVED] data/rf_mac_sieve.ndjson ({len(results)} entries)")
