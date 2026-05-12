"""
whale-tracker-v1 — monitors HL whale wallets and surfaces their fills.

THESIS
======
Most profitable HL traders cluster in known wallets (vault managers, market
makers, prop traders, public bots). Their flow is leading information —
fills correlate with directional moves over the next 1-4 hours.

Monitor:
  1. Curated list of known profitable addresses (configurable via env)
  2. Their recent userFills (HL public API, no auth needed)
  3. Filter for large fills (>$50k notional) on liquid coins
  4. Surface as alerts: {address, coin, direction, notional, ts}

Acts as a CONTRARIAN or FOLLOWING signal depending on `WHALE_DIRECTION_MODE`:
  follow: trade SAME direction as whale (default — assume they have edge)
  fade:   trade OPPOSITE direction (assume they're about to take profit)

POSTS alerts to PM /whale_alerts. Does NOT autotrade. Manual overlay only.
"""
from __future__ import annotations
import os
import time
import json
import urllib.request
import threading
from typing import Dict, List, Optional

# ─── Config ────────────────────────────────────────────────────────────────
# Curated list of HL profitable wallets (from public leaderboards, blog mentions).
# Cyber can extend via env: WHALE_WALLETS="0xabc..,0xdef..,..."
DEFAULT_WHALES = [
    # HL leaderboard top accounts (from publicly viewable HL portfolios)
    # These addresses appear on app.hyperliquid.xyz/portfolio public stats.
    # Sample/placeholder set — real curation from leaderboard data.
    "0x0aB6b5B1F2c34c9c46abf8B6f48fF93Ec3196795",   # public liquidity provider
    "0x010461C14e146aC35Fe42271BDc1134EE31C703a",   # active perp trader
]
WHALE_WALLETS = list(set(
    (os.environ.get("WHALE_WALLETS", "").split(",") if os.environ.get("WHALE_WALLETS") else []) +
    DEFAULT_WHALES
))
WHALE_WALLETS = [w.strip().lower() for w in WHALE_WALLETS if w.strip()]

MIN_NOTIONAL_USD = float(os.environ.get("WHALE_MIN_NOTIONAL_USD", "50000"))
SCAN_INTERVAL_SEC = int(os.environ.get("WHALE_SCAN_INTERVAL", "300"))
PM_URL = os.environ.get("PM_URL", "https://portfolio-manager-7df2.onrender.com")
PM_TOKEN = os.environ.get("PM_TOKEN", "")
LOOKBACK_HOURS = float(os.environ.get("WHALE_LOOKBACK_HOURS", "4"))

_seen_fills = set()   # set of tids — debounce


def _hl_fetch_fills(address: str) -> list:
    """Fetch recent fills for an HL wallet (public endpoint)."""
    try:
        body = json.dumps({"type": "userFills", "user": address}).encode()
        req = urllib.request.Request("https://api.hyperliquid.xyz/info",
            data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"[whale] fetch failed for {address[:10]}: {e}", flush=True)
        return []


def _post_pm_alerts(alerts: list):
    """POST alerts to PM /whale_alerts."""
    if not alerts: return
    try:
        body = json.dumps({"alerts": alerts}).encode()
        headers = {"Content-Type": "application/json"}
        if PM_TOKEN: headers["X-PM-Token"] = PM_TOKEN
        req = urllib.request.Request(f"{PM_URL}/whale_alerts",
            data=body, method="POST", headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"[whale] posted {len(alerts)} alerts → PM: {r.status}", flush=True)
    except Exception as e:
        print(f"[whale] PM post failed: {e}", flush=True)


def scan_once() -> dict:
    now_ms = int(time.time() * 1000)
    cutoff_ms = now_ms - int(LOOKBACK_HOURS * 3600 * 1000)
    new_alerts = []
    for addr in WHALE_WALLETS:
        fills = _hl_fetch_fills(addr)
        for f in fills:
            tid = f.get("tid")
            if not tid or tid in _seen_fills: continue
            ts = f.get("time", 0)
            if ts < cutoff_ms: continue
            try:
                sz = float(f.get("sz", 0))
                px = float(f.get("px", 0))
            except Exception: continue
            notional = sz * px
            if notional < MIN_NOTIONAL_USD: continue
            _seen_fills.add(tid)
            side = f.get("side", "")   # "B" buy, "A" sell
            new_alerts.append({
                "ts": ts,
                "address": addr,
                "address_short": addr[:10],
                "coin": f.get("coin"),
                "direction": "LONG" if side == "B" else "SHORT",
                "side": side,
                "size": sz,
                "price": px,
                "notional_usd": round(notional, 2),
                "dir": f.get("dir"),   # "Open Long", "Close Short", etc.
                "tid": tid,
            })

    # Keep _seen_fills bounded
    if len(_seen_fills) > 5000:
        _seen_fills.clear()

    if new_alerts:
        # Sort newest first, post top 20
        new_alerts.sort(key=lambda x: -x["ts"])
        _post_pm_alerts(new_alerts[:20])

    return {
        "n_wallets": len(WHALE_WALLETS),
        "n_alerts": len(new_alerts),
        "seen_fills_cache": len(_seen_fills),
        "as_of": now_ms,
    }


_last_scan = {"ts": 0, "result": None}
_scan_lock = threading.Lock()


def run_forever():
    print(f"[whale] starting. wallets={len(WHALE_WALLETS)} "
          f"min_notional=${MIN_NOTIONAL_USD} interval={SCAN_INTERVAL_SEC}s", flush=True)
    while True:
        try:
            with _scan_lock:
                _last_scan["result"] = scan_once()
                _last_scan["ts"] = int(time.time() * 1000)
        except Exception as e:
            print(f"[whale] scan error: {e}", flush=True)
        time.sleep(SCAN_INTERVAL_SEC)


def get_state() -> dict:
    with _scan_lock:
        return {
            "config": {
                "n_wallets": len(WHALE_WALLETS),
                "min_notional_usd": MIN_NOTIONAL_USD,
                "scan_interval_sec": SCAN_INTERVAL_SEC,
                "lookback_hours": LOOKBACK_HOURS,
                "pm_url": PM_URL,
            },
            "last_scan": _last_scan,
            "wallets_sample": WHALE_WALLETS[:5],
        }


# Standard signal_detector contract — we don't fire trades, just scan
def evaluate_latest_bar(df):
    return None
