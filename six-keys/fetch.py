"""تنزيل الأسعار اليومية من Yahoo Finance إلى data/prices/.

يحتاج اتصالاً بـ query1/query2.finance.yahoo.com.
  python fetch.py 1120 4030 2222 ...        # رموز تداول
  python fetch.py --file symbols.txt         # رمز في كل سطر
"""
from __future__ import annotations

import argparse
from pathlib import Path

import yfinance as yf

OUT = Path(__file__).parent / "data" / "prices"


def fetch(symbol: str, start: str) -> None:
    ticker = "^TASI.SR" if symbol == "TASI" else f"{symbol}.SR"
    df = yf.download(ticker, start=start, progress=False, auto_adjust=True, multi_level_index=False)
    if df.empty:
        print(f"لا بيانات: {symbol}")
        return
    df.index.name = "Date"
    df[["Open", "High", "Low", "Close", "Volume"]].to_csv(OUT / f"{symbol}.csv")
    print(f"{symbol}: {len(df)} يوم")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("symbols", nargs="*")
    ap.add_argument("--file")
    ap.add_argument("--start", default="2018-01-01")
    a = ap.parse_args()
    syms = list(a.symbols)
    if a.file:
        syms += [s.strip() for s in Path(a.file).read_text().split() if s.strip()]
    OUT.mkdir(parents=True, exist_ok=True)
    for s in ["TASI", *syms]:
        fetch(s, a.start)
