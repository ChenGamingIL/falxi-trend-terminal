# -*- coding: utf-8 -*-
"""
Robustness validation for the EMA 50/200 bot.
Winning config: fixed 1.5R target + daily brake, no trailing, risk 0.5%, both sides.
Tests: multi-year, multi-instrument, and out-of-sample (train/test) split.
"""
import backtest as b

b.RISK_PCT = 0.5           # prop-safe sizing
CFG = dict(use_trailing=False, use_brake=True, tp_r=1.5)   # the winning config

def line(name, r):
    pf = "inf" if r["profit_factor"] == float("inf") else f"{r['profit_factor']:.2f}"
    verdict = "WIN " if (r["profit_factor"] > 1.0 and r["net_pct"] > 0) else "LOSS"
    print(f"  {name:<34} | {verdict} | trades {r['trades']:>4} | "
          f"win {r['win_rate']:>4.1f}% | net {r['net_pct']:>+7.2f}% | "
          f"PF {pf:>4} | DD {r['max_dd']:>5.2f}%")

def block(title):
    print("\n" + "=" * 96)
    print(f"  {title}")
    print("=" * 96)

# ---------------------------------------------------------------------------
# 1) MULTI-INSTRUMENT, full history, H1
# ---------------------------------------------------------------------------
block("1) MULTI-INSTRUMENT  (H1, full history, winning config)")
insts = [("EUR/USD ~2.8y", "eurusd_h1_2y.csv"),
         ("GBP/USD ~2.8y", "gbpusd_h1.csv"),
         ("GOLD    ~2.4y", "gold_h1.csv"),
         ("NASDAQ  ~2.4y", "nas_h1.csv")]
for name, f in insts:
    b.DATA_FILE = f
    line(name + " BOTH",   b.run(**CFG))
    line(name + " SHORTS", b.run(side=-1, **CFG))
    line(name + " LONGS",  b.run(side=1,  **CFG))
    print("  " + "-" * 90)

# ---------------------------------------------------------------------------
# 2) OUT-OF-SAMPLE split on EUR/USD H1 (~2.8y)
#    train = first 60%, test = last 40% (unseen)
# ---------------------------------------------------------------------------
block("2) OUT-OF-SAMPLE  (EUR/USD H1 ~2.8y)  train 60% / test 40%")
b.DATA_FILE = "eurusd_h1_2y.csv"
line("FULL period       BOTH",   b.run(**CFG))
line("TRAIN (first 60%) BOTH",   b.run(frac_start=0.0, frac_end=0.6, **CFG))
line("TEST  (last  40%) BOTH",   b.run(frac_start=0.6, frac_end=1.0, **CFG))
print("  " + "-" * 90)
line("TEST  (last  40%) SHORTS", b.run(frac_start=0.6, frac_end=1.0, side=-1, **CFG))
line("TEST  (last  40%) LONGS",  b.run(frac_start=0.6, frac_end=1.0, side=1,  **CFG))

# ---------------------------------------------------------------------------
# 3) LONG-TERM check on EUR/USD DAILY (10y)
# ---------------------------------------------------------------------------
block("3) LONG-TERM  (EUR/USD DAILY, 10 years)")
b.DATA_FILE = "eurusd_d1.csv"
line("Daily 10y  BOTH  (no brake)",  b.run(use_trailing=False, use_brake=False, tp_r=1.5))
line("Daily 10y  SHORTS(no brake)",  b.run(use_trailing=False, use_brake=False, tp_r=1.5, side=-1))
line("Daily 10y  LONGS (no brake)",  b.run(use_trailing=False, use_brake=False, tp_r=1.5, side=1))

print("\nDone.")
