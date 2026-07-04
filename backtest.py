# -*- coding: utf-8 -*-
"""
Backtest for the EMA 50/200 strategy on EUR/USD M15.
Replicates the Pine Script logic + the 3 new features:
  1) Trailing stop (ATR based)
  2) Stats "dashboard" (printed summary)
  3) Daily loss brake (stop trading after N losses / X% daily loss)
"""
import csv, datetime as dt, numpy as np

# ----------------------------- params -----------------------------
EMA_FAST   = 50
EMA_SLOW   = 200
ATR_LEN    = 14
ATR_MULT   = 1.5
RISK_PCT   = 1.0      # % equity risked per trade
MIN_RR     = 1.0      # reject trades with reward/risk below this
USE_TREND  = True
DYNAMIC_TP = True     # target follows the 200 EMA
SPREAD     = 0.00010  # ~1 pip cost applied per round trip
START_EQ   = 10000.0

# ------------------------- helpers --------------------------------
def ema(arr, length):
    out = np.empty(len(arr)); out[:] = np.nan
    k = 2 / (length + 1)
    s = None
    for i, v in enumerate(arr):
        s = v if s is None else (v - s) * k + s
        out[i] = s
    return out

def atr(h, l, c, length):
    tr = np.empty(len(c)); tr[:] = np.nan
    for i in range(len(c)):
        if i == 0:
            tr[i] = h[i] - l[i]
        else:
            tr[i] = max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
    # Wilder's smoothing
    out = np.empty(len(c)); out[:] = np.nan
    s = None
    for i in range(len(c)):
        s = tr[i] if s is None else (s*(length-1)+tr[i])/length
        out[i] = s
    return out

def load(path):
    ts, o, h, l, c = [], [], [], [], []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ts.append(int(row["timestamp"]))
            o.append(float(row["open"])); h.append(float(row["high"]))
            l.append(float(row["low"]));  c.append(float(row["close"]))
    return (np.array(ts), np.array(o), np.array(h), np.array(l), np.array(c))

# --------------------------- engine -------------------------------
DATA_FILE = "eurusd_m15.csv"   # override before calling run()

def run(use_trailing=True, use_brake=True,
        max_daily_losses=3, max_daily_loss_pct=3.0,
        tp_r=None, invert=False, side=0, slope=0,
        frac_start=0.0, frac_end=1.0):
    # tp_r: None -> target = 200 EMA (image default). number -> fixed R multiple.
    # invert: take the opposite side of every signal.
    # side: 0 = both, 1 = longs only, -1 = shorts only.
    # slope: 0 = off. >0 = 200 EMA trend filter over N bars
    #        (long only if 200 EMA rising, short only if falling).
    # frac_start/frac_end: trade only within this fraction of bars
    #        (indicators still computed on the full series -> clean warmup).
    ts, o, h, l, c = load(DATA_FILE)
    ef = ema(c, EMA_FAST); es = ema(c, EMA_SLOW); a = atr(h, l, c, ATR_LEN)
    n = len(c)
    i_start = max(1, int(n * frac_start))
    i_end   = int(n * frac_end)

    equity = START_EQ
    peak = equity
    max_dd = 0.0
    eq_curve = []
    trades = []          # dict per closed trade
    pos = None           # open position

    # daily brake state
    cur_day = None
    day_start_eq = equity
    day_losses = 0
    blocked = False

    for i in range(i_start, i_end):
        if np.isnan(es[i]) or np.isnan(a[i]):
            eq_curve.append(equity); continue

        day = dt.datetime.utcfromtimestamp(ts[i]).date()
        if day != cur_day:
            cur_day = day
            day_start_eq = equity
            day_losses = 0
            blocked = False

        # ---- manage open position on THIS bar (intrabar via H/L) ----
        if pos is not None:
            # fixed R target -> locked price; else dynamic 200 EMA
            tp = pos["tp"] if pos["fixed"] else (es[i] if DYNAMIC_TP else pos["tp"])
            if use_trailing:
                if pos["dir"] == 1:
                    pos["stop"] = max(pos["stop"], h[i] - a[i]*ATR_MULT)
                else:
                    pos["stop"] = min(pos["stop"], l[i] + a[i]*ATR_MULT)

            exit_px = None
            if pos["dir"] == 1:                       # long
                if l[i] <= pos["stop"]:               # stop first (conservative)
                    exit_px = pos["stop"]
                elif h[i] >= tp:
                    exit_px = tp
            else:                                     # short
                if h[i] >= pos["stop"]:
                    exit_px = pos["stop"]
                elif l[i] <= tp:
                    exit_px = tp

            if exit_px is not None:
                gross = (exit_px - pos["entry"]) * pos["qty"] * pos["dir"]
                cost  = SPREAD * pos["qty"]
                pnl   = gross - cost
                equity += pnl
                won = pnl > 0
                if not won:
                    day_losses += 1
                trades.append({"dir": pos["dir"], "pnl": pnl, "won": won,
                               "R": pnl / pos["risk_amt"]})
                pos = None

        # ---- equity curve / drawdown ----
        peak = max(peak, equity)
        dd = (peak - equity) / peak * 100
        max_dd = max(max_dd, dd)
        eq_curve.append(equity)

        # ---- daily brake check ----
        if use_brake and not blocked:
            day_loss_pct = (day_start_eq - equity) / day_start_eq * 100
            if day_losses >= max_daily_losses or day_loss_pct >= max_daily_loss_pct:
                blocked = True

        # ---- look for entry (only if flat & not blocked) ----
        if pos is None and not blocked:
            cross_dn = c[i] < ef[i] and c[i-1] >= ef[i-1]
            cross_up = c[i] > ef[i] and c[i-1] <= ef[i-1]
            # Geometry of the image: price reverts from the 50 EMA toward the 200 EMA.
            # SHORT -> 200 sits BELOW price (downside target): es < close
            # LONG  -> 200 sits ABOVE price (upside  target): es > close
            trend_dn = (not USE_TREND) or (es[i] < c[i])
            trend_up = (not USE_TREND) or (es[i] > c[i])
            stop_dist = a[i] * ATR_MULT
            risk_cap = equity * RISK_PCT / 100.0

            sig = 0
            if cross_dn and trend_dn:
                sig = -1
            elif cross_up and trend_up:
                sig = 1
            if invert:
                sig = -sig
            if slope > 0 and i >= slope:               # 200 EMA trend filter
                if sig == 1 and not (es[i] > es[i-slope]):
                    sig = 0
                if sig == -1 and not (es[i] < es[i-slope]):
                    sig = 0
            if side != 0 and sig != side:
                sig = 0

            if sig != 0 and stop_dist > 0:
                qty = risk_cap / stop_dist
                if tp_r is None:                      # target = 200 EMA (image)
                    tp = es[i]
                    ok = (c[i]-tp)/stop_dist >= MIN_RR if sig < 0 else (tp-c[i])/stop_dist >= MIN_RR
                    ok = ok and ((tp < c[i]) if sig < 0 else (tp > c[i]))
                    fixed = False
                else:                                  # fixed R-multiple target
                    tp = c[i] - tp_r*stop_dist if sig < 0 else c[i] + tp_r*stop_dist
                    ok = True
                    fixed = True
                if ok:
                    stop = c[i] + stop_dist if sig < 0 else c[i] - stop_dist
                    pos = {"dir": sig, "entry": c[i], "stop": stop,
                           "tp": tp, "qty": qty, "risk_amt": risk_cap, "fixed": fixed}

    return summarize(trades, equity, max_dd, eq_curve)

def summarize(trades, equity, max_dd, eq_curve):
    n = len(trades)
    wins = [t for t in trades if t["won"]]
    losses = [t for t in trades if not t["won"]]
    gross_w = sum(t["pnl"] for t in wins)
    gross_l = -sum(t["pnl"] for t in losses)
    pf = (gross_w / gross_l) if gross_l > 0 else float("inf")
    win_rate = (len(wins)/n*100) if n else 0
    net = equity - START_EQ
    net_pct = net / START_EQ * 100
    avg_r = np.mean([t["R"] for t in trades]) if n else 0
    return {
        "trades": n, "win_rate": win_rate, "net_pct": net_pct,
        "final_eq": equity, "profit_factor": pf, "max_dd": max_dd,
        "avg_R": avg_r, "wins": len(wins), "losses": len(losses),
    }

def show(name, r):
    pf = "inf" if r["profit_factor"] == float("inf") else f"{r['profit_factor']:.2f}"
    print(f"\n=== {name} ===")
    print(f"  Trades........... {r['trades']}  (W {r['wins']} / L {r['losses']})")
    print(f"  Win rate......... {r['win_rate']:.1f}%")
    print(f"  Net P&L.......... {r['net_pct']:+.2f}%   (final ${r['final_eq']:,.0f})")
    print(f"  Profit factor.... {pf}")
    print(f"  Max drawdown..... {r['max_dd']:.2f}%")
    print(f"  Avg R per trade.. {r['avg_R']:+.2f}R")

if __name__ == "__main__":
    print("EUR/USD M15  |  EMA 50/200 strategy  |  60-day backtest")
    print("\n########## IMAGE STRATEGY (target = 200 EMA) ##########")
    show("Baseline (no trailing, no brake)", run(False, False))
    show("+ Trailing stop",                  run(True,  False))
    show("+ Daily brake",                    run(False, True))
    show("+ Trailing + Daily brake (FULL)",  run(True,  True))

    print("\n########## VARIANTS (can we fix it?) ##########")
    show("Fixed target 1.5R",                run(False, False, tp_r=1.5))
    show("Fixed target 2R",                  run(False, False, tp_r=2.0))
    show("Fixed target 1.5R + brake",        run(False, True,  tp_r=1.5))
    show("INVERTED signal, target 200 EMA",  run(False, False, invert=True))
    show("INVERTED signal, fixed 2R",        run(False, False, tp_r=2.0, invert=True))
