"""
engine-template — signal detector STUB.

REPLACE THIS FILE IN YOUR FORK with your strategy logic.

Contract: `evaluate_latest_bar(df)` takes a pandas DataFrame of OHLCV
candles (index = pandas Timestamp UTC, columns = open/high/low/close/volume)
and returns either:

  None                — no signal on the latest bar
  dict signal payload — see schema below

REQUIRED payload keys (trader.py and persistence.py read these):
  fire_ts        — pandas Timestamp of the bar that fired
  ref_price      — float, entry reference (last close)
  atr            — float, ATR at fire
  trade_side     — str, "B" for BUY, "A" for SELL (HL convention)
  is_long        — bool, True for long, False for short
  sl_px          — float, stop-loss absolute price
  tp_px          — float, take-profit absolute price
  max_hold_bars  — int, time-stop in bars (uses STRATEGY timeframe)

OPTIONAL — strategy debug fields, free-form:
  fire_reason    — short tag for telemetry
  raw_direction  — legacy field, freely usable; set to direction if no inversion
  fade_direction — legacy field, freely usable
  Any other keys you want logged go through and land in extras_json
  (handled automatically by trader → persistence.insert_signal).

The trader handles:
  - PM /size/{engine} multiplier on default notional
  - PM /check pre-trade gate
  - PM /register_cloid attribution
  - Order placement (paper or live)
  - SL/TP/time-stop management
  - PnL booking, /closures POST

You only write the signal logic.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Optional

from .config import STRATEGY_PARAMS, TRADE_PARAMS


def calc_atr(highs, lows, closes, period: int = 14) -> float:
    """ATR helper most engines need."""
    h_s = pd.Series(highs)
    l_s = pd.Series(lows)
    pc = pd.Series(closes).shift(1)
    tr = pd.concat([h_s - l_s, (h_s - pc).abs(), (l_s - pc).abs()], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])


def evaluate_latest_bar(df: pd.DataFrame) -> Optional[dict]:
    """
    TEMPLATE STUB. Replace with your engine's signal logic.

    The template returns None always, so the scheduler runs but no trades fire.
    Useful for verifying the deploy + plumbing before writing strategy code.
    """
    if df is None or len(df) < STRATEGY_PARAMS.get("candles_history", 200):
        return None

    # ─── Replace below with your fire condition ──────────────────────────
    #
    # closes = df["close"].values
    # highs  = df["high"].values
    # lows   = df["low"].values
    # vols   = df["volume"].values
    #
    # last_close = float(closes[-1])
    # last_atr   = calc_atr(highs, lows, closes, TRADE_PARAMS["atr_period"])
    #
    # # Your fire logic:
    # is_long = ...   # bool
    # fired   = ...   # bool
    # if not fired:
    #     return None
    #
    # if is_long:
    #     sl_px = last_close - TRADE_PARAMS["sl_atr_mult"] * last_atr
    #     tp_px = last_close + TRADE_PARAMS["tp_atr_mult"] * last_atr
    # else:
    #     sl_px = last_close + TRADE_PARAMS["sl_atr_mult"] * last_atr
    #     tp_px = last_close - TRADE_PARAMS["tp_atr_mult"] * last_atr
    #
    # return {
    #     "fire_ts":       df.index[-1],
    #     "ref_price":     last_close,
    #     "atr":           last_atr,
    #     "trade_side":    "B" if is_long else "A",
    #     "is_long":       is_long,
    #     "sl_px":         float(sl_px),
    #     "tp_px":         float(tp_px),
    #     "max_hold_bars": TRADE_PARAMS["max_hold_bars"],
    #     "fire_reason":   "your_strategy_tag",
    #     # any other debug fields — they'll be stored in extras_json
    # }

    return None
