# -*- coding: utf-8 -*-
"""
ICT / Smart-Money-Concepts engine: BOS + CHoCH + Order Block retest.

Precise, testable definitions (no discretion, no look-ahead):

Swing High : bar j whose high is strictly greater than the highs of the N bars
             on each side. Confirmed only at bar j+N (we cannot know earlier).
Swing Low  : mirror image.

Trend      : +1 after an upside structure break, -1 after a downside break,
             0 before the first break.
BOS        : close breaks the last confirmed swing IN the trend direction
             (continuation).
CHoCH      : close breaks the last confirmed swing AGAINST the trend
             (reversal signal — the setup in the reference image).

Order Block: the last opposite-direction candle (bearish for a bullish break,
             bullish for a bearish break) within the leg that caused the break.
             Zone = that candle's [low, high].

Entry      : limit order at the near edge of the OB zone (retest).
Stop       : far edge of the OB zone minus/plus a small ATR buffer.
Target     : fixed R:R multiple (risk manager rejects anything below MIN_RR
             by construction — TP is placed at MIN_RR).
Expiry     : pending order cancelled after `expiry` bars, or if price violates
             the OB (hits stop level) before filling, or if a new break
             replaces the setup.

Conservative fills: if a bar touches both SL and TP, count SL (worst case).
Costs: same per-instrument spread+slippage convention as trend.py.
"""
import csv, numpy as np

START_EQ = 10000.0

SPREADS = {
    "eurusd": 0.00012, "audusd": 0.00012, "gbpusd": 0.00012, "usdjpy": 0.012,
    "gold":   0.35,    "silver": 0.03,    "nas":    1.0,
    "crude":  0.04,    "btc":    15.0,
}
def spread_for(path):
    for k, v in SPREADS.items():
        if k in path:
            return v
    return 0.00012

def ema(arr, length):
    out = np.empty(len(arr)); out[:] = np.nan
    k = 2 / (length + 1); s = None
    for i, v in enumerate(arr):
        s = v if s is None else (v - s) * k + s
        out[i] = s
    return out

def atr(h, l, c, length=14):
    n = len(c); tr = np.empty(n)
    for i in range(n):
        tr[i] = h[i]-l[i] if i == 0 else max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
    out = np.empty(n); out[:] = np.nan; s = None
    for i in range(n):
        s = tr[i] if s is None else (s*(length-1)+tr[i])/length
        out[i] = s
    return out

def load(path):
    ts, o, h, l, c = [], [], [], [], []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ts.append(int(row["timestamp"])); o.append(float(row["open"]))
            h.append(float(row["high"])); l.append(float(row["low"])); c.append(float(row["close"]))
    return (np.array(ts), np.array(o), np.array(h), np.array(l), np.array(c))

# --------------------------- engine -------------------------------
def run(path, swing_n=5, rr=2.0, risk_pct=0.5, expiry=30, mode="choch",
        buf_atr=0.1, trend_len=0, frac_start=0.0, frac_end=1.0, spread=None,
        return_trades=False):
    """
    mode: "choch" = trade only CHoCH (reversal) setups, as in the image.
          "both"  = also trade BOS (continuation) setups.
    trend_len: if >0, only take longs above / shorts below this EMA (HTF filter).
    """
    ts, o, h, l, c = load(path)
    spread = spread_for(path) if spread is None else spread
    a = atr(h, l, c)
    tema = ema(c, trend_len) if trend_len > 0 else None
    n = len(c)
    i0 = max(2*swing_n + 1, int(n*frac_start)); i1 = int(n*frac_end)

    equity = START_EQ; peak = equity; max_dd = 0.0
    trades = []
    trend = 0
    last_sh = None   # (idx, price) most recent confirmed, unbroken swing high
    last_sl = None
    pending = None   # {"dir","limit","sl","tp","placed","event"}
    pos = None       # {"dir","entry","sl","tp","qty","risk_amt","event"}

    def close_trade(fill, i, reason):
        nonlocal equity, pos
        pnl = (fill - pos["entry"]) * pos["qty"] * pos["dir"] - spread * pos["qty"]
        equity += pnl
        trades.append({"dir": pos["dir"], "pnl": pnl, "won": pnl > 0,
                       "R": pnl / pos["risk_amt"], "ts": ts[i],
                       "event": pos["event"], "exit": reason})
        pos = None

    for i in range(i0, i1):
        # ---- 1. confirm swings formed N bars ago (known only now) ----
        j = i - swing_n
        if j >= swing_n:
            win_h = h[j-swing_n:j+swing_n+1]
            if h[j] == win_h.max() and (win_h == h[j]).sum() == 1:
                last_sh = (j, h[j])
            win_l = l[j-swing_n:j+swing_n+1]
            if l[j] == win_l.min() and (win_l == l[j]).sum() == 1:
                last_sl = (j, l[j])

        # ---- 2. manage open position (intrabar, SL takes priority) ----
        if pos is not None:
            if pos["dir"] == 1:
                if l[i] <= pos["sl"]:
                    close_trade(min(o[i], pos["sl"]), i, "sl")
                elif h[i] >= pos["tp"]:
                    close_trade(pos["tp"], i, "tp")
            else:
                if h[i] >= pos["sl"]:
                    close_trade(max(o[i], pos["sl"]), i, "sl")
                elif l[i] <= pos["tp"]:
                    close_trade(pos["tp"], i, "tp")

        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak * 100)

        # ---- 3. manage pending limit order ----
        if pending is not None and pos is None:
            p = pending
            if i - p["placed"] > expiry:
                pending = None
            elif p["dir"] == 1:
                if l[i] <= p["sl"]:            # OB violated -> worst case handling
                    if l[i] <= p["limit"] and o[i] > p["sl"]:
                        # filled at limit then stopped same bar (conservative loss)
                        risk_amt = equity * risk_pct / 100.0
                        qty = risk_amt / (p["limit"] - p["sl"])
                        pos = {"dir": 1, "entry": p["limit"], "sl": p["sl"], "tp": p["tp"],
                               "qty": qty, "risk_amt": risk_amt, "event": p["event"]}
                        close_trade(p["sl"], i, "sl")
                    pending = None
                elif l[i] <= p["limit"]:
                    entry = min(o[i], p["limit"])
                    risk_amt = equity * risk_pct / 100.0
                    qty = risk_amt / (entry - p["sl"])
                    pos = {"dir": 1, "entry": entry, "sl": p["sl"], "tp": p["tp"],
                           "qty": qty, "risk_amt": risk_amt, "event": p["event"]}
                    pending = None
            else:
                if h[i] >= p["sl"]:
                    if h[i] >= p["limit"] and o[i] < p["sl"]:
                        risk_amt = equity * risk_pct / 100.0
                        qty = risk_amt / (p["sl"] - p["limit"])
                        pos = {"dir": -1, "entry": p["limit"], "sl": p["sl"], "tp": p["tp"],
                               "qty": qty, "risk_amt": risk_amt, "event": p["event"]}
                        close_trade(p["sl"], i, "sl")
                    pending = None
                elif h[i] >= p["limit"]:
                    entry = max(o[i], p["limit"])
                    risk_amt = equity * risk_pct / 100.0
                    qty = risk_amt / (p["sl"] - entry)
                    pos = {"dir": -1, "entry": entry, "sl": p["sl"], "tp": p["tp"],
                           "qty": qty, "risk_amt": risk_amt, "event": p["event"]}
                    pending = None

        # ---- 4. structure breaks on close ----
        buf = a[i] * buf_atr if not np.isnan(a[i]) else 0.0

        if last_sh is not None and c[i] > last_sh[1]:
            event = "choch" if trend == -1 else "bos"
            trend = 1
            sh_idx = last_sh[0]; last_sh = None
            trend_ok = tema is None or (not np.isnan(tema[i]) and c[i] > tema[i])
            if pos is None and trend_ok and (mode == "both" or event == "choch"):
                # OB = last bearish candle in the leg [sh_idx..i]
                ob = None
                for k in range(i, max(sh_idx - 2*expiry, 0), -1):
                    if c[k] < o[k]:
                        ob = k; break
                if ob is not None:
                    limit, sl = h[ob], l[ob] - buf
                    if limit - sl > 0:
                        pending = {"dir": 1, "limit": limit, "sl": sl,
                                   "tp": limit + rr * (limit - sl),
                                   "placed": i, "event": event}

        elif last_sl is not None and c[i] < last_sl[1]:
            event = "choch" if trend == 1 else "bos"
            trend = -1
            sl_idx = last_sl[0]; last_sl = None
            trend_ok = tema is None or (not np.isnan(tema[i]) and c[i] < tema[i])
            if pos is None and trend_ok and (mode == "both" or event == "choch"):
                ob = None
                for k in range(i, max(sl_idx - 2*expiry, 0), -1):
                    if c[k] > o[k]:
                        ob = k; break
                if ob is not None:
                    limit, sl_price = l[ob], h[ob] + buf
                    if sl_price - limit > 0:
                        pending = {"dir": -1, "limit": limit, "sl": sl_price,
                                   "tp": limit - rr * (sl_price - limit),
                                   "placed": i, "event": event}

    years = (ts[i1-1] - ts[i0]) / (365.25*24*3600) if i1 > i0 else 0
    if return_trades:
        return trades
    return summarize(trades, equity, max_dd, years)

def summarize(trades, equity, max_dd, years):
    n = len(trades)
    wins = [t for t in trades if t["won"]]
    gw = sum(t["pnl"] for t in wins)
    gl = -sum(t["pnl"] for t in trades if not t["won"])
    pf = gw/gl if gl > 0 else float("inf")
    net = (equity - START_EQ) / START_EQ * 100
    cagr = ((equity/START_EQ)**(1/years) - 1) * 100 if years > 0.2 and equity > 0 else float("nan")
    return {"trades": n, "win_rate": (len(wins)/n*100 if n else 0), "net_pct": net,
            "cagr": cagr, "profit_factor": pf, "max_dd": max_dd,
            "avg_R": (np.mean([t["R"] for t in trades]) if n else 0), "years": years}

def line(name, r):
    pf = "inf" if r["profit_factor"] == float("inf") else f"{r['profit_factor']:.2f}"
    win = r["profit_factor"] > 1.0 and r["net_pct"] > 0
    print(f"  {name:<34} | {'WIN ' if win else 'LOSS'} | trd {r['trades']:>4} | "
          f"win {r['win_rate']:>4.1f}% | net {r['net_pct']:>+7.1f}% | "
          f"PF {pf:>4} | DD {r['max_dd']:>5.1f}% | avgR {r['avg_R']:>+5.2f}")
