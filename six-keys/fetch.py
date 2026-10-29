"""تنزيل الأسعار اليومية من Yahoo Finance إلى data/prices/.

يحتاج اتصالاً بـ query1/query2.finance.yahoo.com.
  python fetch.py 1120 4030 2222 ...        # رموز تداول
  python fetch.py --file symbols.txt         # رمز في كل سطر
  python fetch.py --universe                 # كل الرموز في data/universe.csv (من crawl_universe.py)

إيقاع هادئ (~20 طلباً في الدقيقة) وانتظار عند حد الطلبات؛ يتخطى الرمز إن كان ملفه يبدأ من --start أصلاً.
"""
from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

import pandas as pd
import yfinance as yf
from yfinance.exceptions import YFRateLimitError

logging.getLogger("yfinance").setLevel(logging.CRITICAL)
yf.config.debug.hide_exceptions = False

OUT = Path(__file__).parent / "data" / "prices"


def _covered(f: Path, start: str) -> bool:
    if not f.exists():
        return False
    first = pd.read_csv(f, usecols=["Date"], nrows=1)["Date"].iloc[0]
    return pd.Timestamp(first) <= pd.Timestamp(start) + pd.Timedelta(days=45)


def fetch(symbol: str, start: str) -> None:
    ticker = "^TASI.SR" if symbol == "TASI" else f"{symbol}.SR"
    for _ in range(12):
        try:
            df = yf.download(ticker, start=start, progress=False, auto_adjust=True, multi_level_index=False)
            break
        except Exception as e:
            if not (isinstance(e, YFRateLimitError) or "Rate" in str(e)):
                df = pd.DataFrame()
                break
            print(f"حد الطلبات عند {symbol} — انتظار", flush=True)
            time.sleep(600)
    else:
        raise SystemExit(f"توقف عند {symbol}: حد الطلبات مستمر")
    if df.empty:
        print(f"لا بيانات: {symbol}", flush=True)
        return
    df.index.name = "Date"
    df[["Open", "High", "Low", "Close", "Volume"]].to_csv(OUT / f"{symbol}.csv")
    print(f"{symbol}: {len(df)} يوم من {df.index[0].date()}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("symbols", nargs="*")
    ap.add_argument("--file")
    ap.add_argument("--universe", action="store_true")
    ap.add_argument("--start", default="2014-01-01")
    a = ap.parse_args()
    syms = list(a.symbols)
    if a.file:
        syms += [s.strip() for s in Path(a.file).read_text().split() if s.strip()]
    if a.universe:
        syms += pd.read_csv(OUT.parent / "universe.csv", dtype={"symbol": str})["symbol"].tolist()
    OUT.mkdir(parents=True, exist_ok=True)
    for s in dict.fromkeys(syms):
        if _covered(OUT / f"{s}.csv", a.start):
            continue
        fetch(s, a.start)
        time.sleep(1.8)
