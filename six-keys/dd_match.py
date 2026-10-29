"""معيار حلال بنفس أسوأ تراجع المنهج: نسبة w في سلة النقية الشهرية (بعد العمولات) والباقي مرابحة،
تُختار بالتنصيف بحيث يساوي أسوأ تراجع للمعيار أسوأ تراجع المنهج، ثم يُقارن العائد السنوي.
  python dd_match.py   ← results/dd_match.md
"""
from __future__ import annotations

import pandas as pd

import data
from cash_yield import RATES, blend, cash_fraction, with_cash
from final_checks import COST, R, md_table, net_curve, rebalanced, stats

METHODS = {"B125 / KSA / النقية": "ksa_B125_pure", "B125 / EW / النقية": "ew_B125_pure"}


def match_weight(asset: pd.Series, rate: float, target_dd: float) -> tuple[float, dict]:
    """أصغر w في [0, 1] يبلغ بها أسوأ تراجع المعيار target_dd (التراجع يزيد مع w)."""
    lo, hi = 0.0, 1.0
    if stats(blend(asset, rate, hi, COST))["أسوأ تراجع"] > target_dd:   # حتى 100% سلة أقل تراجعاً
        return hi, stats(blend(asset, rate, hi, COST))
    for _ in range(30):
        mid = (lo + hi) / 2
        if stats(blend(asset, rate, mid, COST))["أسوأ تراجع"] > target_dd:
            lo = mid
        else:
            hi = mid
    return hi, stats(blend(asset, rate, hi, COST))


if __name__ == "__main__":
    closes = pd.DataFrame({s: data.load_prices(s)["Close"] for s in data.symbols()})
    sharia = data.load_sharia()
    pure = pd.DataFrame({s: pd.Series(data.pure_mask(sharia, s, closes.index), index=closes.index) for s in closes})
    hist_days = closes.notna().cumsum()

    def pure_on(d):  # نفس تعريف final_checks.py
        prev = closes.index[closes.index < d]
        if not len(prev):
            return []
        ok = pure.loc[prev[-1]] & closes.loc[prev[-5:]].notna().any() & (hist_days.loc[prev[-1]] >= 60)
        return ok.index[ok].tolist()

    out = ["# معيار حلال بنفس تراجع المنهج", "",
           f"المعيار = w × سلة النقية الشهرية + (1−w) × مرابحة، إعادة توازن شهرية، العمولة {COST:.2%} لكل جهة. "
           "w تُختار ليساوي أسوأ تراجع للمعيار أسوأ تراجع المنهج (بعد العمولات وبنفس عائد الكاش).", ""]
    for pn, per, start in (("2016–اليوم", "full", "2016-01-01"), ("2018–اليوم", "2018_now", "2018-01-01")):
        bcurve = rebalanced(closes.loc[start:], pure_on, "M", COST)[0]
        rows = []
        for label, stem in METHODS.items():
            tag = f"{stem}_{per}"
            cash, net = cash_fraction(tag, closes), net_curve(tag, COST)
            for rate in RATES:
                m = stats(with_cash(net, cash, rate))
                w, b = match_weight(bcurve, rate, m["أسوأ تراجع"])
                rows.append([label, f"{rate:.0%}", f"{m['أسوأ تراجع']:.1%}", f"{w:.0%}", f"{b['أسوأ تراجع']:.1%}",
                             f"{m['سنوياً']:+.2%}", f"{b['سنوياً']:+.2%}", f"{m['سنوياً'] - b['سنوياً']:+.2%}"])
        out += [f"## {pn}", "", md_table(["المنهج", "عائد الكاش", "تراجع المنهج", "نسبة السلة في المعيار",
                                            "تراجع المعيار", "المنهج سنوياً", "المعيار سنوياً", "الفرق"], rows), ""]
    (R / "dd_match.md").write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))
