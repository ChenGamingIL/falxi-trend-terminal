# -*- coding: utf-8 -*-
"""Resample an H1 CSV into H4 (blocks of 4 bars). Usage: py resample.py in.csv out.csv 4"""
import csv, sys

def main(inp, out, k):
    rows = []
    with open(inp, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append((int(r["timestamp"]), float(r["open"]), float(r["high"]),
                         float(r["low"]), float(r["close"])))
    with open(out, "w", encoding="utf-8") as f:
        f.write("timestamp,open,high,low,close\n")
        for i in range(0, len(rows) - k + 1, k):
            block = rows[i:i+k]
            ts = block[0][0]; o = block[0][1]
            h = max(b[2] for b in block); l = min(b[3] for b in block)
            c = block[-1][4]
            f.write(f"{ts},{o},{h},{l},{c}\n")
    print(f"{inp} -> {out}: {len(rows)} -> {(len(rows)//k)} bars (x{k})")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]))
