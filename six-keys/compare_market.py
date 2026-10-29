"""مقارنة اتجاه السوق (المفتاح 3) بين صندوق KSA (بتأخير يوم) والمؤشر التقريبي متساوي الأوزان."""
from __future__ import annotations

import pandas as pd

import data
from backtest import trend_series
from keys import Params

if __name__ == "__main__":
    p = Params()
    ksa, _, lag = data.load_benchmark()
    ew = data.ew_index()
    t_ksa = trend_series(ksa, p)
    t_ksa.index = t_ksa.index + pd.Timedelta(days=lag)
    t_ew = trend_series(ew, p)
    days = ew.index
    k = t_ksa.reindex(t_ksa.index.union(days)).ffill().reindex(days)
    first_valid = t_ksa[t_ksa != "غير كافٍ"].index.min()
    print(f"KSA: أول يوم تداول {ksa.index[0].date()}، أول اتجاه محسوب {first_valid.date()}"
          f" (بعد {int((ksa.index < first_valid).sum())} يوم تداول)")
    df = pd.DataFrame({"ksa": k, "ew": t_ew}).loc["2016-01-01":]
    df["ksa_up"], df["ew_up"] = df.ksa == "صاعد", df.ew == "صاعد"
    agree = (df.ksa_up == df.ew_up)
    print(f"تطابق المفتاح 3 (صاعد/غير صاعد) منذ 2016: {agree.mean():.0%}")
    print("نسبة الأيام الصاعدة: KSA", f"{df.ksa_up.mean():.0%}", "| متساوي الأوزان", f"{df.ew_up.mean():.0%}")
    by = pd.DataFrame({"تطابق": agree, "KSA صاعد": df.ksa_up, "EW صاعد": df.ew_up}).groupby(df.index.year).mean()
    print((by * 100).round(0).astype(int).to_string())
    print("\nحالات الاتجاه أول 2016 (KSA مقابل EW):")
    print(df.loc[:"2016-03-31", ["ksa", "ew"]].value_counts().to_string())
