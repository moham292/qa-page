"""التداول الورقي للأمام — B125 النقية، المفتاح 3 من KSA. القواعد مثبتة في PAPER_RULES.md ولا تُعدَّل.

يُشغَّل بعد إغلاق السوق كل يوم تداول:
  python paper_trade.py            # يحدّث الأسعار، ينفّذ أوامر الأمس بافتتاح اليوم، يقيّم على الإغلاق، يولّد أوامر الغد
  python paper_trade.py --no-fetch # بلا تنزيل (على البيانات المحفوظة)
إن فاتت أيام، يعالجها كلها بالترتيب من الأسعار التاريخية.

البيانات (محفوظة في الفرع، paper/data/):
  raw/<الرمز>.csv   أسعار خام غير معدّلة + Dividends + Splits. التنزيل الأول 3 سنوات، ثم يومياً آخر ~15 يوماً تُدمج.
  KSA.csv           صندوق KSA معدّل (طلب واحد كامل كل يوم).
للإشارات: تُبنى سلسلة معدّلة بالتوزيعات من الخام (مثل Yahoo) ثم تنظيف الأداة (data.clean، ومنه تصحيح الإجراءات الرأسمالية).
للمحفظة: التنفيذ والتقييم بالأسعار الخام، والتوزيعات تُضاف للكاش يوم الاستحقاق.
يكتب في paper/: state.json، trades.csv، equity.csv، daily/<التاريخ>.md، fetch_log.csv، ويطبع الملخص.
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from yfinance.exceptions import YFRateLimitError

import data
from keys import Params, above_sma, macd_negative_cross, macd_positive, support_status, trend

ROOT = Path(__file__).parent
P = ROOT / "paper"
PDATA = P / "data"
RAW = PDATA / "raw"
SIGNAL_START = pd.Timestamp("2026-10-29")   # أول يوم إشارة
END = pd.Timestamp("2027-04-29")            # آخر يوم تقييم (آخر إشارات في يوم التداول السابق له)
CAPITAL = 100_000.0
COST = 0.0015
SLOT, MAX_SLOTS = 0.20, 4
PARAMS = Params(pivot_n=8, support_tol=0.05, sr_lookback=125)   # B125 (باقي المعاملات افتراضية مثبتة)
HISTORY_YEARS = 3
OVERLAP_DAYS = 15          # نافذة التحديث اليومي (أيام تقويمية قبل آخر يوم محفوظ)
BIG_MOVE = 0.105           # حد التذبذب ±10% + هامش تقريب
MAX_FAIL_SHARE = 0.20      # إن فشل تنزيل أكثر من هذا (أو KSA) يؤجَّل المعالجة للتشغيل التالي
COLS = ["Open", "High", "Low", "Close", "Volume", "Dividends", "Splits"]

logging.getLogger("yfinance").setLevel(logging.CRITICAL)
yf.config.debug.hide_exceptions = False


# ---------- التنزيل والتخزين ----------

def pure_symbols(sharia: pd.DataFrame, on: pd.Timestamp) -> list[str]:
    r = sharia[(sharia.valid_from <= on) & (sharia.valid_to.isna() | (sharia.valid_to >= on))
               & (sharia.classification == "نقية")]
    return sorted(s for s in r.symbol.unique() if not s.startswith("9"))


def download(ticker: str, start: str, adjusted: bool) -> pd.DataFrame | None:
    """None = فشل بعد إعادة المحاولة. إطار فارغ = لا بيانات في النافذة."""
    for attempt in range(4):
        try:
            df = yf.download(ticker, start=start, progress=False, auto_adjust=adjusted, actions=not adjusted,
                             multi_level_index=False)
            if df is None:
                raise ValueError("no data")
            df.index = pd.to_datetime(df.index).tz_localize(None)
            df.index.name = "Date"
            if not adjusted:
                df = df.rename(columns={"Stock Splits": "Splits"})
                for c in ("Dividends", "Splits"):
                    if c not in df:
                        df[c] = 0.0
                return df[COLS]
            return df[["Open", "High", "Low", "Close", "Volume"]]
        except Exception as e:
            rate = isinstance(e, YFRateLimitError) or "Rate" in str(e)
            time.sleep(120 if rate else 5)
    return None


def update_raw(sym: str) -> tuple[bool, list[pd.Timestamp], bool]:
    """يدمج آخر الأيام في raw/<sym>.csv. يعيد (نجح، التواريخ الجديدة، حدثت تجزئة → أُعيد التنزيل الكامل)."""
    f = RAW / f"{sym}.csv"
    old = pd.read_csv(f, parse_dates=["Date"]).set_index("Date") if f.exists() else None
    full_start = str(date.today() - timedelta(days=365 * HISTORY_YEARS))
    start = full_start if old is None or old.empty else str((old.index[-1] - timedelta(days=OVERLAP_DAYS)).date())
    new = download(f"{sym}.SR", start, adjusted=False)
    if new is None:
        return False, [], False
    split = old is not None and not new.empty and (new["Splits"] > 0).any() and start != full_start
    if split:   # Yahoo يعدّل التاريخ كله عند التجزئة ← نعيد التنزيل الكامل بدل الدمج
        new = download(f"{sym}.SR", full_start, adjusted=False)
        if new is None:
            return False, [], False
        old = None
    merged = new if old is None else pd.concat([old[~old.index.isin(new.index)], new]).sort_index()
    added = [d for d in new.index if old is None or d not in old.index]
    merged.to_csv(f)
    return True, added, bool(split)


def fetch(symbols: list[str]) -> dict:
    RAW.mkdir(parents=True, exist_ok=True)
    rep = {"failed": [], "added": {}, "splits": [], "ksa_ok": True}
    ksa = download("KSA", str(date.today() - timedelta(days=365 * HISTORY_YEARS)), adjusted=True)
    if ksa is None or ksa.empty:
        rep["ksa_ok"] = False
    else:
        ksa.to_csv(PDATA / "KSA.csv")
    for s in symbols:
        ok, added, split = update_raw(s)
        if not ok:
            rep["failed"].append(s)
        else:
            rep["added"][s] = added
            if split:
                rep["splits"].append(s)
        time.sleep(1.5)
    return rep


# ---------- التحميل ----------

def adjust_dividends(raw: pd.DataFrame) -> pd.DataFrame:
    """سلسلة معدّلة بالتوزيعات (طريقة Yahoo): قبل كل يوم استحقاق تُضرب الأسعار في 1 − التوزيع ÷ إغلاق اليوم السابق."""
    df = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
    div = raw["Dividends"].fillna(0).to_numpy()
    c = raw["Close"].to_numpy()
    factor = np.ones(len(df))
    for i in np.nonzero(div > 0)[0]:
        if i > 0 and c[i - 1] > 0:
            factor[:i] *= 1 - div[i] / c[i - 1]
    for col in ("Open", "High", "Low", "Close"):
        df[col] = df[col] * factor
    return df


def load_all(symbols: list[str]):
    """يعيد (الخام، المعدّل المنظّف للإشارات، KSA)."""
    raw, adj = {}, {}
    for s in symbols:
        f = RAW / f"{s}.csv"
        if not f.exists():
            continue
        r = pd.read_csv(f, parse_dates=["Date"]).set_index("Date").sort_index()
        r = r[(r["Volume"] > 0) & (r[["Open", "High", "Low", "Close"]] > 0).all(axis=1)].dropna(subset=["Close"])
        if len(r):
            raw[s] = r
            a = data.clean(adjust_dividends(r))
            # تقريب لأربع منازل: يثبّت تعادل القمم/القيعان (أسعار تداول بوحدات 0.01–0.1) ضد ضوضاء الفاصلة العائمة
            adj[s] = a.assign(**{c: a[c].round(4) for c in ("Open", "High", "Low", "Close")})
    ksa = pd.read_csv(PDATA / "KSA.csv", parse_dates=["Date"]).set_index("Date").sort_index()
    return raw, adj, ksa[["Open", "High", "Low", "Close", "Volume"]].dropna()


def big_moves(raw: dict, days: list[pd.Timestamp], held: set) -> list[str]:
    """حركات يومية خام تتجاوز ±10% (بعد احتساب التوزيع) في الأيام المعالجة."""
    out = []
    for s, r in raw.items():
        rr = (r["Close"] + r["Dividends"].fillna(0)) / r["Close"].shift(1) - 1
        for d in days:
            if d in rr.index and abs(rr.at[d]) > BIG_MOVE:
                tag = " — **في المحفظة: التقييم بالسعر الخام قد يحتاج مراجعة يدوية**" if s in held else ""
                out.append(f"{s} {d.date()}: {rr.at[d]:+.1%} (يتجاوز حد التذبذب ← غالباً إجراء رأسمالي؛ "
                           f"عُدّل تلقائياً في سلسلة الإشارات){tag}")
    return out


# ---------- الحالة والسجلات ----------

def load_state() -> dict:
    f = P / "state.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return {"cash": CAPITAL, "positions": {}, "pending_entries": [], "pending_exits": [], "last_date": None}


def save_state(st: dict) -> None:
    (P / "state.json").write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def append_csv(name: str, rows: list[dict]) -> None:
    if not rows:
        return
    f = P / name
    pd.DataFrame(rows).to_csv(f, mode="a", header=not f.exists(), index=False, encoding="utf-8")


# ---------- القواعد ----------

def price_on(px, s, d, col):
    df = px.get(s)
    return float(df.at[d, col]) if df is not None and d in df.index else None


def last_close(px, s, d):
    df = px.get(s)
    if df is None:
        return None
    x = df["Close"].loc[:d]
    return float(x.iloc[-1]) if len(x) else None


def equity(st, raw, d, include_today=True):
    day = d if include_today else d - pd.Timedelta(days=1)
    v = st["cash"]
    for s, pos in st["positions"].items():
        c = last_close(raw, s, day)
        v += pos["shares"] * (c if c is not None else pos["entry_price"])
    return v


def evaluate(df: pd.DataFrame, market_up: bool) -> dict:
    k1 = trend(df, PARAMS) == "صاعد"
    k4 = k1 and support_status(df, PARAMS)[0] == "دعم"
    k5, k6 = above_sma(df, PARAMS), macd_positive(df, PARAMS)
    keys = [k1, True, market_up, k4, k5, k6]   # المفتاح 2 غير مطبّق ← متحقق
    return {"score": sum(map(bool, keys)), "keys": keys}


def process_day(st, raw, adj, ksa, d, pure_today, log):
    buys, sells, divs, warns = [], [], [], []
    executing = st["last_date"] is not None
    # 0) توزيعات الأسهم المملوكة (يوم الاستحقاق) ← كاش
    for s, pos in st["positions"].items():
        dv = price_on(raw, s, d, "Dividends")
        if dv:
            amt = pos["shares"] * dv
            st["cash"] += amt
            pos["dividends"] = pos.get("dividends", 0.0) + amt
            row = {"date": str(d.date()), "action": "توزيع", "symbol": s, "price": dv, "shares": round(pos["shares"], 4),
                   "amount": round(amt, 2), "fee": 0, "return": "", "entry_date": pos["entry_date"], "max_drawdown": ""}
            divs.append(row); log.append(row)
    # 1) أوامر الأمس بافتتاح اليوم (أسعار خام): الخروج أولاً
    if executing:
        for s in list(st["pending_exits"]):
            o = price_on(raw, s, d, "Open")
            if o is None or s not in st["positions"]:
                continue
            pos = st["positions"].pop(s)
            gross = pos["shares"] * o
            fee = gross * COST
            st["cash"] += gross - fee
            ret = (gross - fee + pos.get("dividends", 0.0)) / pos["invested"] - 1
            st["pending_exits"].remove(s)
            row = {"date": str(d.date()), "action": "بيع", "symbol": s, "price": round(o, 4), "shares": round(pos["shares"], 4),
                   "amount": round(gross, 2), "fee": round(fee, 2), "return": round(ret, 4),
                   "entry_date": pos["entry_date"], "max_drawdown": round(pos["max_dd"], 4)}
            sells.append(row); log.append(row)
        still = []
        for s in st["pending_entries"]:
            o = price_on(raw, s, d, "Open")
            if s in st["positions"]:
                continue
            if o is None:
                still.append(s); continue
            eq = equity(st, raw, d, include_today=False)
            amount = min(SLOT * eq, st["cash"])
            if amount <= 1:
                continue
            fee = amount * COST / (1 + COST)
            shares = (amount - fee) / o
            st["cash"] -= amount
            st["positions"][s] = {"shares": shares, "entry_date": str(d.date()), "entry_price": o,
                                  "invested": amount, "max_dd": 0.0, "dividends": 0.0}
            row = {"date": str(d.date()), "action": "شراء", "symbol": s, "price": round(o, 4), "shares": round(shares, 4),
                   "amount": round(amount - fee, 2), "fee": round(fee, 2), "return": "", "entry_date": str(d.date()),
                   "max_drawdown": ""}
            buys.append(row); log.append(row)
        st["pending_entries"] = still
    # 2) التقييم على الإغلاق (خام)
    for s, pos in st["positions"].items():
        lo = price_on(raw, s, d, "Low")
        if lo is not None:
            pos["max_dd"] = min(pos["max_dd"], lo / pos["entry_price"] - 1)
        if s not in pure_today:
            warns.append(f"{s} لم يعد نقياً حسب القائمة السارية (لا خروج إجباري حسب القواعد)")
    eq = equity(st, raw, d)
    # 3) إشارات اليوم (سلسلة معدّلة) ← أوامر الغد
    new_exits, new_entries, cands = [], [], []
    if d < END:
        market_up = trend(ksa.loc[:d - pd.Timedelta(days=1)], PARAMS) == "صاعد"
        for s in st["positions"]:
            df = adj.get(s)
            if df is not None and d in df.index and s not in st["pending_exits"] and macd_negative_cross(df.loc[:d], PARAMS):
                st["pending_exits"].append(s); new_exits.append(s)
        used = len(st["positions"]) + len(st["pending_entries"])
        for s in pure_today:
            df = adj.get(s)
            if s in st["positions"] or s in st["pending_entries"] or df is None or d not in df.index:
                continue
            sl = df.loc[:d]
            if len(sl) < 80:
                continue
            if evaluate(sl, market_up)["score"] == 6:
                liq = float((sl["Close"] * sl["Volume"]).rolling(20, min_periods=5).mean().iloc[-1])
                cands.append((-liq, s))
        for _, s in sorted(cands):
            if used >= MAX_SLOTS:
                break
            st["pending_entries"].append(s); new_entries.append(s); used += 1
        st["market_up"] = market_up
    st["last_date"] = str(d.date())
    return {"date": d, "buys": buys, "sells": sells, "divs": divs, "new_entries": new_entries, "new_exits": new_exits,
            "equity": eq, "cash": st["cash"], "invested": eq - st["cash"], "warns": warns, "n_cands": len(cands)}


def summary_md(r: dict, st: dict, raw) -> str:
    d = r["date"].date()
    L = [f"# التداول الورقي — {d}", "",
         f"**رصيد المحفظة:** {r['equity']:,.0f} ريال ({r['equity'] / CAPITAL - 1:+.2%} منذ البداية) — "
         f"كاش {r['cash']:,.0f}، مستثمر {r['invested'] / r['equity']:.0%}", ""]
    L.append("**صفقات دخلت (بافتتاح اليوم):** " + ("، ".join(f"{b['symbol']} @ {b['price']:.2f} ({b['amount']:,.0f})" for b in r["buys"]) or "لا شيء"))
    L.append("**صفقات خرجت (بافتتاح اليوم):** " + ("، ".join(f"{x['symbol']} @ {x['price']:.2f} ({x['return']:+.2%})" for x in r["sells"]) or "لا شيء"))
    if r["divs"]:
        L.append("**توزيعات:** " + "، ".join(f"{x['symbol']} {x['amount']:,.0f}" for x in r["divs"]))
    L.append("**أوامر الغد:** دخول: " + ("، ".join(r["new_entries"]) or "لا شيء") + " | خروج: " + ("، ".join(r["new_exits"]) or "لا شيء"))
    L.append(f"**اتجاه السوق (KSA):** {'صاعد' if st.get('market_up') else 'غير صاعد'} — مرشحون 6/6: {r['n_cands']}")
    if st["positions"]:
        L += ["", "| السهم | دخول | سعر الدخول | الإغلاق | العائد | أسوأ نزول |", "|---|---|---|---|---|---|"]
        for s, pos in st["positions"].items():
            c = last_close(raw, s, r["date"]) or pos["entry_price"]
            L.append(f"| {s} | {pos['entry_date']} | {pos['entry_price']:.2f} | {c:.2f} | {c / pos['entry_price'] - 1:+.2%} | {pos['max_dd']:.1%} |")
    for w in r["warns"]:
        L.append(f"- ⚠ {w}")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true")
    a = ap.parse_args()
    P.mkdir(exist_ok=True); (P / "daily").mkdir(exist_ok=True)
    st = load_state()
    sharia = data.load_sharia()
    today = pd.Timestamp(date.today())
    universe = sorted(set(pure_symbols(sharia, min(today, END))) | set(st["positions"]) | set(st["pending_entries"]))
    notes = []
    if not a.no_fetch:
        rep = fetch(universe)
        append_csv("fetch_log.csv", [{"run": str(pd.Timestamp.now().round("s")), "symbols": len(universe),
                                      "failed": len(rep["failed"]), "ksa_ok": rep["ksa_ok"],
                                      "failed_list": " ".join(rep["failed"])}])
        if rep["failed"]:
            notes.append(f"فشل تنزيل {len(rep['failed'])} من {len(universe)} سهماً بعد إعادة المحاولة: {', '.join(rep['failed'][:20])}")
        if rep["splits"]:
            notes.append(f"تجزئة مسجّلة في Yahoo (أُعيد تنزيل التاريخ كاملاً): {', '.join(rep['splits'])}")
        held_failed = set(rep["failed"]) & set(st["positions"])
        if not rep["ksa_ok"] or len(rep["failed"]) > MAX_FAIL_SHARE * len(universe):
            print("\n".join(notes) + ("\nفشل تنزيل KSA." if not rep["ksa_ok"] else "")
                  + "\nتأجيل المعالجة: البيانات ناقصة اليوم، وسيعوّضها التشغيل التالي تلقائياً.")
            return
        if held_failed:
            notes.append(f"أسهم مملوكة بلا بيانات اليوم (تقييمها بآخر إغلاق معروف): {', '.join(sorted(held_failed))}")
    raw, adj, ksa = load_all(universe)
    counts = pd.Series([d for df in raw.values() for d in df.index]).value_counts()
    days = sorted(counts[counts >= 0.5 * len(raw)].index)   # يوم تداول فعلي: لنصف الأسهم على الأقل بيانات فيه
    last = pd.Timestamp(st["last_date"]) if st["last_date"] else SIGNAL_START - pd.Timedelta(days=1)
    todo = [d for d in days if last < d <= END and d >= SIGNAL_START]
    if not todo:
        print("\n".join(notes))
        print("PAPER_ENDED" if last >= END else f"لا يوم تداول جديد بعد {last.date()}")
        return
    log, reports = [], []
    for d in todo:
        report = process_day(st, raw, adj, ksa, d, pure_symbols(sharia, d), log)
        append_csv("equity.csv", [{"date": str(d.date()), "equity": round(report["equity"], 2), "cash": round(report["cash"], 2),
                                   "exposure": round(report["invested"] / report["equity"], 4)}])
        reports.append(report)
    moves = big_moves(raw, todo, set(st["positions"]) | {s for r in reports for s in (x["symbol"] for x in r["sells"])})
    md = summary_md(reports[-1], st, raw)
    extra = [f"- ⚠ {m}" for m in moves] + [f"- {n}" for n in notes]
    if extra:
        md += "\n**تنبيهات البيانات:**\n" + "\n".join(extra) + "\n"
    for r in reports[:-1]:
        (P / "daily" / f"{r['date'].date()}.md").write_text(summary_md(r, st, raw), encoding="utf-8")
    (P / "daily" / f"{reports[-1]['date'].date()}.md").write_text(md, encoding="utf-8")
    append_csv("trades.csv", log)
    save_state(st)
    if len(reports) > 1:   # تعويض أيام فائتة
        print(f"تعويض {len(reports)} أيام تداول: {reports[0]['date'].date()} ← {reports[-1]['date'].date()}\n")
        for r in reports[:-1]:
            ins = "، ".join(f"{b['symbol']} @ {b['price']:.2f}" for b in r["buys"]) or "لا شيء"
            outs = "، ".join(f"{x['symbol']} ({x['return']:+.2%})" for x in r["sells"]) or "لا شيء"
            print(f"- {r['date'].date()}: دخول: {ins} | خروج: {outs} | الرصيد {r['equity']:,.0f}")
        print()
    print(md)
    if reports[-1]["date"] >= END:
        print("PAPER_ENDED — انتهت فترة التجربة (آخر تقييم 2027-04-29؛ الصفقات المفتوحة مقيّمة بالإغلاق).")


if __name__ == "__main__":
    main()
