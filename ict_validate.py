# -*- coding: utf-8 -*-
"""Full validation suite for the ICT BOS/CHoCH/Order-Block strategy."""
import ict

DATASETS = [
    ("EURUSD H1 (2y)",  "eurusd_h1_2y.csv"),
    ("EURUSD H4 (2y)",  "eurusd_h4.csv"),
    ("EURUSD D1 (10y)", "eurusd_d1.csv"),
    ("AUDUSD H1 (2y)",  "audusd_h1.csv"),
    ("AUDUSD H4 (2y)",  "audusd_h4.csv"),
    ("AUDUSD D1 (10y)", "audusd_d1.csv"),
    ("GOLD   H1 (2y)",  "gold_h1.csv"),
    ("GOLD   H4 (2y)",  "gold_h4.csv"),
    ("GOLD   D1 (10y)", "gold_d1.csv"),
]

EXTRA_D1 = [
    ("GBPUSD H1 (2y)",  "gbpusd_h1.csv"),
    ("USDJPY D1 (10y)", "usdjpy_d1.csv"),
    ("NASDAQ D1 (10y)", "nas_d1.csv"),
    ("CRUDE  D1 (10y)", "crude_d1.csv"),
    ("SILVER D1 (10y)", "silver_d1.csv"),
    ("BTC    D1 (10y)", "btc_d1.csv"),
]

def block(title):
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)

# ---- 1. baseline: the exact setup from the image (CHoCH + OB retest, R:R 1:2, risk 0.5%) ----
block("1. CHoCH + Order Block retest  (the image setup)  |  swing_n=5, R:R 1:2, risk 0.5%")
for name, path in DATASETS:
    ict.line(name, ict.run(path, mode="choch"))

# ---- 2. adding BOS continuations ----
block("2. CHoCH + BOS (continuation trades added)")
for name, path in DATASETS:
    ict.line(name, ict.run(path, mode="both"))

# ---- 3. other instruments, daily ----
block("3. Other instruments (mode=both)")
for name, path in EXTRA_D1:
    ict.line(name, ict.run(path, mode="both"))

# ---- 4. parameter stability on the most promising rows (filled after first pass) ----
block("4. Parameter stability: swing_n sweep (mode=both)")
for name, path in DATASETS:
    print(f"  {name}")
    for sn in (3, 4, 5, 7, 10):
        ict.line(f"    swing_n={sn}", ict.run(path, mode="both", swing_n=sn))

block("5. Parameter stability: R:R sweep (mode=both, swing_n=5)")
for name, path in [("GOLD D1", "gold_d1.csv"), ("EURUSD H1", "eurusd_h1_2y.csv"),
                   ("GOLD H4", "gold_h4.csv")]:
    print(f"  {name}")
    for rr in (1.5, 2.0, 2.5, 3.0):
        ict.line(f"    rr={rr}", ict.run(path, mode="both", rr=rr))

# ---- 6. out-of-sample split 60/40 ----
block("6. Out-of-sample 60/40 split (mode=both)")
for name, path in DATASETS:
    tr = ict.run(path, mode="both", frac_end=0.6)
    te = ict.run(path, mode="both", frac_start=0.6)
    ict.line(f"{name} TRAIN", tr)
    ict.line(f"{name} TEST ", te)
