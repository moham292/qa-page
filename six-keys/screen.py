"""الفحص اليومي: يُشغّل بعد إغلاق السوق، ويطبع الأسهم مرتبة حسب عدد المفاتيح المتحققة.

  python screen.py               # على آخر يوم في البيانات
  python screen.py --date 2024-08-06
"""
from __future__ import annotations

import argparse

import pandas as pd

import data
from keys import Params, evaluate, macd_negative_cross


def screen(on: pd.Timestamp | None, p: Params) -> pd.DataFrame:
    tasi, _, lag = data.load_benchmark()
    syms = data.symbols()
    # آخر يوم تداول (حتى on إن حُدد) عبر كل الأسهم
    day = max(d for s in syms for d in data.load_prices(s).loc[:on].index[-1:])
    tasi = tasi.loc[:day - pd.Timedelta(days=lag)] if lag else tasi.loc[:day]
    fund, sharia = data.load_fundamentals(), data.load_sharia()
    rows = []
    for sym in syms:
        df = data.load_prices(sym).loc[:day]
        if len(df) < p.sma_len + 10 or df.index[-1] != day:
            continue
        pure = data.is_pure(sharia, sym, day)
        if pure is False:
            continue
        ni = True if fund is None else bool(data.net_income_positive(fund, sym, day))  # بدون ملف: معطّل
        e = evaluate(df, tasi, ni, p)
        rows.append({
            "الرمز": sym, "المفاتيح": f"{e.score}/6",
            "اتجاه السهم": e.trend, "صافي ربح موجب": e.profitable, "اتجاه تاسي": e.market_trend,
            "دعم/مقاومة": e.sr, "فوق SMA55": e.above_sma55, "MACD إيجابي": e.macd_pos,
            "تقاطع سلبي اليوم (خروج)": macd_negative_cross(df, p),
            "_score": e.score,
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values("_score", ascending=False).drop(columns="_score")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    a = ap.parse_args()
    res = screen(pd.Timestamp(a.date) if a.date else None, Params())
    pd.set_option("display.width", 200)
    print(res.to_string(index=False))
    res.to_csv("screen_result.csv", index=False, encoding="utf-8-sig")
