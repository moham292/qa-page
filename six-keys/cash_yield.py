"""أثر عائد الكاش (صناديق مرابحة) على المنهج: الكاش في الاختبار عائده صفر، والمنهج في الكاش ~75% من الوقت.

نسبة الكاش اليومية تُعاد بناؤها من سجل الصفقات وأسعار الإغلاق. عائد اليوم المعدّل =
عائد المحفظة بعد العمولات + (نسبة الكاش أمس) × عائد المرابحة للفترة. المعدل ثابت طوال الفترة (تبسيط).
  python cash_yield.py   ← results/cash_yield.md
"""
from __future__ import annotations

import pandas as pd

import data
from final_checks import COST, R, md_table, net_curve, rebalanced, stats

RATES = (0.0, 0.02, 0.04)
TAGS = {"B125 / KSA / النقية": "ksa_B125_pure", "B125 / KSA / النقية + 5/6": "ksa_B125_pure_five",
        "B125 / EW / النقية": "ew_B125_pure", "B125 / KSA / كل السوق": "ksa_B125_all",
        "B125 / EW / كل السوق": "ew_B125_all"}


def cash_fraction(tag: str, closes: pd.DataFrame) -> pd.Series:
    eq = pd.read_csv(R / f"equity_{tag}.csv", index_col=0, parse_dates=True)["equity"]
    t = pd.read_csv(R / f"trades_{tag}.csv", parse_dates=["entry_date", "exit_date"], dtype={"symbol": str})
    invested = pd.Series(0.0, index=eq.index)
    for x in t.itertuples():
        shares = x.weight * eq.asof(x.entry_date) / x.entry   # المبلغ = الوزن × قيمة المحفظة يوم الدخول
        end = x.exit_date if pd.notna(x.exit_date) else eq.index[-1] + pd.Timedelta(days=1)
        days = eq.index[(eq.index >= x.entry_date) & (eq.index < end)]
        invested.loc[days] += shares * closes[x.symbol].reindex(days).ffill().bfill().to_numpy()
    return (1 - invested / eq).clip(0, 1)


def with_cash(curve: pd.Series, cash: pd.Series, rate: float) -> pd.Series:
    r = curve.pct_change().fillna(0)
    dt = curve.index.to_series().diff().dt.days.fillna(0)
    i = (1 + rate) ** (dt / 365.25) - 1
    return (1 + r + cash.shift(1).fillna(1) * i).cumprod() * curve.iloc[0]


if __name__ == "__main__":
    closes = pd.DataFrame({s: data.load_prices(s)["Close"] for s in data.symbols()})
    ksa = data.load_benchmark()[0]["Close"]
    sharia = data.load_sharia()
    pure = pd.DataFrame({s: pd.Series(data.pure_mask(sharia, s, closes.index), index=closes.index) for s in closes})
    hist_days = closes.notna().cumsum()

    def pure_on(d):  # نفس تعريف final_checks.py
        prev = closes.index[closes.index < d]
        if not len(prev):
            return []
        ok = pure.loc[prev[-1]] & closes.loc[prev[-5:]].notna().any() & (hist_days.loc[prev[-1]] >= 60)
        return ok.index[ok].tolist()
    out = ["# أثر عائد الكاش (مرابحة)", "",
           f"كل أرقام المنهج بعد العمولات ({COST:.2%} لكل جهة). المعدل ثابت طوال الفترة — تبسيط؛ العوائد الفعلية تغيّرت عبر السنوات.",
           "KSA وسلة النقية مستثمران بالكامل ← عائد الكاش لا يغيّرهما.", ""]
    for pn, per, start in (("2016–اليوم", "full", "2016-01-01"), ("2018–اليوم", "2018_now", "2018-01-01")):
        ks = stats(ksa.loc[start:])
        bk = stats(rebalanced(closes.loc[start:], pure_on, "M", COST)[0])
        cell = lambda x: f"{x['سنوياً']:+.2%} / {x['أسوأ تراجع']:.1%} / {x['سنوي÷تراجع']:.2f}"
        kr = ksa.loc[start:].pct_change().fillna(0)
        dt = ksa.loc[start:].index.to_series().diff().dt.days.fillna(0)

        def blend(rate, w=0.26):  # نفس تعرّض المنهج تقريباً: 26% KSA و74% مرابحة، إعادة توازن شهرية
            i = (1 + rate) ** (dt / 365.25) - 1
            level, vals = 1.0, []
            for _, g in pd.DataFrame({"k": kr, "i": i}).groupby(kr.index.to_period("M")):
                path = w * (1 + g.k).cumprod() + (1 - w) * (1 + g.i).cumprod()
                vals += list(level * path)
                level *= float(path.iloc[-1])
            return pd.Series(vals, index=kr.index)

        rows = [["KSA", *[cell(ks)] * len(RATES), "0%"],
                ["26% KSA + 74% مرابحة (نفس تعرّض المنهج)", *[cell(stats(blend(r))) for r in RATES], "74%"],
                ["سلة النقية الشهرية (بعد العمولات)", *[cell(bk)] * len(RATES), "0%"]]
        for label, stem in TAGS.items():
            tag = f"{stem.replace('_five', '')}_{per}" + ("_five" if stem.endswith("_five") else "")
            if not (R / f"equity_{tag}.csv").exists():
                continue
            cash = cash_fraction(tag, closes)
            net = net_curve(tag, COST)
            cells = []
            for rate in RATES:
                s = stats(with_cash(net, cash, rate))
                cells.append(f"{s['سنوياً']:+.2%} / {s['أسوأ تراجع']:.1%} / {s['سنوي÷تراجع']:.2f}")
            rows.append([label, *cells, f"{cash.mean():.0%}"])
        out += [f"## {pn}", "", "كل خلية: العائد السنوي / أسوأ تراجع / سنوي÷تراجع", "",
                md_table(["المحفظة", "كاش 0%", "كاش 2%", "كاش 4%", "متوسط الكاش"], rows), ""]
    (R / "cash_yield.md").write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))
