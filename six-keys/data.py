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

import numpy as np
import pandas as pd

DATA = Path(__file__).parent / "data"


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """تنظيف بيانات Yahoo للأسهم السعودية:
    - أيام حجمها صفر بسعر مكرر (عطل/إيقاف يملؤها Yahoo) ← تُحذف.
    - قفزة معزولة ليوم واحد (حركة > 25% تنعكس في اليوم التالي بأكثر من 20%) ← خطأ بيانات، تُحذف.
      حد التذبذب اليومي في تداول ±10%، فلا تُحذف حركة حقيقية بهذه القاعدة إلا نادراً."""
    df = df[(df["Volume"] > 0) & (df[["Open", "High", "Low", "Close"]] > 0).all(axis=1)]
    r = df["Close"].pct_change()
    spike = (r.abs() > 0.25) & (r.shift(-1).abs() > 0.20) & (np.sign(r) != np.sign(r.shift(-1)))
    return df[~spike]


def load_prices(symbol: str, root: Path = DATA) -> pd.DataFrame:
    df = pd.read_csv(root / "prices" / f"{symbol}.csv", parse_dates=["Date"]).set_index("Date").sort_index()
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    return df if symbol == "TASI" else clean(df)


def load_benchmark(root: Path = DATA) -> tuple[pd.DataFrame, str, int]:
    """مؤشر السوق للمفتاح 3 وللمقارنة: تاسي إن توفر تاريخه، وإلا صندوق KSA (iShares MSCI Saudi Arabia) كبديل.
    يعيد (البيانات، الاسم، التأخير بالأيام). KSA يُغلق في نيويورك بعد إغلاق تداول بساعات ← يُستخدم بتأخير يوم."""
    f = root / "prices" / "TASI.csv"
    if f.exists():
        t = load_prices("TASI", root)
        if len(t) >= 250:
            return t, "تاسي", 0
    df = pd.read_csv(root / "benchmark" / "KSA.csv", parse_dates=["Date"]).set_index("Date").sort_index()
    return df[["Open", "High", "Low", "Close", "Volume"]].dropna(), "KSA (بديل تاسي)", 1


def symbols(root: Path = DATA, include_nomu: bool = False) -> list[str]:
    """أسهم السوق الرئيسية (مكونات تاسي). نمو (الرموز 9xxx) مستبعد افتراضياً: ليس في تاسي، وسيولته ضعيفة."""
    return sorted(p.stem for p in (root / "prices").glob("*.csv")
                  if p.stem != "TASI" and (include_nomu or not p.stem.startswith("9")))


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




def load_sharia(root: Path = DATA, strict: bool = False) -> pd.DataFrame | None:
    """strict: السريان يبدأ من تاريخ نشر القائمة (list_published) حتى لو سُجّل valid_from أقدم
    (القائمة الأولى منشورة 2016-06-05 ومسجلة من 2000-01-01)."""
    f = root / "sharia.csv"
    if not f.exists():
        return None
    df = pd.read_csv(f, parse_dates=["valid_from", "valid_to"], dtype={"symbol": str})
    if strict and "list_published" in df:
        df["valid_from"] = df[["valid_from"]].join(pd.to_datetime(df["list_published"])).max(axis=1)
    return df


def pure_mask(sharia: pd.DataFrame, symbol: str, dates: pd.DatetimeIndex) -> np.ndarray:
    """لكل تاريخ: هل السهم "نقي" حسب القائمة السارية؟ (غير مدرج في القائمة = غير نقي)."""
    out = np.zeros(len(dates), dtype=bool)
    for r in sharia[sharia.symbol == symbol].itertuples():
        end = r.valid_to if pd.notna(r.valid_to) else pd.Timestamp.max
        out[(dates >= r.valid_from) & (dates <= end)] = r.classification == "نقية"
    return out


def is_pure(sharia: pd.DataFrame | None, symbol: str, on: pd.Timestamp) -> bool | None:
    """None = لا توجد قائمة بعد (الفلتر معطّل)."""
    if sharia is None:
        return None
    r = sharia[(sharia.symbol == symbol) & (sharia.valid_from <= on)
               & (sharia.valid_to.isna() | (sharia.valid_to >= on))]
    return (not r.empty) and r.iloc[-1].classification == "نقية"
