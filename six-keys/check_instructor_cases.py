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


if __name__ == "__main__":
    for n, tol in itertools.product([2, 3, 5, 8], [0.02, 0.03, 0.05]):
        res = run(Params(pivot_n=n, support_tol=tol))
        scored = [r for r in res if r[4] != "لا بيانات"]
        hit = sum(r[3] == r[4] for r in scored)
        print(f"pivot_n={n} support_tol={tol:.0%}: {hit}/{len(scored)} تطابق")
    print()
    for r in run(Params()):
        mark = "✓" if r[3] == r[4] else "✗"
        print(mark, *r)
