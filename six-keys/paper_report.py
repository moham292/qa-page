"""الملخص الشهري للتداول الورقي: المحفظة مقابل سلة النقية الشهرية، ومقابل معيار حلال بنفس التعرّض.

  python paper_report.py            ← paper/monthly/<الشهر>.md (يستخدم بيانات paper/data المحمّلة يومياً)
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

import data
from cash_yield import blend
from final_checks import COST, md_table, rebalanced
from paper_trade import CAPITAL, END, P, load_all, load_state, pure_symbols


def total(s: pd.Series) -> float:
    return float(s.iloc[-1] / s.iloc[0] - 1)


def dd(s: pd.Series) -> float:
    return float((s / s.cummax() - 1).min())


BT = Path(__file__).parent / "results"
BT_TAG = "ksa_B125_pure_full"   # الاختبار التاريخي المطابق للتجربة: B125، النقية، المفتاح 3 من KSA، 2016–اليوم
ROUND_TRIP = 2 * COST           # الاختبار التاريخي بلا عمولات؛ الورقي يخصمها


def backtest_expectations(n_days: int) -> dict:
    """مقارنة الورقي بتوقعات الاختبار التاريخي (تُقرأ من سجل صفقاته، لا أرقام ثابتة)."""
    t = pd.read_csv(BT / f"trades_{BT_TAG}.csv", parse_dates=["entry_date", "exit_date"])
    days = pd.read_csv(BT / f"equity_{BT_TAG}.csv", index_col=0, parse_dates=True).index
    c = t[t.exit_date.notna()]
    entries = pd.Series(1, index=t.entry_date).groupby(level=0).sum().reindex(days, fill_value=0)
    if n_days > 0:
        win = entries.rolling(n_days).sum().dropna()
        exp_n = f"{len(t) / len(days) * n_days:.1f} (المعتاد تاريخياً لنافذة بنفس الطول: {win.quantile(.1):.0f}–{win.quantile(.9):.0f})"
    else:
        exp_n = "0"
    return {"win_g": (c.ret > 0).mean(), "win_n": ((c.ret - ROUND_TRIP) > 0).mean(), "avg_g": c.ret.mean(),
            "avg_n": (c.ret - ROUND_TRIP).mean(), "dd_med": t.max_drawdown.median(), "dd_p10": t.max_drawdown.quantile(.1),
            "dd_min": t.max_drawdown.min(), "n": len(t), "exp_n": exp_n}


if __name__ == "__main__":
    eqf = P / "equity.csv"
    if not eqf.exists():
        raise SystemExit("لا يوجد paper/equity.csv بعد")
    eq = pd.read_csv(eqf, parse_dates=["date"]).set_index("date")
    st = load_state()
    sharia = data.load_sharia()
    universe = sorted(set().union(*[pure_symbols(sharia, d) for d in eq.index[[0, -1]]]) | set(st["positions"]))
    _, adj, ksa = load_all(universe)   # السلة على السلسلة المعدّلة بالتوزيعات (عائد إجمالي، مثل المحفظة التي تقبض التوزيعات)
    closes = pd.DataFrame({s: df["Close"] for s, df in adj.items()})
    pure = pd.DataFrame({s: pd.Series(data.pure_mask(sharia, s, closes.index), index=closes.index) for s in closes})
    hist_days = closes.notna().cumsum()

    def pure_on(d):  # نفس تعريف final_checks.py
        prev = closes.index[closes.index < d]
        if not len(prev):
            return []
        ok = pure.loc[prev[-1]] & closes.loc[prev[-5:]].notna().any() & (hist_days.loc[prev[-1]] >= 60)
        return ok.index[ok].tolist()

    start, end = eq.index[0], eq.index[-1]
    paper = eq["equity"]   # أول صف = إغلاق يوم البداية (100 ألف)
    # السلة تبدأ أيضاً من إغلاق يوم البداية: أول عائد هو عائد يوم التداول التالي
    if len(closes.loc[start:end]) > 1:
        basket = pd.concat([pd.Series([1.0], index=[start]), rebalanced(closes.loc[start:end], pure_on, "M", COST)[0]])
    else:
        basket = pd.Series([1.0], index=[start])
    w = float(eq["exposure"].mean())
    k = ksa["Close"].loc[:end]
    k = k.loc[k.index >= k.loc[:start].index[-1]]   # من آخر إغلاق لـ KSA حتى يوم البداية

    trades = pd.read_csv(P / "trades.csv") if (P / "trades.csv").exists() else pd.DataFrame()
    n_buy = int((trades.get("action") == "شراء").sum()) if len(trades) else 0
    sells = trades[trades["action"] == "بيع"] if len(trades) else trades
    rows = [["المحفظة الورقية (بعد العمولات، كاش 0%)", f"{total(paper):+.2%}", f"{dd(paper):.1%}"],
            ["سلة النقية الشهرية (بعد العمولات)", f"{total(basket):+.2%}", f"{dd(basket):.1%}"]]
    for rate in (0.0, 0.04):
        b = blend(basket, rate, w, COST)
        rows.append([f"معيار حلال بنفس التعرّض ({w:.0%} سلة + مرابحة {rate:.0%})", f"{total(b):+.2%}", f"{dd(b):.1%}"])
    rows.append(["KSA (للمرجع، ليس حلالاً بالضرورة)", f"{total(k):+.2%}", f"{dd(k):.1%}"])
    # مقارنة بتوقعات الاختبار التاريخي
    n_days = len(eq) - 1   # الصف الأول = إغلاق يوم البداية (بلا تداول)
    e = backtest_expectations(n_days)
    rets = pd.to_numeric(sells["return"]) if len(sells) else pd.Series(dtype=float)
    dds = list(pd.to_numeric(sells["max_drawdown"])) if len(sells) else []
    dds += [p["max_dd"] for p in st["positions"].values()]
    na = "—"
    exp_rows = [
        ["نسبة الصفقات الرابحة (المغلقة)", f"{(rets > 0).mean():.0%} من {len(rets)}" if len(rets) else na,
         f"{e['win_n']:.0%} (قبل العمولة {e['win_g']:.0%})"],
        ["متوسط عائد الصفقة (المغلقة)", f"{rets.mean():+.2%}" if len(rets) else na,
         f"{e['avg_n']:+.2%} (قبل العمولة {e['avg_g']:+.2%})"],
        ["أسوأ نزول داخل صفقة (مغلقة ومفتوحة)", f"{min(dds):.1%}" if dds else na,
         f"الوسيط {e['dd_med']:.1%}، 10% من الصفقات أسوأ من {e['dd_p10']:.1%}، الأسوأ تاريخياً {e['dd_min']:.1%}"],
        ["عدد صفقات الدخول", f"{n_buy}", e["exp_n"]],
    ]
    se = (e["win_n"] * (1 - e["win_n"]) / len(rets)) ** 0.5 if len(rets) else None
    month = end.strftime("%Y-%m")
    out = [f"# الملخص الشهري للتداول الورقي — حتى {end.date()}", "",
           f"الفترة: {start.date()} ← {end.date()} ({len(eq)} يوم تداول). متوسط الاستثمار الفعلي: {w:.0%}. "
           f"صفقات: {n_buy} دخول، {len(sells)} خروج"
           + (f"، متوسط عائد الصفقة المغلقة {pd.to_numeric(sells['return']).mean():+.2%}" if len(sells) else "") + ".", "",
           md_table(["المحفظة", "العائد منذ البداية", "أسوأ تراجع"], rows), "",
           f"رصيد المحفظة: {eq['equity'].iloc[-1]:,.0f} ريال. الصفقات المفتوحة: {', '.join(st['positions']) or 'لا شيء'}.", "",
           f"## مقارنة مع توقعات الاختبار التاريخي (B125 النقية، {e['n']} صفقة، 2016–اليوم)", "",
           md_table(["المقياس", "الورقي حتى الآن", "توقع الاختبار التاريخي"], exp_rows), "",
           "التوقع بعد العمولة يطابق الورقي (0.15% لكل جهة). "
           + (f"بعدد {len(rets)} صفقة مغلقة، الفرق في نسبة الرابحة ضمن ±{2 * se:.0%} لا يعني شيئاً إحصائياً. " if se else "")
           + "إن جاء أسوأ نزول أعمق من الأسوأ تاريخياً فهذا يستحق الانتباه، لأن القواعد بلا وقف خسارة.", "",
           "⚠ فترة قصيرة وعدد صفقات قليل: مؤشر أولي، لا حكم. المعيار الحلال يستخدم متوسط تعرّض المحفظة الفعلي حتى الآن."]
    (P / "monthly").mkdir(exist_ok=True)
    (P / "monthly" / f"{month}.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))
    if end >= END:
        print("\nPAPER_ENDED — هذا الملخص الختامي للتجربة.")
