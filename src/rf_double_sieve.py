#!/usr/bin/env python3
"""
Double Sieve: run two consecutive 30s MAC scans, cross-reference,
and update config/static_ignore.json with MACs present in both.

Usage:
    python3 src/rf_double_sieve.py [/dev/ttyUSB1]

Output:
    - Shows intersection (static/persistent MACs found in both scans)
    - Prompts before writing to config/static_ignore.json
    - Appends to ignore list (preserves existing entries)

Dependencies:
    - rf_mac_sieve.py (imported for scan logic)
"""

import json
import sys
import time
from pathlib import Path

# Reuse the MAC scanning logic from rf_mac_sieve
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.rf_mac_sieve import parse_src, mac_norm

DEVICE = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB1"
SCAN_DURATION = 30  # seconds per scan

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
IGNORE_PATH = CONFIG_DIR / "static_ignore.json"


def run_sieve(device: str, duration: int, label: str) -> set:
    """Run ndjson-based sieve for `duration` seconds, return set of MACs seen."""
    import os
    import select
    import signal
    from collections import defaultdict

    running = True
    def _sig(*_):
        nonlocal running
        running = False
    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    macs = {}
    total_lines = 0

    fd = os.open(device, os.O_RDONLY | os.O_NONBLOCK)
    print(f"[SIEVE {label}] Reading {device} for {duration}s...")
    start = time.time()
    buf = b""

    try:
        while running and (time.time() - start) < duration:
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
                        macs[src] = macs.get(src, 0) + 1

            elapsed = time.time() - start
            if int(elapsed) % 10 == 0 and int(elapsed) > 0:
                print(f"\r[SIEVE {label}] {elapsed:.0f}s | lines={total_lines} unique_macs={len(macs)}", end="")
                sys.stdout.flush()
                time.sleep(0.5)
    except KeyboardInterrupt:
        print(f"\n[SIEVE {label}] Interrupted")
    finally:
        os.close(fd)

    elapsed = time.time() - start
    print(f"\n[SIEVE {label}] Done. Ran {elapsed:.1f}s, {total_lines} lines, {len(macs)} unique MACs")
    return set(macs.keys())


def load_ignore_list() -> set:
    """Load existing ignore MACs, return as uppercase set."""
    if not IGNORE_PATH.exists():
        print(f"[INFO] No existing {IGNORE_PATH}, starting fresh")
        return set()
    with IGNORE_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    existing = {m.strip().upper() for m in data.get("ignore_macs", [])}
    print(f"[INFO] Existing ignore list: {len(existing)} MACs")
    return existing


def save_ignore_list(macs: set) -> None:
    """Write sorted MAC set to static_ignore.json."""
    sorted_macs = sorted(macs)
    with IGNORE_PATH.open("w", encoding="utf-8") as f:
        json.dump({"ignore_macs": sorted_macs}, f, indent=2)
        f.write("\n")
    print(f"[SAVED] {IGNORE_PATH} — {len(sorted_macs)} MACs")


def main():
    print("=== RF Double Sieve ===")
    print(f"Device: {DEVICE}")
    print(f"Scan duration per pass: {SCAN_DURATION}s")
    print()

    # Scan 1
    macs_1 = run_sieve(DEVICE, SCAN_DURATION, "1/2")
    print()

    # Scan 2
    macs_2 = run_sieve(DEVICE, SCAN_DURATION, "2/2")
    print()

    # Cross-reference
    common = macs_1 & macs_2
    only_1 = macs_1 - macs_2
    only_2 = macs_2 - macs_1

    print("=== Results ===")
    print(f"Scan 1 unique: {len(macs_1)}")
    print(f"Scan 2 unique: {len(macs_2)}")
    print(f"Common (persistent/static): {len(common)}")
    print(f"Scan 1 only (transient): {len(only_1)}")
    print(f"Scan 2 only (transient): {len(only_2)}")
    print()

    if not common:
        print("[RESULT] No persistent MACs found. No changes to ignore list.")
        return

    print("Persistent MACs (present in both scans):")
    for mac in sorted(common):
        print(f"  {mac}")

    # Load existing ignore list
    existing = load_ignore_list()

    # New MACs to add
    new_macs = common - existing
    if not new_macs:
        print("[RESULT] All persistent MACs already in ignore list. No changes needed.")
        return

    print(f"\nNew MACs to add to ignore list: {len(new_macs)}")
    for mac in sorted(new_macs):
        print(f"  {mac}")

    # Prompt
    print()
    try:
        response = input("Add these MACs to static_ignore.json? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        response = "n"
        print()

    if response not in ("y", "yes"):
        print("[ABORTED] No changes made.")
        return

    # Merge and save
    updated = existing | common
    save_ignore_list(updated)
    print(f"[DONE] Added {len(updated - existing)} new MACs to ignore list (total: {len(updated)})")


if __name__ == "__main__":
    main()
