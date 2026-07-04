# -*- coding: utf-8 -*-
"""
סורק קרנות REIT
================
שולף עבור כל טיקר: מחיר, תשואת דיבידנד, שווי שוק, ו-FFO מקורב (המדד החשוב ל-REIT).
שומר שורת היסטוריה ל-CSV ומתריע כשתשואת הדיבידנד חוצה את הסף שהוגדר ב-config.json.

FFO (Funds From Operations) ≈ רווח נקי + פחת והפחתות.
זה הקירוב המקובל, כי ב-REIT הפחת החשבונאי על נכסים מעוות את הרווח הנקי (EPS).
לכן P/FFO אמין יותר מ-P/E להערכת שווי של קרן נדל"ן.

הרצה:
    py reit_scanner.py
"""

import json
import os
import sys
from datetime import datetime

try:
    import yfinance as yf
except ImportError:
    print("חסרה הספרייה yfinance. התקן עם:  py -m pip install yfinance")
    sys.exit(1)

import csv

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("tickers", [])
    cfg.setdefault("dividend_yield_alert_pct", 5.0)
    cfg.setdefault("csv_path", "reit_history.csv")
    return cfg


def safe_get(d, key, default=None):
    """שליפה בטוחה ממילון שעלול להחזיר None או ערך חסר."""
    val = d.get(key, default)
    return default if val is None else val


def approx_ffo_per_share(tk):
    """
    FFO מקורב = רווח נקי + פחת והפחתות, מחולק במספר המניות.
    נשלף מדוח תזרים המזומנים / דוח רווח-הפסד השנתי האחרון.
    מחזיר None אם הנתונים חסרים.
    """
    try:
        cf = tk.cashflow  # DataFrame: שורות = סעיפים, עמודות = שנים
        if cf is None or cf.empty:
            return None
        latest = cf.columns[0]

        def row(name):
            return float(cf.loc[name, latest]) if name in cf.index else None

        net_income = row("Net Income") or row("Net Income From Continuing Operations")
        dep = (
            row("Depreciation And Amortization")
            or row("Depreciation Amortization Depletion")
            or row("Depreciation")
        )
        if net_income is None or dep is None:
            return None

        shares = safe_get(tk.info, "sharesOutstanding")
        if not shares:
            return None
        ffo = net_income + dep
        return ffo / shares
    except Exception:
        return None


def scan_ticker(symbol):
    tk = yf.Ticker(symbol)
    info = tk.info or {}

    price = safe_get(info, "currentPrice") or safe_get(info, "regularMarketPrice")
    div_yield_raw = safe_get(info, "dividendYield")  # לרוב באחוזים (למשל 5.4), לעיתים שבר
    market_cap = safe_get(info, "marketCap")

    # נירמול תשואת דיבידנד לאחוזים
    div_yield_pct = None
    if div_yield_raw is not None:
        div_yield_pct = div_yield_raw * 100 if div_yield_raw < 1 else div_yield_raw

    ffo_ps = approx_ffo_per_share(tk)
    p_ffo = (price / ffo_ps) if (price and ffo_ps and ffo_ps > 0) else None

    return {
        "symbol": symbol,
        "name": safe_get(info, "shortName", symbol),
        "price": round(price, 2) if price else None,
        "div_yield_pct": round(div_yield_pct, 2) if div_yield_pct else None,
        "ffo_per_share": round(ffo_ps, 2) if ffo_ps else None,
        "p_ffo": round(p_ffo, 1) if p_ffo else None,
        "market_cap_b": round(market_cap / 1e9, 2) if market_cap else None,
    }


def append_csv(path, rows, timestamp):
    full = os.path.join(HERE, path)
    is_new = not os.path.exists(full)
    fields = ["timestamp", "symbol", "name", "price",
              "div_yield_pct", "ffo_per_share", "p_ffo", "market_cap_b"]
    with open(full, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if is_new:
            w.writeheader()
        for r in rows:
            w.writerow({"timestamp": timestamp, **r})
    return full


def main():
    cfg = load_config()
    threshold = float(cfg["dividend_yield_alert_pct"])
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    print(f"\n  סורק REIT  |  {timestamp}  |  סף התראת תשואה: {threshold}%\n")
    header = f"{'טיקר':<8}{'מחיר':>10}{'תשואת div%':>13}{'FFO/share':>12}{'P/FFO':>9}{'שווי(B$)':>12}"
    print(header)
    print("-" * len(header.encode("ascii", "ignore")) if False else "-" * 70)

    rows, alerts = [], []
    for sym in cfg["tickers"]:
        try:
            r = scan_ticker(sym)
        except Exception as e:
            print(f"{sym:<8}  שגיאה בשליפה: {e}")
            continue
        rows.append(r)
        print(f"{r['symbol']:<8}"
              f"{('$'+str(r['price'])) if r['price'] else '-':>10}"
              f"{(str(r['div_yield_pct'])+'%') if r['div_yield_pct'] else '-':>13}"
              f"{r['ffo_per_share'] if r['ffo_per_share'] else '-':>12}"
              f"{r['p_ffo'] if r['p_ffo'] else '-':>9}"
              f"{r['market_cap_b'] if r['market_cap_b'] else '-':>12}")
        if r["div_yield_pct"] and r["div_yield_pct"] >= threshold:
            alerts.append(r)

    if rows:
        path = append_csv(cfg["csv_path"], rows, timestamp)
        print(f"\n  נשמרו {len(rows)} שורות אל: {os.path.basename(path)}")

    if alerts:
        print(f"\n  🔔 התראות — תשואת דיבידנד ≥ {threshold}%:")
        for a in alerts:
            print(f"     {a['symbol']:<6} {a['div_yield_pct']}%   (P/FFO: {a['p_ffo'] if a['p_ffo'] else '?'})")
    else:
        print(f"\n  אין קרן עם תשואת דיבידנד מעל {threshold}% כרגע.")
    print()


if __name__ == "__main__":
    main()
