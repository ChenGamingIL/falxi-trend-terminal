# -*- coding: utf-8 -*-
"""Second pass: ICT with the standard HTF trend filter (EMA 200), both modes."""
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
    ("NASDAQ D1 (10y)", "nas_d1.csv"),
]

print("=" * 100)
print("CHoCH-only + EMA200 trend filter")
print("=" * 100)
for name, path in DATASETS:
    ict.line(name, ict.run(path, mode="choch", trend_len=200))

print()
print("=" * 100)
print("CHoCH+BOS + EMA200 trend filter")
print("=" * 100)
for name, path in DATASETS:
    ict.line(name, ict.run(path, mode="both", trend_len=200))

print()
print("=" * 100)
print("OOS 60/40 for any promising combo (gold H4/H1, filtered)")
print("=" * 100)
for name, path, mode in [("GOLD H4 choch+f", "gold_h4.csv", "choch"),
                         ("GOLD H4 both +f", "gold_h4.csv", "both"),
                         ("GOLD H1 both +f", "gold_h1.csv", "both"),
                         ("NASDAQ D1 both+f", "nas_d1.csv", "both")]:
    tr = ict.run(path, mode=mode, trend_len=200, frac_end=0.6)
    te = ict.run(path, mode=mode, trend_len=200, frac_start=0.6)
    ict.line(f"{name} TRAIN", tr)
    ict.line(f"{name} TEST ", te)
