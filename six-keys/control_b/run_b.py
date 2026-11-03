"""الضابط (ب): سلة النقية + شرط اتجاه السوق (المفتاح 3 كما في B125). القواعد في B_RULES.md — لا تُعدَّل.

  python control_b/run_b.py   ← control_b/results.md + control_b/equity_b_*.csv
لا يعدّل أي ملف خارج control_b/.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import data  # noqa: E402
from backtest import trend_series  # noqa: E402
from cash_yield import RATES, blend, cash_fraction, with_cash  # noqa: E402
from dd_match import match_weight  # noqa: E402
from final_checks import COST, R, md_table, net_curve, rebalanced, stats  # noqa: E402
from keys import Params  # noqa: E402

START = "2016-01-01"
B125 = {"strict": "ksa_B125_strict_full", "pure": "ksa_B125_pure_full"}
END = pd.read_csv(R / f"equity_{B125['strict']}.csv", index_col=0, parse_dates=True).index[-1]
P = Params(pivot_n=8, support_tol=0.05, sr_lookback=125)   # B125


def market_up(all_days: pd.DatetimeIndex) -> pd.Series:
    """نفس backtest.py: اتجاه KSA بتأخير يوم، ممدود على أيام التداول السعودية."""
    mkt, name, lag = data.load_benchmark()
    assert name.startswith("KSA") and lag == 1, name
    up = trend_series(mkt.loc[:END], P) == "صاعد"
    up.index = up.index + pd.Timedelta(days=lag)
    return up.reindex(up.index.union(all_days)).ffill().fillna(False).astype(bool).reindex(all_days)


def run_b(opens, closes, up, pick, rate):
    """محاكاة (ب) يومياً. الحالة: قيمة كل سهم عند إغلاق الأمس + كاش."""
    days = closes.index
    prev_close = closes.ffill()
    r_co = (opens / prev_close.shift(1))            # من إغلاق الأمس إلى افتتاح اليوم
    r_oc = (closes / opens)                          # من الافتتاح إلى الإغلاق
    r_co = r_co.where(opens.notna(), 1.0).fillna(1.0)
    r_oc = r_oc.where(opens.notna() & closes.notna(), 1.0).fillna(1.0)
    # القص عند ±50% على العائد اليومي الكامل (كما في السلة): نقص الجزأين بالتناسب إن تجاوز
    full = (r_co * r_oc).clip(0.5, 1.5)
    scale = full / (r_co * r_oc)
    r_co = r_co * np.sqrt(scale); r_oc = r_oc * np.sqrt(scale)
    ret_co, ret_oc = r_co.to_numpy(), r_oc.to_numpy()
    col = {s: i for i, s in enumerate(closes.columns)}

    h = np.zeros(len(closes.columns)); cash = 1.0
    in_mkt, pending = False, None           # pending: "in" / "out"
    eq, invested, comm_total = [], [], 0.0
    entries = exits = rebal = 0
    month = None
    for t, d in enumerate(days):
        dt = (d - days[t - 1]).days if t else 0
        cash *= (1 + rate) ** (dt / 365.25)
        h = h * ret_co[t]                    # الافتتاح
        new_month = month is not None and d.month != month
        month = d.month
        trade_to = None
        if pending == "out" and in_mkt:
            v = h.sum(); c = COST * v
            cash += v - c; comm_total += c; h[:] = 0; in_mkt = False; exits += 1
        elif pending == "in" and not in_mkt:
            trade_to = pick(d); in_mkt = True; entries += 1
        elif in_mkt and new_month:
            trade_to = pick(d); rebal += 1
        pending = None
        if trade_to is not None:
            idx = [col[s] for s in trade_to if s in col]
            V = cash + h.sum()
            if idx:
                tgt = np.zeros_like(h); tgt[idx] = 1.0 / len(idx)
                cur = h / V
                tr = np.abs(tgt - cur).sum() * V
                c = COST * tr
                Vn = V - c
                h = tgt * Vn; cash = 0.0; comm_total += c
            else:                            # لا أسهم مؤهلة (قبل نشر أول قائمة) ← كاش
                cash, h = V, np.zeros_like(h)
        h = h * ret_oc[t]                    # الإغلاق
        eq.append(cash + h.sum()); invested.append(h.sum())
        # إشارة الإغلاق ← أمر الغد
        if up.iloc[t] and not in_mkt:
            pending = "in"
        elif not up.iloc[t] and in_mkt:
            pending = "out"
    s = pd.Series(eq, index=days)
    inv = pd.Series(invested, index=days) / s
    return s, {"inv": inv, "comm": comm_total, "entries": entries, "exits": exits, "rebal": rebal}


def basket_comm(closes, pick):
    """سلة النقية الشهرية بعد العمولات + مجموع العمولات (نسبة من رأس المال الابتدائي)."""
    curve, to = rebalanced(closes, pick, "M", COST)
    gross, _ = rebalanced(closes, pick, "M", 0.0)
    # العمولة المدفوعة تقريباً: دوران سنوي × سنوات × متوسط المستوى × COST
    years = (curve.index[-1] - curve.index[0]).days / 365.25
    return curve, to * years * COST * float(curve.mean()), to


def b125_info(tag, closes):
    eq = pd.read_csv(R / f"equity_{tag}.csv", index_col=0, parse_dates=True)["equity"]
    t = pd.read_csv(R / f"trades_{tag}.csv", parse_dates=["entry_date", "exit_date"])
    net = net_curve(tag, COST)
    hit = 1 - (net / eq) / (net / eq).shift(1).fillna(1)
    comm = float((hit * net.shift(1).fillna(1)).sum())
    cash = cash_fraction(tag, closes)
    return net, cash, {"comm": comm, "entries": len(t), "exits": int(t.exit_date.notna().sum()),
                       "time_in": float((cash < 0.99).mean()), "avg_inv": float(1 - cash.mean())}


def yearly(s: pd.Series) -> pd.Series:
    y = s.groupby(s.index.year).last()
    first = s.iloc[0]
    return y / pd.concat([pd.Series([first]), y.iloc[:-1]]).to_numpy() - 1


if __name__ == "__main__":
    syms = data.symbols()
    prices = {s: data.load_prices(s).loc[:END] for s in syms}
    closes_all = pd.DataFrame({s: df["Close"] for s, df in prices.items()})
    opens_all = pd.DataFrame({s: df["Open"] for s, df in prices.items()}).reindex(closes_all.index)
    sharia = {k: data.load_sharia(strict=(k == "strict")) for k in ("strict", "pure")}
    hist_days = closes_all.notna().cumsum()

    def make_pick(sh):
        pure = pd.DataFrame({s: data.pure_mask(sh, s, closes_all.index) for s in syms}, index=closes_all.index)

        def pick(d):   # نفس pure_on في final_checks.py
            prev = closes_all.index[closes_all.index < d]
            if not len(prev):
                return []
            ok = pure.loc[prev[-1]] & closes_all.loc[prev[-5:]].notna().any() & (hist_days.loc[prev[-1]] >= 60)
            return ok.index[ok].tolist()
        return pick

    pick_strict, pick_pure = make_pick(sharia["strict"]), make_pick(sharia["pure"])
    up_all = market_up(closes_all.index)
    c, o, up = closes_all.loc[START:], opens_all.loc[START:], up_all.loc[START:]

    B, Binfo = {}, {}
    for rate in RATES:
        B[rate], Binfo[rate] = run_b(o, c, up, pick_strict, rate)
        B[rate].to_csv(HERE / f"equity_b_cash{int(rate * 100)}.csv", header=["equity"])
    bi = Binfo[0.0]
    bsk_s, bsk_s_comm, bsk_s_to = basket_comm(c, pick_strict)
    bsk_p, bsk_p_comm, _ = basket_comm(c, pick_pure)
    ref = {}
    for k, tag in B125.items():
        net, cash, info = b125_info(tag, closes_all)
        ref[k] = ({r: with_cash(net, cash, r) for r in RATES}, info)

    pct = lambda x: f"{x:+.1%}"
    out = ["# نتائج الضابط (ب)", "",
           f"الفترة: {c.index[0].date()} ← {c.index[-1].date()}. كل الأرقام بعد العمولات ({COST:.2%} لكل جهة).",
           f"مؤشر السوق: KSA بتأخير يوم، `pivot_n=8`. الأسهم: النقية بسريان صارم (من تاريخ النشر).", ""]

    # 1) الجدول الموحد
    rows = []
    def row(name, curves, info):
        cells = [name]
        for r in RATES:
            st = stats(curves[r])
            cells.append(f"{pct(st['العائد'])} / {st['سنوياً']:+.2%} / {st['أسوأ تراجع']:.1%}")
        cells += info
        rows.append(cells)
    row("(ب) سلة النقية + شرط السوق", B,
        [f"{(bi['inv'] > 0.01).mean():.0%}", f"{bi['inv'].mean():.0%}", f"{bi['entries']} / {bi['exits']}",
         f"{bi['comm']:.1%}"])
    for k, name in (("strict", "B125 النقية (صارم) — المرجع"), ("pure", "B125 النقية (غير صارم، المعتمد في التقرير)")):
        curves, info = ref[k]
        row(name, curves, [f"{info['time_in']:.0%}", f"{info['avg_inv']:.0%}", f"{info['entries']} / {info['exits']}",
                           f"{info['comm']:.1%}"])
    row("سلة النقية الدائمة (صارم)", {r: bsk_s for r in RATES}, ["100%", "100%", "1 / 0", f"~{bsk_s_comm:.1%}"])
    row("سلة النقية الدائمة (غير صارم)", {r: bsk_p for r in RATES}, ["100%", "100%", "1 / 0", f"~{bsk_p_comm:.1%}"])
    out += ["## 1. المقارنة العامة", "",
            "كل خلية عائد: العائد الكلي / السنوي / أسوأ تراجع. «الوقت في السوق» = نسبة الأيام بأي استثمار؛ "
            "«متوسط الاستثمار» = متوسط نسبة المحفظة في الأسهم. العمولات = مجموع ما دُفع كنسبة من رأس المال الابتدائي (عند كاش 0%). "
            "عدد الدخول/الخروج لـB125 = عدد الصفقات (لكل سهم)، ولـ(ب) = دخول/خروج المحفظة كاملة.", "",
            md_table(["المحفظة", "كاش 0%", "كاش 2%", "كاش 4%", "الوقت في السوق", "متوسط الاستثمار",
                      "دخول / خروج", "العمولات"], rows), "",
            f"(ب): {bi['rebal']} إعادة توازن شهرية إضافة إلى الدخول. عمولة السلة الدائمة تقريبية "
            f"(دوران سنوي {bsk_s_to:.0%} × سنوات × متوسط المستوى).", ""]

    # 2) تساوي التراجع
    out += ["## 2. عند تساوي التراجع (طريقة dd_match)", "",
            "الخليط = w × (ب) + (1−w) × مرابحة، توازن شهري، عمولة على المنقول. w بحيث يساوي تراجع الخليط تراجع B125 (حد أعلى 100%).", ""]
    verdicts, matched = {}, {}
    for k in ("strict", "pure"):
        rows = []
        for r in RATES:
            m = stats(ref[k][0][r])
            w, bst = match_weight(B[r], r, m["أسوأ تراجع"])
            mix = blend(B[r], r, w, COST)
            matched[(k, r)] = (w, mix)
            diff = m["سنوياً"] - bst["سنوياً"]
            rows.append([f"{r:.0%}", f"{m['أسوأ تراجع']:.1%}", f"{stats(B[r])['أسوأ تراجع']:.1%}", f"{w:.0%}",
                         f"{bst['أسوأ تراجع']:.1%}", f"{m['سنوياً']:+.2%}", f"{bst['سنوياً']:+.2%}", f"{diff:+.2%}"])
            if k == "strict":
                verdicts[r] = {"diff": diff}
        out += [f"### مقابل {'B125 الصارمة (المرجع)' if k == 'strict' else 'B125 غير الصارمة (للاطلاع)'}", "",
                md_table(["عائد الكاش", "تراجع B125", "تراجع (ب) كاملاً", "w في (ب)", "تراجع الخليط",
                          "B125 سنوياً", "الخليط سنوياً", "فرق B125"], rows), ""]

    # 3) سنة بسنة
    for k in ("strict",):
        out += ["## 3. سنة بسنة: B125 الصارمة مقابل (ب)", "",
                "«(ب) مطابق» = خليط (ب) بنفس تراجع B125 من القسم 2. «يفوز» = B125 أعلى من (ب) المطابق.", ""]
        for r in RATES:
            yb = yearly(ref[k][0][r]); yB = yearly(B[r]); w, mix = matched[(k, r)]; ym = yearly(mix)
            rows = []
            wins = 0
            for y in yb.index:
                d = yb[y] - ym[y]; wins += d > 0
                rows.append([str(y), f"{yb[y]:+.1%}", f"{yB[y]:+.1%}", f"{ym[y]:+.1%}", f"{d:+.1%}",
                             "B125" if d > 0 else "(ب)"])
            verdicts[r]["wins"], verdicts[r]["years"] = int(wins), len(yb)
            out += [f"### كاش {r:.0%} (w = {w:.0%})", "",
                    md_table(["السنة", "B125", "(ب) كاملاً", "(ب) مطابق", "فرق B125", "الأعلى"], rows), "",
                    f"B125 أعلى في {wins} من {len(yb)} سنة.", ""]

    # 4) الحكم الآلي
    out += ["## 4. تطبيق المعيار (مقابل B125 الصارمة)", ""]
    labels = {}
    for r, v in verdicts.items():
        if v["diff"] <= 0:
            lab = "المفاتيح لا تضيف قيمة تُذكر"
        elif v["diff"] >= 0.02 and v["wins"] > v["years"] / 2:
            lab = "المفاتيح تضيف قيمة"
        else:
            lab = "غير حاسمة"
        labels[r] = lab
        out.append(f"- كاش {r:.0%}: فرق {v['diff']:+.2%} سنوياً، B125 أعلى في {v['wins']}/{v['years']} سنة ← **{lab}**")
    final = labels[RATES[0]] if len(set(labels.values())) == 1 else "غير حاسمة (الحكم يختلف بين معدلات الكاش)"
    out += ["", f"**الحكم:** {final}", ""]
    (HERE / "results.md").write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))
