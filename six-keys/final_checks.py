"""فحوص أخيرة: مخاطرة سلة النقية، محفظة عملية بسيطة (أكثر 20 سهماً نقياً سيولة)، وجدول العائد/التراجع لكل الإعدادات.

العمولة: COST لكل جهة (شراء أو بيع) على قيمة التداول الفعلية — تقدير لم يُتحقق منه.
  python final_checks.py        ← results/final_checks.md
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

import data

COST = 0.0015
R = Path(__file__).parent / "results"
PERIODS = {"2016–اليوم": "2016-01-01", "2018–اليوم": "2018-01-01"}


def cagr(s: pd.Series) -> float:
    y = (s.index[-1] - s.index[0]).days / 365.25
    return float((s.iloc[-1] / s.iloc[0]) ** (1 / y) - 1)


def max_dd(s: pd.Series) -> float:
    return float((s / s.cummax() - 1).min())


def stats(s: pd.Series) -> dict:
    c, d = cagr(s), max_dd(s)
    return {"العائد": s.iloc[-1] / s.iloc[0] - 1, "سنوياً": c, "أسوأ تراجع": d, "سنوي÷تراجع": c / abs(d)}


def rebalanced(closes: pd.DataFrame, pick, freq: str, cost: float) -> tuple[pd.Series, float]:
    """محفظة بأوزان متساوية تُعاد كل فترة (freq). pick(date) ← قائمة الأسهم عند بداية الفترة (بيانات قبلها فقط).
    بين المواعيد تنجرف الأوزان. العمولة على قيمة التداول عند كل إعادة توازن. يعيد (المنحنى، متوسط الدوران السنوي)."""
    r = closes.pct_change(fill_method=None).clip(-0.5, 0.5).iloc[1:].fillna(0)  # سهم بلا تداول يُعامل ثابتاً
    level, held = 1.0, pd.Series(dtype=float)   # held = أوزان فعلية بعد الانجراف
    vals, idx, turnover = [], [], 0.0
    for _, g in r.groupby(r.index.to_period(freq)):
        names = [s for s in pick(g.index[0]) if s in g.columns]
        if not names:
            vals += [level] * len(g); idx += list(g.index); held = pd.Series(dtype=float); continue
        target = pd.Series(1 / len(names), index=names)
        tr = target.sub(held, fill_value=0).abs().sum()
        turnover += tr
        level *= 1 - cost * tr
        growth = (1 + g[names]).cumprod()
        path = growth.mul(target, axis=1).sum(axis=1)
        vals += list(level * path); idx += list(g.index)
        level *= float(path.iloc[-1])
        held = growth.iloc[-1] * target / path.iloc[-1]
    s = pd.Series(vals, index=idx)
    years = (s.index[-1] - s.index[0]).days / 365.25
    return s, turnover / years


def net_curve(tag: str, cost: float) -> pd.Series:
    """منحنى المنهج بعد العمولات: كل دخول يخصم w×cost من رأس المال، وكل خروج w×(1+ret)×cost (تقريب: بوزن الدخول)."""
    eq = pd.read_csv(R / f"equity_{tag}.csv", index_col=0, parse_dates=True)["equity"]
    t = pd.read_csv(R / f"trades_{tag}.csv", parse_dates=["entry_date", "exit_date"])
    hit = pd.Series(0.0, index=eq.index)
    for x in t.itertuples():
        hit[eq.index[eq.index.searchsorted(x.entry_date)]] += x.weight * cost
        if pd.notna(x.exit_date):
            hit[eq.index[min(eq.index.searchsorted(x.exit_date), len(eq) - 1)]] += x.weight * (1 + x.ret) * cost
    return eq * (1 - hit).cumprod()


def fmt(d: dict) -> list[str]:
    return [f"{d['العائد']:+.1%}", f"{d['سنوياً']:+.2%}", f"{d['أسوأ تراجع']:.1%}", f"{d['سنوي÷تراجع']:.2f}"]


def md_table(head: list[str], rows: list[list[str]]) -> str:
    return "\n".join(["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(r) + " |" for r in rows])


if __name__ == "__main__":
    syms = data.symbols()
    prices = {s: data.load_prices(s) for s in syms}
    closes = pd.DataFrame({s: df["Close"] for s, df in prices.items()})
    value = pd.DataFrame({s: (df["Close"] * df["Volume"]) for s, df in prices.items()}).reindex(closes.index)
    sharia = data.load_sharia()
    pure = pd.DataFrame({s: pd.Series(data.pure_mask(sharia, s, closes.index), index=closes.index) for s in syms})
    ksa = data.load_benchmark()[0]["Close"]

    hist_days = closes.notna().cumsum()

    def pure_on(d):
        """المؤهل عند d (بيانات قبله فقط): نقي حسب التصنيف الساري أمس، وله سعر خلال آخر 5 أيام تداول،
        و60 يوم تداول على الأقل (نفس فترة الإحماء التي لا يتداول فيها المنهج) ← سلة قابلة للمقارنة بالمنهج."""
        prev = closes.index[closes.index < d]
        if not len(prev):
            return []
        p = prev[-1]
        ok = pure.loc[p] & closes.loc[prev[-5:]].notna().any() & (hist_days.loc[p] >= 60)
        return ok.index[ok].tolist()

    def top20(d):  # أكثر 20 سهماً نقياً سيولة: متوسط قيمة التداول في 60 يوم تداول قبل d
        names = pure_on(d)
        hist = value.loc[value.index < d].tail(60)[names]
        liq = hist.mean().dropna()
        return liq[hist.notna().sum() >= 40].nlargest(20).index.tolist()

    out = ["# فحوص أخيرة", "", f"العمولة المفترضة: {COST:.2%} لكل جهة على قيمة التداول (تقدير غير مُتحقق منه). "
           "«سنوي÷تراجع» = العائد السنوي ÷ |أسوأ تراجع| (أعلى = عائد أكبر لكل وحدة تراجع).", ""]
    unified = {}
    for pn, start in PERIODS.items():
        c = closes.loc[start:]
        ks = ksa.loc[start:]
        bm, bm_to = rebalanced(c, pure_on, "M", 0.0)
        bmn, _ = rebalanced(c, pure_on, "M", COST)
        t20, t20_to = rebalanced(c, top20, "Y", COST)
        t20g, _ = rebalanced(c, top20, "Y", 0.0)
        b125 = net_curve(f"ksa_B125_pure_{'full' if start == '2016-01-01' else '2018_now'}", COST)
        rows = [["KSA (شراء واحتفاظ، رسومه داخل السعر)", *fmt(stats(ks)), "–"],
                ["سلة النقية الشهرية — قبل العمولات", *fmt(stats(bm)), f"{bm_to:.0%}"],
                ["سلة النقية الشهرية — بعد العمولات", *fmt(stats(bmn)), f"{bm_to:.0%}"],
                ["أكثر 20 نقياً سيولة، توازن سنوي — قبل العمولات", *fmt(stats(t20g)), f"{t20_to:.0%}"],
                ["أكثر 20 نقياً سيولة، توازن سنوي — بعد العمولات", *fmt(stats(t20)), f"{t20_to:.0%}"],
                ["المنهج B125 النقية (KSA للمفتاح 3) — بعد العمولات", *fmt(stats(b125)), "–"]]
        out += [f"## {pn}", "", md_table(["المحفظة", "العائد", "سنوياً", "أسوأ تراجع", "سنوي÷تراجع", "الدوران السنوي"], rows), ""]
        unified[pn] = {"KSA": stats(ks), "سلة النقية الشهرية (صافٍ)": stats(bmn), "أكثر 20 نقياً سيولة (صافٍ)": stats(t20)}

    # الجدول الموحد لكل إعدادات المنهج بعد العمولات
    out += ["## جدول موحد: كل إعدادات المنهج بعد العمولات", ""]
    for pn, start in PERIODS.items():
        per = "full" if start == "2016-01-01" else "2018_now"
        rows = [[k, *fmt(v)] for k, v in unified[pn].items()]
        for mk, mn in (("ksa", "KSA"), ("ew", "EW")):
            for cfg in ("A125", "A250", "B125"):
                for u, un in (("all", "كل السوق"), ("pure", "النقية"), ("strict", "النقية صارم")):
                    for five in ("", "_five"):
                        tag = f"{mk}_{cfg}_{u}_{per}{five}"
                        if (R / f"equity_{tag}.csv").exists():
                            rows.append([f"{cfg} / {mn} / {un}{' + 5/6' if five else ''}", *fmt(stats(net_curve(tag, COST)))])
        bench = rows[:3]
        rows = bench + sorted(rows[3:], key=lambda r: -float(r[4]))
        out += [f"### {pn} (مرتب حسب سنوي÷تراجع)", "", md_table(["الإعداد", "العائد", "سنوياً", "أسوأ تراجع", "سنوي÷تراجع"], rows), ""]

    (R / "final_checks.md").write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))
