# -*- coding: utf-8 -*-
"""
Diversified trend-following PORTFOLIO backtest.
Runs the SAME robust breakout system on several trending instruments and merges
their trades onto one compounding equity curve (risk% of live equity per trade).
This is how professional CTAs deploy — the big trends (gold) carry the basket,
and diversification smooths the equity curve.
"""
import numpy as np
import trend as t

# instrument -> (data file, realistic spread in price units)
UNIVERSE = {
    "GOLD":   ("gold_d1.csv",   0.35),
    "CRUDE":  ("crude_d1.csv",  0.03),
    "NASDAQ": ("nas_d1.csv",    1.0),
    "BITCOIN":("btc_d1.csv",    20.0),
}

PARAMS = dict(entry_len=40, trend_len=200, atr_len=14, stop_mult=2.0, trail_mult=3.0)

def collect(instruments, frac_start=0.0, frac_end=1.0):
    """Gather all trades (with close timestamp + R multiple) across instruments."""
    allt = []
    per = {}
    for name in instruments:
        f, sp = UNIVERSE[name]
        trs = t.run(f, spread=sp, risk_pct=1.0, frac_start=frac_start,
                    frac_end=frac_end, return_trades=True, **PARAMS)
        per[name] = trs
        for tr in trs:
            allt.append((tr["ts"], name, tr["R"]))
    allt.sort(key=lambda x: x[0])          # chronological by close time
    return allt, per

def simulate(allt, risk_pct=1.0, start_eq=10000.0):
    """Compound one shared account: each closed trade moves equity by risk% * R."""
    eq = start_eq; peak = eq; max_dd = 0.0
    wins = 0; gw = 0.0; gl = 0.0; curve = []
    for ts, name, R in allt:
        pnl = eq * (risk_pct/100.0) * R
        eq += pnl
        if pnl > 0: wins += 1; gw += pnl
        else:       gl -= pnl
        peak = max(peak, eq); max_dd = max(max_dd, (peak-eq)/peak*100)
        curve.append((ts, eq))
    n = len(allt)
    pf = gw/gl if gl > 0 else float("inf")
    net = (eq-start_eq)/start_eq*100
    years = (allt[-1][0]-allt[0][0])/(365.25*24*3600) if n > 1 else 0
    cagr = ((eq/start_eq)**(1/years)-1)*100 if years > 0.2 else float("nan")
    return dict(trades=n, win_rate=wins/n*100 if n else 0, net_pct=net, cagr=cagr,
                profit_factor=pf, max_dd=max_dd, final_eq=eq, years=years)

def show(name, r):
    pf = "inf" if r["profit_factor"] == float("inf") else f"{r['profit_factor']:.2f}"
    cagr = "n/a" if r["cagr"] != r["cagr"] else f"{r['cagr']:+.1f}%"
    print(f"  {name:<26} | trd {r['trades']:>4} | win {r['win_rate']:>4.1f}% | "
          f"net {r['net_pct']:>+8.1f}% | CAGR {cagr:>6} | PF {pf:>4} | "
          f"DD {r['max_dd']:>5.1f}% | ${r['final_eq']:>10,.0f}")

if __name__ == "__main__":
    RISK = 1.0
    core = ["GOLD", "CRUDE", "NASDAQ"]
    full = ["GOLD", "CRUDE", "NASDAQ", "BITCOIN"]

    print("="*104)
    print(f"  DIVERSIFIED TREND PORTFOLIO | DAILY 10y | risk {RISK}%/trade | breakout40 + Chandelier trail")
    print("="*104)

    print("\n-- each instrument standalone (risk 1%) --")
    for name in full:
        allt, _ = collect([name])
        show(name, simulate(allt, RISK))

    print("\n-- PORTFOLIOS (merged, compounding, shared account) --")
    allt, _ = collect(core)
    show("CORE: Gold+Crude+Nasdaq", simulate(allt, RISK))
    allt, _ = collect(full)
    show("FULL: +Bitcoin", simulate(allt, RISK))

    print("\n-- CORE portfolio OUT-OF-SAMPLE --")
    a_tr, _ = collect(core, 0.0, 0.6); show("TRAIN first 60%", simulate(a_tr, RISK))
    a_te, _ = collect(core, 0.6, 1.0); show("TEST  last 40%",  simulate(a_te, RISK))
