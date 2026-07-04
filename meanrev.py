# -*- coding: utf-8 -*-
"""
Mean-reversion engine for ranging FX (Bollinger reversion + regime filter).
Long : close < lower band AND close > SMA(regime)  -> buy the dip in an uptrend
Short: close > upper band AND close < SMA(regime)  -> sell the rally in a downtrend
Exit : back to middle band (SMA) OR ATR stop OR time stop.
"""
import numpy as np
from trend import load, atr, spread_for, summarize, line, START_EQ

def sma(a, n):
    out = np.empty(len(a)); out[:] = np.nan
    csum = np.cumsum(np.insert(a, 0, 0.0))
    for i in range(n-1, len(a)):
        out[i] = (csum[i+1]-csum[i+1-n])/n
    return out

def rstd(a, n):
    out = np.empty(len(a)); out[:] = np.nan
    for i in range(n-1, len(a)):
        out[i] = a[i-n+1:i+1].std()
    return out

def run(path, bb_len=20, bb_k=2.0, regime_len=200, atr_len=14, stop_mult=3.0,
        risk_pct=0.5, max_hold=30, side=0, frac_start=0.0, frac_end=1.0, spread=None):
    ts, o, h, l, c = load(path)
    spread = spread_for(path) if spread is None else spread
    mid = sma(c, bb_len); sd = rstd(c, bb_len)
    upper = mid + bb_k*sd; lower = mid - bb_k*sd
    reg = sma(c, regime_len); a = atr(h, l, c, atr_len)

    n = len(c); i0 = max(1, int(n*frac_start)); i1 = int(n*frac_end)
    equity = START_EQ; peak = equity; max_dd = 0.0
    trades = []; pos = None

    for i in range(i0, i1):
        if np.isnan(reg[i]) or np.isnan(a[i]) or np.isnan(mid[i]):
            continue
        if pos is not None:
            pos["bars"] += 1
            exit_px = None
            if pos["dir"] == 1:
                if l[i] <= pos["stop"]:
                    exit_px = min(o[i], pos["stop"])
                elif c[i] >= mid[i]:                 # reverted to mean
                    exit_px = c[i]
            else:
                if h[i] >= pos["stop"]:
                    exit_px = max(o[i], pos["stop"])
                elif c[i] <= mid[i]:
                    exit_px = c[i]
            if exit_px is None and pos["bars"] >= max_hold:
                exit_px = c[i]                        # time stop
            if exit_px is not None:
                pnl = (exit_px-pos["entry"])*pos["qty"]*pos["dir"] - spread*pos["qty"]
                equity += pnl
                trades.append({"dir": pos["dir"], "pnl": pnl, "won": pnl > 0,
                               "R": pnl/pos["risk_amt"]})
                pos = None
        peak = max(peak, equity); max_dd = max(max_dd, (peak-equity)/peak*100)

        if pos is None:
            sig = 0
            if c[i] < lower[i] and c[i] > reg[i]:
                sig = 1
            elif c[i] > upper[i] and c[i] < reg[i]:
                sig = -1
            if side != 0 and sig != side:
                sig = 0
            if sig != 0:
                dist = a[i]*stop_mult
                if dist > 0:
                    qty = (equity*risk_pct/100.0)/dist
                    pos = {"dir": sig, "entry": c[i], "qty": qty,
                           "risk_amt": equity*risk_pct/100.0, "bars": 0,
                           "stop": c[i]-dist if sig == 1 else c[i]+dist}

    years = (ts[i1-1]-ts[i0])/(365.25*24*3600) if i1 > i0 else 0
    return summarize(trades, equity, max_dd, years)

if __name__ == "__main__":
    print("===== MEAN-REVERSION (Bollinger) =====")
    for tf, files in [("DAILY", [("EUR/USD","eurusd_d1.csv"),("AUD/USD","audusd_d1.csv"),("GOLD","gold_d1.csv")]),
                      ("H4",    [("EUR/USD","eurusd_h4.csv"),("AUD/USD","audusd_h4.csv"),("GOLD","gold_h4.csv")])]:
        print(f"-- {tf} --")
        for name, f in files:
            line(name, run(f))
        print()
