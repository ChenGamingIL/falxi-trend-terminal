# -*- coding: utf-8 -*-
"""Fetch EUR/USD 15-minute OHLC data from Yahoo Finance -> eurusd_m15.csv"""
import json, ssl, sys, time, urllib.request

# args: interval range outfile symbol   (default: 15m 60d eurusd_m15.csv EURUSD=X)
INTERVAL = sys.argv[1] if len(sys.argv) > 1 else "15m"
RANGE    = sys.argv[2] if len(sys.argv) > 2 else "60d"
OUTFILE  = sys.argv[3] if len(sys.argv) > 3 else "eurusd_m15.csv"
SYMBOL   = sys.argv[4] if len(sys.argv) > 4 else "EURUSD=X"

URL = (f"https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL}"
       f"?interval={INTERVAL}&range={RANGE}")
HEADERS = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/124.0 Safari/537.36")}

def fetch(url, tries=5):
    ctx = ssl.create_default_context()
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
                return r.read()
        except Exception as e:
            last = e
            wait = 3 * (i + 1)
            print(f"  attempt {i+1} failed: {e}; retry in {wait}s", flush=True)
            time.sleep(wait)
    raise last

def main():
    raw = fetch(URL)
    data = json.loads(raw)
    res = data["chart"]["result"][0]
    ts = res["timestamp"]
    q = res["indicators"]["quote"][0]
    o, h, l, c = q["open"], q["high"], q["low"], q["close"]
    rows = []
    for i in range(len(ts)):
        if None in (o[i], h[i], l[i], c[i]):
            continue
        rows.append((ts[i], o[i], h[i], l[i], c[i]))
    with open(OUTFILE, "w", encoding="utf-8") as f:
        f.write("timestamp,open,high,low,close\n")
        for t, oo, hh, ll, cc in rows:
            f.write(f"{t},{oo},{hh},{ll},{cc}\n")
    print(f"Saved {len(rows)} bars to {OUTFILE}")
    if rows:
        import datetime as dt
        a = dt.datetime.utcfromtimestamp(rows[0][0])
        b = dt.datetime.utcfromtimestamp(rows[-1][0])
        print(f"Range: {a} -> {b} (UTC)")

if __name__ == "__main__":
    main()
