"""الاختبار التاريخي للمفاتيح الستة — محاكاة محفظة كما في الدورة.

القواعد:
  الدخول (محاضرة 5 و8): 6 من 6 على إغلاق اليوم ← الشراء بافتتاح اليوم التالي.
  الخروج (محاضرة 8): التقاطع السلبي في MACD فقط ← البيع بافتتاح اليوم التالي.
  تقسيم المحفظة (محاضرة 9): خمسة أجزاء، جزء كاش للطوارئ، وأربعة للعمل ← كل صفقة 6/6 = 20% من رأس المال.
  استثناء 5 من 6 (محاضرة 9، اختياري لمن "يحب المخاطرة"): مسموح فقط إذا تحقق المفتاحان 1 و2،
     وبربع جزء = 5% من رأس المال.
  لا وقف خسارة (لم يُذكر) — نقيس أسوأ نزول داخل كل صفقة لنعرف حجم الثغرة.

الترتيب عند زيادة المرشحين على الأجزاء المتاحة: لم تحدده الدورة (التوزيعات للمفاضلة فقط) —
  نأخذ الأعلى سيولة (متوسط قيمة التداول 20 يوماً)، وهذا اجتهاد.

يقارن النتيجة بالشراء والاحتفاظ بمؤشر تاسي (معيار خالد في محاضرة 3).
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

import data
from keys import Params, macd, pivots, sma, support_status, trend

SLOT_FULL = 0.20    # جزء كامل
SLOT_RISKY = 0.05   # ربع جزء لـ 5 من 6
MAX_FULL_SLOTS = 4  # الجزء الخامس كاش للطوارئ


@dataclass
class Trade:
    symbol: str
    kind: str          # "6/6" أو "5/6"
    entry_date: pd.Timestamp
    entry: float
    weight: float
    exit_date: pd.Timestamp | None = None
    exit: float | None = None
    ret: float | None = None
    max_drawdown: float = 0.0  # أسوأ نزول من سعر الدخول أثناء الصفقة


def _prep(df: pd.DataFrame, p: Params) -> pd.DataFrame:
    df = df.copy()
    body = (df["Close"] - df["Open"]).abs()
    df["_avg_body"] = body.rolling(p.avg_window, min_periods=5).mean()
    df["_avg_vol"] = df["Volume"].rolling(p.avg_window, min_periods=5).mean()
    return df


def _visible(piv, t: int, n: int):
    """القمم/القيعان المعروفة حتى اليوم t (القمة عند i لا تتأكد إلا في i+n)."""
    highs, lows = piv
    return [i for i in highs if i + n <= t], [i for i in lows if i + n <= t]


def trend_series(df: pd.DataFrame, p: Params) -> pd.Series:
    df = _prep(df, p)
    piv = pivots(df, p.pivot_n)
    return pd.Series([trend(df.iloc[:t + 1], p, _visible(piv, t, p.pivot_n)) for t in range(len(df))],
                     index=df.index)


def signals(sym: str, df: pd.DataFrame, tasi_up: pd.Series, fund, sharia, p: Params,
            warmup: int = 60) -> pd.DataFrame:
    """جدول يومي بالمفاتيح الستة وإشارة الخروج لسهم واحد (بلا نظر للمستقبل)."""
    df = _prep(df, p)
    piv = pivots(df, p.pivot_n)
    s55 = sma(df["Close"], p.sma_len)
    line, sig = macd(df["Close"], p.macd_fast, p.macd_slow, p.macd_signal)
    diff = (line - sig).to_numpy()
    value = (df["Close"] * df["Volume"]).rolling(20, min_periods=5).mean()
    rows = []
    for t in range(warmup, len(df)):
        d = df.index[t]
        vis = _visible(piv, t, p.pivot_n)
        sl = df.iloc[:t + 1]
        k1 = trend(sl, p, vis) == "صاعد"
        k2 = True if fund is None else bool(data.net_income_positive(fund, sym, d))
        k3 = bool(tasi_up.get(d, False))
        k4 = k1 and support_status(sl, p, vis)[0] == "دعم"  # الدعم لا يُحسب إلا للمرشحين (للسرعة)
        k5 = min(df["Open"].iloc[t], df["Close"].iloc[t]) > s55.iloc[t]  # جسم الشمعة كله فوق المتوسط
        k6 = diff[t] > 0
        if p.macd_mode == "event":
            k6 = k6 and any(diff[j - 1] <= 0 < diff[j]
                            for j in range(max(1, t - p.macd_event_days + 1), t + 1))
        pure = data.is_pure(sharia, sym, d)
        rows.append({"date": d, "k1": k1, "k2": k2, "k3": k3, "k4": k4, "k5": bool(k5), "k6": bool(k6),
                     "exit": bool(diff[t - 1] >= 0 > diff[t]), "allowed": pure is not False,
                     "liquidity": value.iloc[t]})
    out = pd.DataFrame(rows).set_index("date")
    out["score"] = out[["k1", "k2", "k3", "k4", "k5", "k6"]].sum(axis=1)
    return out


def simulate(sigs: dict[str, pd.DataFrame], prices: dict[str, pd.DataFrame],
             allow_five: bool) -> tuple[pd.Series, list[Trade]]:
    """محفظة بأوزان ثابتة من رأس المال الابتدائي (مبسّطة: بلا إعادة استثمار داخل اليوم، بلا عمولات)."""
    dates = sorted(set().union(*[s.index for s in sigs.values()]))
    cash, equity_curve, exposure = 1.0, [], []
    open_pos: dict[str, tuple[Trade, float]] = {}  # symbol -> (trade, shares)
    closed: list[Trade] = []
    pending_exit, pending_entry = set(), []

    for d in dates:
        # تنفيذ أوامر الأمس بافتتاح اليوم
        for sym in list(pending_exit):
            if sym in open_pos and d in prices[sym].index:
                tr, sh = open_pos.pop(sym)
                px = prices[sym].at[d, "Open"]
                cash += sh * px
                tr.exit_date, tr.exit, tr.ret = d, px, px / tr.entry - 1
                closed.append(tr)
                pending_exit.discard(sym)
        for sym, kind, w in pending_entry:
            if sym in open_pos or d not in prices[sym].index:
                continue
            equity = cash + sum(sh * prices[s].loc[:d, "Close"].iloc[-1] for s, (_, sh) in open_pos.items())
            amount = min(w * equity, cash)
            if amount <= 0:
                continue
            px = prices[sym].at[d, "Open"]
            open_pos[sym] = (Trade(sym, kind, d, px, w), amount / px)
            cash -= amount
        pending_entry = []

        # تحديث أسوأ نزول، وتقييم المحفظة على الإغلاق
        value = cash
        for sym, (tr, sh) in open_pos.items():
            if d in prices[sym].index:
                tr.max_drawdown = min(tr.max_drawdown, prices[sym].at[d, "Low"] / tr.entry - 1)
            value += sh * prices[sym].loc[:d, "Close"].iloc[-1]
        equity_curve.append((d, value))
        exposure.append((d, 1 - cash / value))

        # إشارات اليوم ← أوامر الغد
        for sym in open_pos:
            s = sigs[sym]
            if d in s.index and s.at[d, "exit"]:
                pending_exit.add(sym)
        # السعة: أربعة أجزاء عمل؛ صفقة 5/6 تستهلك ربع جزء، والجزء الخامس يبقى كاشاً.
        used = sum(1 if tr.kind == "6/6" else 0.25 for tr, _ in open_pos.values())
        cands = []
        for sym, s in sigs.items():
            if sym in open_pos or d not in s.index or not s.at[d, "allowed"]:
                continue
            row = s.loc[d]
            if row["score"] == 6:
                cands.append((0, -row["liquidity"], sym, "6/6", SLOT_FULL))
            elif allow_five and row["score"] == 5 and row["k1"] and row["k2"]:
                cands.append((1, -row["liquidity"], sym, "5/6", SLOT_RISKY))
        for _, _, sym, kind, w in sorted(cands):
            need = 1 if kind == "6/6" else 0.25
            if used + need > MAX_FULL_SLOTS:
                continue
            used += need
            pending_entry.append((sym, kind, w))

    for sym, (tr, sh) in open_pos.items():  # صفقات مفتوحة حتى نهاية البيانات
        px = prices[sym]["Close"].iloc[-1]
        tr.exit, tr.ret = px, px / tr.entry - 1
        closed.append(tr)
    eq = pd.Series(dict(equity_curve)).sort_index()
    eq.attrs["exposure"] = pd.Series(dict(exposure)).sort_index()
    return eq, closed


def _max_dd(s: pd.Series) -> float:
    return float((s / s.cummax() - 1).min())


def _cagr(s: pd.Series) -> float:
    years = (s.index[-1] - s.index[0]).days / 365.25
    return float((s.iloc[-1] / s.iloc[0]) ** (1 / years) - 1) if years > 0 else float("nan")


def equal_weight(prices: dict[str, pd.DataFrame], dates: pd.DatetimeIndex) -> pd.Series:
    """معيار ثانوي: متوسط العائد اليومي لكل الأسهم المتاحة (أوزان متساوية، إعادة توازن يومية)."""
    closes = pd.DataFrame({s: df["Close"] for s, df in prices.items()}).reindex(dates)
    r = closes.pct_change(fill_method=None).mean(axis=1).fillna(0)
    return (1 + r).cumprod()


def summarize(eq: pd.Series, trades: list[Trade], bench: pd.DataFrame, bench_name: str = "تاسي",
              ew: pd.Series | None = None) -> dict:
    t = bench["Close"].loc[eq.index[0]:eq.index[-1]]
    out = {
        "الفترة": f"{eq.index[0].date()} ← {eq.index[-1].date()}",
        "عائد المحفظة": f"{eq.iloc[-1] / eq.iloc[0] - 1:.2%} (سنوياً {_cagr(eq):.2%})",
        f"عائد {bench_name} (شراء واحتفاظ)": f"{t.iloc[-1] / t.iloc[0] - 1:.2%} (سنوياً {_cagr(t):.2%})",
        "أسوأ تراجع للمحفظة": f"{_max_dd(eq):.2%}",
        f"أسوأ تراجع لـ {bench_name}": f"{_max_dd(t):.2%}",
    }
    if ew is not None:
        out["عائد كل الأسهم بأوزان متساوية"] = f"{ew.iloc[-1] - 1:.2%} (سنوياً {_cagr(ew):.2%})، أسوأ تراجع {_max_dd(ew):.2%}"
    if "exposure" in eq.attrs:
        x = eq.attrs["exposure"]
        out["متوسط نسبة الاستثمار (الباقي كاش)"] = f"{x.mean():.0%} — أيام بلا أي صفقة: {(x < 0.01).mean():.0%}"
    out["عدد الصفقات"] = len(trades)
    if trades:
        r = np.array([x.ret for x in trades])
        dd = np.array([x.max_drawdown for x in trades])
        out |= {
            "نسبة الصفقات الرابحة": f"{(r > 0).mean():.0%}",
            "متوسط عائد الصفقة": f"{r.mean():.2%}",
            "أسوأ صفقة": f"{r.min():.2%}",
            "أسوأ نزول داخل صفقة (بلا وقف خسارة)": f"{dd.min():.2%}",
        }
        for kind in ("6/6", "5/6"):
            rk = np.array([x.ret for x in trades if x.kind == kind])
            if len(rk):
                out[f"صفقات {kind}"] = f"{len(rk)} — متوسط {rk.mean():.2%}"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", help="بداية الاختبار (بعد فترة الإحماء)")
    ap.add_argument("--end")
    ap.add_argument("--tag", default="", help="لاحقة لأسماء ملفات النتائج")
    ap.add_argument("--pivot-n", type=int, default=3)
    ap.add_argument("--support-tol", type=float, default=0.03)
    ap.add_argument("--macd-mode", choices=["state", "event"], default="state")
    ap.add_argument("--allow-five", action="store_true", help="السماح بـ 5 من 6 بحجم 5%% (محاضرة 9)")
    a = ap.parse_args()
    p = Params(pivot_n=a.pivot_n, support_tol=a.support_tol, macd_mode=a.macd_mode)

    tasi, bench_name, lag = data.load_benchmark()
    print(f"مؤشر السوق: {bench_name}" + (f" — بتأخير {lag} يوم لتجنب النظر للمستقبل" if lag else ""))
    tasi_up = trend_series(tasi, p) == "صاعد"
    if lag:  # حالة المؤشر المعروفة قبل يوم التداول السعودي d: آخر إغلاق قبل d
        tasi_up.index = tasi_up.index + pd.Timedelta(days=lag)
    fund, sharia = data.load_fundamentals(), data.load_sharia()
    if fund is None:
        print("تنبيه: لا يوجد fundamentals.csv — المفتاح 2 يُعتبر متحققاً لكل الأسهم.")
    if sharia is None:
        print("تنبيه: لا يوجد sharia.csv — الفلتر الشرعي معطّل.")

    prices = {s: data.load_prices(s).loc[:a.end] for s in data.symbols()}
    all_days = sorted(set().union(*[df.index for df in prices.values()]))
    tasi_up = tasi_up.reindex(tasi_up.index.union(all_days)).ffill().fillna(False).astype(bool)
    sigs = {s: signals(s, df, tasi_up, fund, sharia, p) for s, df in prices.items() if len(df) > 80}
    if a.start:
        sigs = {s: x.loc[a.start:] for s, x in sigs.items() if len(x.loc[a.start:])}
    eq, trades = simulate(sigs, prices, a.allow_five)
    pd.DataFrame([asdict(t) for t in trades]).to_csv(f"trades{a.tag}.csv", index=False, encoding="utf-8-sig")
    eq.to_csv(f"equity{a.tag}.csv", header=["equity"])
    ew = equal_weight(prices, eq.index)
    for k, v in summarize(eq, trades, tasi, bench_name, ew).items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
