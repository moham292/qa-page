"""تحميل البيانات.

الصيغة المحلية (مجلد data/):
  data/prices/<الرمز>.csv     أعمدة: Date,Open,High,Low,Close,Volume   (تاسي باسم TASI.csv)
  data/fundamentals.csv        أعمدة: symbol,fiscal_year,net_income,available_from
                               available_from = تاريخ إعلان القوائم (لتجنب استخدام معلومة قبل إعلانها)
  data/sharia.csv              أعمدة: symbol,classification,valid_from,valid_to
                               classification: نقية / مختلطة / محرمة — القائمة من المرجع الذي تعتمده
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA = Path(__file__).parent / "data"


def load_prices(symbol: str, root: Path = DATA) -> pd.DataFrame:
    df = pd.read_csv(root / "prices" / f"{symbol}.csv", parse_dates=["Date"]).set_index("Date").sort_index()
    return df[["Open", "High", "Low", "Close", "Volume"]].dropna()


def symbols(root: Path = DATA) -> list[str]:
    return sorted(p.stem for p in (root / "prices").glob("*.csv") if p.stem != "TASI")


def load_fundamentals(root: Path = DATA) -> pd.DataFrame | None:
    f = root / "fundamentals.csv"
    if not f.exists():
        return None
    return pd.read_csv(f, parse_dates=["available_from"], dtype={"symbol": str})


def net_income_positive(fund: pd.DataFrame | None, symbol: str, on: pd.Timestamp) -> bool | None:
    """آخر سنة مالية أُعلنت قبل التاريخ on: هل صافي الربح موجب؟"""
    if fund is None:
        return None
    rows = fund[(fund.symbol == symbol) & (fund.available_from <= on)]
    if rows.empty:
        return None
    return bool(rows.sort_values("fiscal_year").iloc[-1].net_income > 0)


def load_sharia(root: Path = DATA) -> pd.DataFrame | None:
    f = root / "sharia.csv"
    if not f.exists():
        return None
    return pd.read_csv(f, parse_dates=["valid_from", "valid_to"], dtype={"symbol": str})


def is_pure(sharia: pd.DataFrame | None, symbol: str, on: pd.Timestamp) -> bool | None:
    """None = لا توجد قائمة بعد (الفلتر معطّل)."""
    if sharia is None:
        return None
    r = sharia[(sharia.symbol == symbol) & (sharia.valid_from <= on)
               & (sharia.valid_to.isna() | (sharia.valid_to >= on))]
    return (not r.empty) and r.iloc[-1].classification == "نقية"
