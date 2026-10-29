"""فحوص تفسير تفوق السلة المتساوية: أثر تصحيح الإجراءات الرأسمالية، وأثر تكرار إعادة التوازن."""
from __future__ import annotations

import numpy as np
import pandas as pd

import data


def raw_clean(s: str) -> pd.DataFrame:
    """نفس التنظيف بدون تعديل الإجراءات الرأسمالية."""
    df = pd.read_csv(f"data/prices/{s}.csv", parse_dates=["Date"]).set_index("Date").sort_index()
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    df = df[(df.Volume > 0) & (df[["Open", "High", "Low", "Close"]] > 0).all(axis=1)]
    r = df.Close.pct_change()
    spike = (r.abs() > 0.25) & (r.shift(-1).abs() > 0.20) & (np.sign(r) != np.sign(r.shift(-1)))
    return df[~spike]


def basket(cl: pd.DataFrame, freq: str | None) -> float:
    """عائد سلة متساوية الأوزان. freq=None: إعادة توازن يومية؛ "M": شهرية؛ "Y": سنوية.
    بين مواعيد إعادة التوازن تنجرف الأوزان مع الأسعار (شراء واحتفاظ)."""
    r = cl.pct_change(fill_method=None).clip(-0.5, 0.5).iloc[1:]
    if freq is None:
        return float((1 + r.mean(axis=1).fillna(0)).prod() - 1)
    total = 1.0
    for _, g in r.groupby(r.index.to_period(freq)):
        alive = g.columns[g.notna().any()]
        growth = (1 + g[alive].fillna(0)).cumprod().iloc[-1]   # كل سهم من بداية الفترة لنهايتها
        total *= growth.mean()
    return total - 1


if __name__ == "__main__":
    syms = data.symbols()
    before = pd.DataFrame({s: raw_clean(s).Close for s in syms})
    after = pd.DataFrame({s: data.load_prices(s).Close for s in syms})
    rows = []
    for name, (a, b) in {"2016–2017": ("2016-01-01", "2017-12-31"), "2018–اليوم": ("2018-01-01", None),
                         "2016–اليوم": ("2016-01-01", None)}.items():
        res = {}
        for lab, cl in (("قبل التصحيح", before), ("بعد التصحيح", after)):
            c = cl.loc[a:b]
            for fl, f in (("يومي", None), ("شهري", "M"), ("سنوي", "Y")):
                res[f"{fl} — {lab}"] = basket(c, f)
        rows.append(pd.Series(res, name=name))
    t = (pd.DataFrame(rows) * 100).round(1)
    print(t.T.to_string())
    t.T.to_csv("results/ew_basket_checks.csv")
