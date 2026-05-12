"""
whale-tracker-v1 — track known top HL traders, alert on their large entries.

THESIS
======
Some HL accounts have proven track records — winning over months/years
with significant capital. When they open new positions, especially large
ones, their information is statistically reliable signal.

Track approach: poll WHALE_ADDRESSES env var (comma-separated) every
WHALE_POLL_INTERVAL_SEC. For each address:
  - Fetch userFills (recent)
  - Identify new fills since last poll (by tid)
  - For each new fill above MIN_NOTIONAL_USD, push alert to PM

Alerts include:
  - Wallet name (configurable via WHALE_LABELS)
  - Coin, side, size, notional
  - Whether it opens/adds/closes (vs existing position direction)
  - Optional confluence with engine signals (cross-reference active alerts)
"""
from __future__ import annotations
import os
import time
import json
import urllib.request
import threading
from typing import Dict, List, Optional


# Comma-separated list of HL wallet addresses to monitor
WHALE_ADDRESSES = [a.strip().lower() for a in os.environ.get("WHALE_ADDRESSES", "").split(",") if a.strip()]
# Optional labels per address: "0xabc:WhaleA,0xdef:WhaleB"
_label_pairs = os.environ.get("WHALE_LABELS", "").split(",")
WHALE_LABELS = {}
for p in _label_pairs:
    if ":" in p:
        addr, label = p.split(":", 1)
        WHALE_LABELS[addr.strip().lower()] = label.strip()

MIN_NOTIONAL_USD = float(os.environ.get("WHALE_MIN_NOTIONAL_USD", "50000"))
POLL_INTERVAL_SEC = int(os.environ.get("WHALE_POLL_INTERVAL_SEC", "180"))
LOOKBACK_HOURS = int(os.environ.get("WHALE_LOOKBACK_HOURS", "4"))
PM_URL = os.environ.get("PM_URL", "https://portfolio-manager-7df2.onrender.com")

STATE_DIR = os.environ.get("STATE_DIR", "/tmp/whale-state")
_last_seen_file = os.path.join(STATE_DIR, "whale_last_tid.json")
_last_seen: Dict[str, int] = {}   # addr -> last tid seen
_lock = threading.Lock()


def _load_state():
    try:
        with open(_last_seen_file) as f:
            _last_seen.update(json.load(f))
    except Exception:
        pass


def _save_state():
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(_last_seen_file, "w") as f:
            json.dump(_last_seen, f)
    except Exception as e:
        print(f"[whale] save error: {e}", flush=True)


def _fetch_user_fills(addr: str) -> List[dict]:
    try:
        req = urllib.request.Request("https://api.hyperliquid.xyz/info",
            data=json.dumps({"type": "userFills", "user": addr}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"[whale] {addr[:10]} fetch error: {e}", flush=True)
        return []


def scan_whales() -> List[dict]:
    """Scan all monitored whales, return new alert-worthy fills."""
    alerts = []
    cutoff_ms = int((time.time() - LOOKBACK_HOURS * 3600) * 1000)

    for addr in WHALE_ADDRESSES:
        label = WHALE_LABELS.get(addr, addr[:8])
        fills = _fetch_user_fills(addr)
        if not fills:
            continue

        with _lock:
            last_seen_tid = _last_seen.get(addr, 0)
            max_tid_this_scan = last_seen_tid

        for f in fills:
            tid = f.get("tid", 0)
            ts = f.get("time", 0)
            if tid <= last_seen_tid: continue
            if ts < cutoff_ms: continue

            coin = f.get("coin", "")
            side = f.get("side", "")
            sz = float(f.get("sz", 0))
            px = float(f.get("px", 0))
            notional = sz * px
            direction = f.get("dir", "")    # "Open Long", "Open Short", "Close Long", etc

            if notional < MIN_NOTIONAL_USD:
                continue

            is_open = "Open" in direction
            is_long = "Long" in direction
            raw_dir = "LONG" if is_long else "SHORT"

            alerts.append({
                "ts": ts,
                "tid": tid,
                "addr": addr,
                "label": label,
                "coin": coin,
                "side": side,
                "raw_direction": raw_dir,
                "is_open": is_open,
                "size": sz,
                "price": px,
                "notional_usd": notional,
                "dir_str": direction,
                "age_min": (int(time.time()*1000) - ts) / 60_000,
            })

            if tid > max_tid_this_scan:
                max_tid_this_scan = tid

        with _lock:
            _last_seen[addr] = max_tid_this_scan
            _save_state()

    return alerts


def push_to_pm(alerts: List[dict]):
    """Post alerts to PM /whale_alerts endpoint (no-op if PM doesn't have it)."""
    if not alerts: return
    try:
        body = json.dumps({"alerts": alerts}).encode()
        req = urllib.request.Request(f"{PM_URL}/whale_alerts",
            data=body, method="POST",
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status
    except Exception as e:
        print(f"[whale] PM push error: {e}", flush=True)
        return None


def tick():
    if not WHALE_ADDRESSES:
        print("[whale] no WHALE_ADDRESSES configured — skipping", flush=True)
        return
    alerts = scan_whales()
    if alerts:
        summary = [(a['label'], a['coin'], a['raw_direction'], f"${a['notional_usd']:.0f}") for a in alerts]
        print(f"[whale] {len(alerts)} new alerts: {summary}", flush=True)
        push_to_pm(alerts)


def run_forever():
    print(f"[whale] starting. Tracking {len(WHALE_ADDRESSES)} addresses, "
          f"min ${MIN_NOTIONAL_USD:.0f}, poll {POLL_INTERVAL_SEC}s", flush=True)
    _load_state()
    while True:
        try:
            tick()
        except Exception as e:
            print(f"[whale] tick error: {e}", flush=True)
        time.sleep(POLL_INTERVAL_SEC)


def get_state() -> dict:
    return {
        "config": {
            "n_addresses": len(WHALE_ADDRESSES),
            "addresses": [{"addr": a, "label": WHALE_LABELS.get(a, "")} for a in WHALE_ADDRESSES],
            "min_notional_usd": MIN_NOTIONAL_USD,
            "poll_interval_sec": POLL_INTERVAL_SEC,
            "lookback_hours": LOOKBACK_HOURS,
        },
        "last_seen": dict(_last_seen),
    }
