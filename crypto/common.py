"""ثوابت ودوال مشتركة لتجربة العملات. القواعد في CRYPTO_RULES.md ولا تُعدَّل.

يستورد من six-keys/ فقط ولا يعدّل فيه شيئاً.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
SIX = HERE.parent / "six-keys"
if str(SIX) not in sys.path:
    sys.path.insert(0, str(SIX))

from keys import Params  # noqa: E402

LISTS = {
    "core": ["BTC-USD", "ETH-USD", "XRP-USD"],
    "ext": ["LTC-USD", "BCH-USD", "SOL-USD", "ADA-USD", "AVAX-USD", "DOT-USD"],
}
LIST_NAMES = {"core": "الأساسية (المنصوصة)", "ext": "الملحق (القياس)"}
MARKET = "BTC-USD"
COST = 0.001                     # 0.1% لكل جهة
PARAMS = Params(pivot_n=8, support_tol=0.05, sr_lookback=125)   # B125 دون إعادة ضبط
WARMUP = 60                      # 60 يوم بيانات على الأقل قبل يوم الإشارة
START = "2018-01-01"
COLS = ["Open", "High", "Low", "Close", "Volume"]


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """نفس data.clean في six-keys بلا تصحيح الإجراءات الرأسمالية (لا تنطبق على العملات، والقواعد تمنعه):
    - أيام حجمها صفر أو بسعر غير موجب ← تُحذف.
    - قفزة معزولة (> 25% تنعكس في اليوم التالي بأكثر من 20%) ← خطأ بيانات، تُحذف."""
    df = df[(df["Volume"] > 0) & (df[["Open", "High", "Low", "Close"]] > 0).all(axis=1)]
    r = df["Close"].pct_change()
    spike = (r.abs() > 0.25) & (r.shift(-1).abs() > 0.20) & (np.sign(r) != np.sign(r.shift(-1)))
    return df[~spike]


def spikes_removed(df: pd.DataFrame) -> list[pd.Timestamp]:
    d = df[(df["Volume"] > 0) & (df[["Open", "High", "Low", "Close"]] > 0).all(axis=1)]
    return sorted(set(d.index) - set(clean(df).index))


def download(ticker: str, start: str | None = None) -> pd.DataFrame | None:
    """أسعار Yahoo اليومية (شمعة UTC). تُحذف شمعة اليوم الجاري (غير مكتملة). None = فشل بعد إعادة المحاولة."""
    import yfinance as yf
    for attempt in range(4):
        try:
            kw = {"start": start} if start else {"period": "max"}
            df = yf.download(ticker, progress=False, auto_adjust=False, multi_level_index=False, **kw)
            if df is None or df.empty:
                raise ValueError("no data")
            df.index = pd.to_datetime(df.index).tz_localize(None)
            df.index.name = "Date"
            today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
            df = df[df.index < today]
            return df[COLS].dropna()
        except Exception:
            time.sleep(5 * (attempt + 1))
    return None


def load_csv(f: Path) -> pd.DataFrame:
    return pd.read_csv(f, parse_dates=["Date"]).set_index("Date").sort_index()[COLS].dropna()
