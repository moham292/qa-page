"""تنزيل الأسعار اليومية الكاملة من Yahoo إلى crypto/data/<الرمز>.csv وتوثيق أول تاريخ لكل عملة.
  python crypto/fetch_crypto.py   ← crypto/data/*.csv + crypto/data/coverage.md
"""
from __future__ import annotations

import pandas as pd

from common import HERE, LISTS, download

if __name__ == "__main__":
    out = HERE / "data"
    out.mkdir(exist_ok=True)
    rows = ["# تغطية البيانات (Yahoo، شمعة UTC، بلا شمعة اليوم الجاري)", "",
            f"نُزّلت في {pd.Timestamp.now(tz='UTC'):%Y-%m-%d %H:%M} UTC.", "",
            "| الرمز | أول تاريخ | آخر تاريخ | عدد الأيام |", "|---|---|---|---|"]
    for sym in sorted({s for v in LISTS.values() for s in v}):
        df = download(sym)
        if df is None:
            raise SystemExit(f"فشل تنزيل {sym}")
        df.to_csv(out / f"{sym}.csv")
        rows.append(f"| {sym} | {df.index[0].date()} | {df.index[-1].date()} | {len(df)} |")
        print(rows[-1])
    (out / "coverage.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
