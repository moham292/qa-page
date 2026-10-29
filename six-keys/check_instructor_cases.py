"""مقارنة الأداة بإجابات المدربين في الواجبات (حالات اختبار حقيقية من المحاضرات).

  python check_instructor_cases.py
يجرّب عدة قيم لـ pivot_n و support_tol ويطبع نسبة التطابق لكل تركيبة.
"""
from __future__ import annotations

import itertools

import pandas as pd

import data
from keys import Params, support_status, trend

# (رمز تداول، التاريخ، نوع السؤال، إجابة المدرب، المصدر)
# الرموز من ذاكرة عامة — راجعها قبل الاعتماد عليها.
CASES = [
    ("TASI", "2024-08-06", "sr", "دعم", "محاضرة (5)"),
    ("4200", "2024-08-06", "sr", "دعم", "(5) الدريس"),
    ("1810", "2024-08-06", "sr", "لا شيء", "(5) سيرا — كسر الدعم وهابط"),
    ("4050", "2024-08-06", "sr", "دعم", "(5) ساسكو"),
    ("1140", "2024-08-06", "sr", "دعم", "(5) البلاد — مقاومة مخترقة"),
    ("4300", "2024-08-06", "sr", "مقاومة", "(5) دار الأركان"),
    ("TASI", "2024-08-08", "sr", "مقاومة", "(7) تاسي إغلاق الخميس"),
    ("4030", "2024-08-05", "trend", "صاعد", "(6) البحري"),
    ("1120", "2024-08-05", "trend", "صاعد", "(6) الراجحي"),
    ("2382", "2024-08-05", "trend", "هابط", "(6) أديس"),
    ("1211", "2024-08-05", "trend", "هابط", "(6) معادن"),
    ("4162", "2024-08-05", "trend", "هابط", "(6) المنجم"),
    ("1140", "2024-08-05", "trend", "صاعد", "(6) البلاد"),
]


def run(p: Params) -> list[tuple]:
    out = []
    for sym, date, kind, expected, src in CASES:
        try:
            df = data.load_prices(sym).loc[:date]
        except FileNotFoundError:
            df = None
        if df is None or len(df) < 60:
            out.append((sym, date, kind, expected, "لا بيانات", src))
            continue
        got = trend(df, p) if kind == "trend" else support_status(df, p)[0]
        out.append((sym, date, kind, expected, got, src))
    return out


GRID = dict(pivot_n=[2, 3, 5, 8, 13], support_tol=[0.02, 0.03, 0.05], equal_tol=[0.005, 0.01, 0.02],
            provisional=[False, True], sr_tiebreak=["ambiguous", "nearest"])


def grid() -> pd.DataFrame:
    rows = []
    for vals in itertools.product(*GRID.values()):
        kw = dict(zip(GRID, vals))
        res = [r for r in run(Params(**kw)) if r[4] != "لا بيانات"]
        tr = [r for r in res if r[2] == "trend"]
        sr = [r for r in res if r[2] == "sr"]
        rows.append({**kw, "trend": sum(r[3] == r[4] for r in tr), "trend_n": len(tr),
                     "sr": sum(r[3] == r[4] for r in sr), "sr_n": len(sr),
                     "total": sum(r[3] == r[4] for r in res), "n": len(res)})
    return pd.DataFrame(rows).sort_values(["total", "trend"], ascending=False)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--pivot-n", type=int)
    ap.add_argument("--support-tol", type=float)
    ap.add_argument("--equal-tol", type=float)
    ap.add_argument("--provisional", action="store_true")
    ap.add_argument("--sr-tiebreak")
    a = ap.parse_args()
    g = grid()
    g.to_csv("instructor_grid.csv", index=False)
    print(g.head(25).to_string(index=False))
    print(f"\nتركيبات بأعلى مجموع ({g.total.max()}/{g.n.iloc[0]}): {(g.total == g.total.max()).sum()} من {len(g)}")
    best = g.iloc[0].to_dict()
    kw = {k: best[k] for k in GRID}
    for k in GRID:
        v = getattr(a, k)
        if v not in (None, False):
            kw[k] = v
    kw["pivot_n"] = int(kw["pivot_n"])
    print("\nالتفاصيل لـ", kw)
    for r in run(Params(**kw)):
        mark = "✓" if r[3] == r[4] else ("–" if r[4] == "لا بيانات" else "✗")
        print(mark, *r)
