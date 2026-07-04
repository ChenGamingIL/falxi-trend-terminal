# -*- coding: utf-8 -*-
"""
Daily signal engine + forward-test journal for the validated trend portfolio.

Runs the EXACT Universal_Trend_Bot logic (Donchian 40 breakout + EMA 200 filter,
2*ATR initial stop -> 3*ATR Chandelier trail, daily bars) on fresh Yahoo data
and reports, per instrument: current position state, live stop level, any NEW
entry signal on the last closed bar, and position size for your equity/risk.

Every run appends the state to forward_log.csv (one row per instrument per day)
so live performance can later be compared against the backtest honestly.

Usage:
    py signals.py                # equity $10,000, risk 0.75%
    py signals.py 25000 0.5      # equity $25,000, risk 0.5%

Run it once a day AFTER the daily close (early morning Israel time works).
"""
import csv, datetime as dt, json, os, ssl, sys, time, urllib.request
import numpy as np
from trend import ema, atr, rolling_extreme

PARAMS = dict(entry_len=40, trend_len=200, atr_len=14, stop_mult=2.0, trail_mult=3.0)

# name -> (yahoo symbol, decimals for display)
UNIVERSE = {
    "GOLD":    ("GC=F",    1),
    "CRUDE":   ("CL=F",    2),
    "NASDAQ":  ("^NDX",    0),
    "BITCOIN": ("BTC-USD", 0),
}

LOG_FILE = "forward_log.csv"
HEADERS = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/124.0 Safari/537.36")}

def fetch_daily(symbol, rng="2y", tries=4):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
           f"?interval=1d&range={rng}")
    ctx = ssl.create_default_context()
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
                data = json.loads(r.read())
            res = data["chart"]["result"][0]
            ts = res["timestamp"]
            q = res["indicators"]["quote"][0]
            rows = [(ts[i], q["open"][i], q["high"][i], q["low"][i], q["close"][i])
                    for i in range(len(ts))
                    if None not in (q["open"][i], q["high"][i], q["low"][i], q["close"][i])]
            return rows
        except Exception as e:
            last = e
            time.sleep(3 * (i + 1))
    raise last

def replay(ts, o, h, l, c, entry_len, trend_len, atr_len, stop_mult, trail_mult):
    """Walk the whole history with the exact bot logic; return end-of-data state."""
    trend = ema(c, trend_len)
    a = atr(h, l, c, atr_len)
    hh = rolling_extreme(h, entry_len, "max")
    ll = rolling_extreme(l, entry_len, "min")
    pos = None
    n = len(c)
    for i in range(n):
        if np.isnan(trend[i]) or np.isnan(a[i]) or np.isnan(hh[i]) or np.isnan(ll[i]):
            continue
        if pos is not None:
            if pos["dir"] == 1:
                pos["hh"] = max(pos["hh"], h[i])
                pos["stop"] = max(pos["stop"], pos["hh"] - a[i] * trail_mult)
                if l[i] <= pos["stop"]:
                    pos = None
            else:
                pos["ll"] = min(pos["ll"], l[i])
                pos["stop"] = min(pos["stop"], pos["ll"] + a[i] * trail_mult)
                if h[i] >= pos["stop"]:
                    pos = None
        if pos is None:
            if c[i] > hh[i] and c[i] > trend[i]:
                pos = {"dir": 1, "entry": c[i], "entry_ts": ts[i],
                       "stop": c[i] - a[i] * stop_mult, "hh": h[i], "ll": l[i],
                       "risk_dist": a[i] * stop_mult, "new": i == n - 1}
            elif c[i] < ll[i] and c[i] < trend[i]:
                pos = {"dir": -1, "entry": c[i], "entry_ts": ts[i],
                       "stop": c[i] + a[i] * stop_mult, "hh": h[i], "ll": l[i],
                       "risk_dist": a[i] * stop_mult, "new": i == n - 1}
    return pos, a[-1], trend[-1], c[-1], ts[-1]

def log_state(date_str, name, state, close, stop):
    rows = {}
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                rows[(r["date"], r["instrument"])] = r
    rows[(date_str, name)] = {"date": date_str, "instrument": name, "state": state,
                              "close": f"{close:.4f}", "stop": ("" if stop is None else f"{stop:.4f}")}
    with open(LOG_FILE, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "instrument", "state", "close", "stop"])
        w.writeheader()
        for k in sorted(rows):
            w.writerow(rows[k])

def main():
    equity = float(sys.argv[1]) if len(sys.argv) > 1 else 10000.0
    risk_pct = float(sys.argv[2]) if len(sys.argv) > 2 else 0.75
    today_utc = dt.datetime.now(dt.timezone.utc).date()

    print("=" * 78)
    print(f"  TREND PORTFOLIO SIGNALS | equity ${equity:,.0f} | risk {risk_pct}%/trade"
          f" | {today_utc}")
    print("=" * 78)

    actions = []
    for name, (symbol, dec) in UNIVERSE.items():
        try:
            rows = fetch_daily(symbol)
        except Exception as e:
            print(f"\n  {name:<8} !! data fetch failed: {e}")
            continue
        # drop today's still-forming bar: signals are valid on CLOSED bars only
        if dt.datetime.fromtimestamp(rows[-1][0], dt.timezone.utc).date() >= today_utc:
            rows = rows[:-1]
        ts = np.array([r[0] for r in rows])
        o, h, l, c = (np.array([r[k] for r in rows]) for k in (1, 2, 3, 4))

        pos, last_atr, last_trend, last_close, last_ts = replay(ts, o, h, l, c, **PARAMS)
        bar_date = dt.datetime.fromtimestamp(int(last_ts), dt.timezone.utc).date()
        risk_amt = equity * risk_pct / 100.0
        f = f"{{:,.{dec}f}}".format

        print(f"\n  {name:<8} ({symbol})  last closed bar: {bar_date}  close {f(last_close)}")
        print(f"           trend: {'UP' if last_close > last_trend else 'DOWN'} "
              f"(EMA200 {f(last_trend)})  ATR {f(last_atr)}")

        if pos is None:
            print("           position: FLAT — no action. Wait for breakout.")
            log_state(str(bar_date), name, "flat", last_close, None)
        else:
            side = "LONG" if pos["dir"] == 1 else "SHORT"
            entry_d = dt.datetime.fromtimestamp(int(pos["entry_ts"]), dt.timezone.utc).date()
            stop_dist = abs(pos["entry"] - (pos["entry"] - pos["dir"] * PARAMS["stop_mult"] * last_atr))
            if pos["new"]:
                dist = PARAMS["stop_mult"] * last_atr
                qty = risk_amt / dist
                print(f"           *** NEW {side} SIGNAL on this close ***")
                print(f"           enter {side} @ ~{f(last_close)} | initial stop {f(pos['stop'])}")
                print(f"           size: {qty:.4f} units (risk ${risk_amt:,.0f} over {f(dist)} stop distance)")
                actions.append(f"{name}: ENTER {side} @ ~{f(last_close)}, stop {f(pos['stop'])}, {qty:.4f} units")
                log_state(str(bar_date), name, f"enter_{side.lower()}", last_close, pos["stop"])
            else:
                print(f"           position: {side} since {entry_d} @ {f(pos['entry'])}")
                print(f"           trailing stop -> {f(pos['stop'])}  (update your stop to this)")
                actions.append(f"{name}: hold {side}, move stop to {f(pos['stop'])}")
                log_state(str(bar_date), name, side.lower(), last_close, pos["stop"])

    print("\n" + "=" * 78)
    if actions:
        print("  ACTION LIST:")
        for a in actions:
            print(f"   -> {a}")
    else:
        print("  ACTION LIST: nothing to do today. All flat.")
    print(f"  (state journaled to {LOG_FILE})")
    print("=" * 78)

if __name__ == "__main__":
    main()
