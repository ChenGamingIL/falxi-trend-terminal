# -*- coding: utf-8 -*-
"""
Trend-following breakout engine (Donchian + trend filter + Chandelier trail).
The classic, robust CTA / Turtle approach — trades WITH the trend, rides winners.

Entry (long)  : close breaks above highest-high of prior N bars AND close > trend EMA
Entry (short) : close breaks below lowest-low  of prior N bars AND close < trend EMA
Stop          : initial = entry -/+ ATR*stopMult ; then Chandelier trail (ATR*trailMult)
Sizing        : risk% of equity / initial stop distance
Costs         : per-instrument spread+slippage (price units)
No look-ahead : breakout uses PRIOR bars; entries at bar close; exits intrabar via H/L.
"""
import csv, datetime as dt, numpy as np

START_EQ = 10000.0

# --- default spread (price units) per data file (spread + slippage) ---
SPREADS = {
    "eurusd": 0.00012, "audusd": 0.00012, "gbpusd": 0.00012,
    "gold":   0.35,    "nas":    1.0,
}
def spread_for(path):
    for k, v in SPREADS.items():
        if k in path:
            return v
    return 0.00012

# ------------------------- indicators -----------------------------
def ema(arr, length):
    out = np.empty(len(arr)); out[:] = np.nan
    k = 2 / (length + 1); s = None
    for i, v in enumerate(arr):
        s = v if s is None else (v - s) * k + s
        out[i] = s
    return out

def atr(h, l, c, length):
    tr = np.empty(len(c))
    for i in range(len(c)):
        tr[i] = h[i]-l[i] if i == 0 else max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
    out = np.empty(len(c)); out[:] = np.nan; s = None
    for i in range(len(c)):
        s = tr[i] if s is None else (s*(length-1)+tr[i])/length
        out[i] = s
    return out

def rolling_extreme(arr, N, kind):
    out = np.empty(len(arr)); out[:] = np.nan
    for i in range(len(arr)):
        if i >= N:
            window = arr[i-N:i]               # PRIOR N bars (excludes current)
            out[i] = window.max() if kind == "max" else window.min()
    return out

def load(path):
    ts, o, h, l, c = [], [], [], [], []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ts.append(int(row["timestamp"])); o.append(float(row["open"]))
            h.append(float(row["high"])); l.append(float(row["low"])); c.append(float(row["close"]))
    return (np.array(ts), np.array(o), np.array(h), np.array(l), np.array(c))

# --------------------------- engine -------------------------------
def run(path, entry_len=20, trend_len=200, atr_len=14,
        stop_mult=2.0, trail_mult=3.0, risk_pct=0.5, side=0,
        frac_start=0.0, frac_end=1.0, spread=None, return_trades=False):
    ts, o, h, l, c = load(path)
    spread = spread_for(path) if spread is None else spread
    trend = ema(c, trend_len)
    a     = atr(h, l, c, atr_len)
    hh    = rolling_extreme(h, entry_len, "max")
    ll    = rolling_extreme(l, entry_len, "min")

    n = len(c)
    i0 = max(1, int(n*frac_start)); i1 = int(n*frac_end)

    equity = START_EQ; peak = equity; max_dd = 0.0
    trades = []; pos = None

    for i in range(i0, i1):
        if np.isnan(trend[i]) or np.isnan(a[i]) or np.isnan(hh[i]) or np.isnan(ll[i]):
            continue

        # ---- manage open position (Chandelier trail, intrabar) ----
        if pos is not None:
            if pos["dir"] == 1:
                pos["hh"] = max(pos["hh"], h[i])
                pos["stop"] = max(pos["stop"], pos["hh"] - a[i]*trail_mult)
                hit = l[i] <= pos["stop"]
                fill = min(o[i], pos["stop"]) if o[i] <= pos["stop"] else pos["stop"]
            else:
                pos["ll"] = min(pos["ll"], l[i])
                pos["stop"] = min(pos["stop"], pos["ll"] + a[i]*trail_mult)
                hit = h[i] >= pos["stop"]
                fill = max(o[i], pos["stop"]) if o[i] >= pos["stop"] else pos["stop"]
            if hit:
                pnl = (fill - pos["entry"])*pos["qty"]*pos["dir"] - spread*pos["qty"]
                equity += pnl
                trades.append({"dir": pos["dir"], "pnl": pnl, "won": pnl > 0,
                               "R": pnl/pos["risk_amt"], "ts": ts[i]})
                pos = None

        peak = max(peak, equity)
        max_dd = max(max_dd, (peak-equity)/peak*100)

        # ---- entry (flat only) ----
        if pos is None:
            sig = 0
            if c[i] > hh[i] and c[i] > trend[i]:
                sig = 1
            elif c[i] < ll[i] and c[i] < trend[i]:
                sig = -1
            if side != 0 and sig != side:
                sig = 0
            if sig != 0:
                sd = a[i]*stop_mult
                if sd > 0:
                    qty = (equity*risk_pct/100.0)/sd
                    pos = {"dir": sig, "entry": c[i], "qty": qty,
                           "risk_amt": equity*risk_pct/100.0,
                           "stop": c[i]-sd if sig == 1 else c[i]+sd,
                           "hh": h[i], "ll": l[i]}

    years = (ts[i1-1]-ts[i0])/ (365.25*24*3600) if i1 > i0 else 0
    if return_trades:
        return trades
    return summarize(trades, equity, max_dd, years)

def summarize(trades, equity, max_dd, years):
    n = len(trades)
    wins = [t for t in trades if t["won"]]
    gw = sum(t["pnl"] for t in wins)
    gl = -sum(t["pnl"] for t in trades if not t["won"])
    pf = gw/gl if gl > 0 else float("inf")
    net = (equity-START_EQ)/START_EQ*100
    cagr = ((equity/START_EQ)**(1/years)-1)*100 if years > 0.2 and equity > 0 else float("nan")
    return {"trades": n, "win_rate": (len(wins)/n*100 if n else 0), "net_pct": net,
            "cagr": cagr, "profit_factor": pf, "max_dd": max_dd,
            "avg_R": (np.mean([t["R"] for t in trades]) if n else 0),
            "years": years}

def line(name, r):
    pf = "inf" if r["profit_factor"] == float("inf") else f"{r['profit_factor']:.2f}"
    cagr = "n/a" if r["cagr"] != r["cagr"] else f"{r['cagr']:+.1f}%"
    win = r["profit_factor"] > 1.0 and r["net_pct"] > 0
    print(f"  {name:<30} | {'WIN ' if win else 'LOSS'} | trd {r['trades']:>4} | "
          f"win {r['win_rate']:>4.1f}% | net {r['net_pct']:>+7.1f}% | CAGR {cagr:>6} | "
          f"PF {pf:>4} | DD {r['max_dd']:>5.1f}%")
