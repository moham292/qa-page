"""التداول الورقي للعملات — أربع محافظ مستقلة: (أ) و(ب) للقائمة الأساسية، و(أ) و(ب) للملحق.
القواعد في CRYPTO_RULES.md ولا تُعدَّل. على نمط six-keys/paper_trade.py و six-keys/paper_b.py (لا يعدّلهما ولا يكتب في six-keys/).

  python crypto/paper_crypto.py             # ينزّل الأسعار، يعالج كل الأيام الجديدة (بما فيها الجمعة والسبت)، يحفظ، يطبع الملخص
  python crypto/paper_crypto.py --no-fetch  # بلا تنزيل
  python crypto/paper_crypto.py --status    # جدول المحافظ الأربع بلا معالجة
اختبار على فترة تاريخية في مجلد مؤقت (لا يلمس crypto/paper/):
  python crypto/paper_crypto.py --root /tmp/x --test-start 2025-11-01 [--test-until 2026-01-15]

السوق يعمل 7 أيام: اليوم = شمعة UTC. يُعالَج كل يوم حتى آخر شمعة مكتملة متاحة لكل العملات (أقدم «آخر تاريخ» بينها)،
فإن فشل تنزيل عملة تأجلت المعالجة كلها حتى تكتمل بياناتها، ويعوّض التشغيل التالي ما فات.
الإشارات على البيانات المنظّفة حتى يوم الإشارة فقط (clean على ما قبله، بلا نظر للمستقبل)؛ التنفيذ والتقييم بالأسعار الخام.
يكتب في crypto/paper/: data/<الرمز>.csv، <المحفظة>/{state.json,equity.csv,trades.csv}، daily/<التاريخ>.md، fetch_log.csv.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

import common
from common import COST, HERE, LIST_NAMES, LISTS, MARKET, PARAMS, WARMUP, clean, download, load_csv
from keys import above_sma, macd_negative_cross, macd_positive, support_status, trend

SIGNAL_START = None   # يُحدَّد عند التفعيل: pd.Timestamp("YYYY-MM-DD") = أول يوم إشارة (أول يوم تالٍ للتفعيل)
END = pd.Timestamp("2027-04-29")   # آخر يوم تقييم، مع نهاية تجربة الأسهم
CAPITAL = 100_000.0
SLOT, MAX_SLOTS = 0.20, 4
OVERLAP_DAYS = 15
PORTFOLIOS = {"core_A": ("core", "A"), "core_B": ("core", "B"), "ext_A": ("ext", "A"), "ext_B": ("ext", "B")}
PNAME = {"core_A": "الأساسية (أ) المفاتيح", "core_B": "الأساسية (ب) الضابط",
         "ext_A": "الملحق (أ) المفاتيح", "ext_B": "الملحق (ب) الضابط"}
ALL_SYMS = sorted({s for v in LISTS.values() for s in v} | {MARKET})


# ---------- البيانات ----------

def update_symbol(root: Path, sym: str) -> bool:
    f = root / "data" / f"{sym}.csv"
    old = load_csv(f) if f.exists() else None
    start = None if old is None or old.empty else str((old.index[-1] - pd.Timedelta(days=OVERLAP_DAYS)).date())
    new = download(sym, start)
    if new is None:
        return False
    merged = new if old is None else pd.concat([old[~old.index.isin(new.index)], new]).sort_index()
    merged.to_csv(f)
    return True


def fetch(root: Path) -> list[str]:
    (root / "data").mkdir(parents=True, exist_ok=True)
    failed = [s for s in ALL_SYMS if not update_symbol(root, s)]
    log = root / "fetch_log.csv"
    pd.DataFrame([{"run": str(pd.Timestamp.now(tz="UTC").round("s")), "failed": " ".join(failed)}]).to_csv(
        log, mode="a", header=not log.exists(), index=False)
    return failed


def load_raw(root: Path) -> dict[str, pd.DataFrame]:
    out = {}
    for s in ALL_SYMS:
        f = root / "data" / f"{s}.csv"
        if f.exists():
            r = load_csv(f)
            out[s] = r[(r[["Open", "High", "Low", "Close"]] > 0).all(axis=1)]
    return out


def price_on(raw, s, d, col):
    df = raw.get(s)
    return float(df.at[d, col]) if df is not None and d in df.index else None


def last_close(raw, s, d):
    df = raw.get(s)
    if df is None:
        return None
    x = df["Close"].loc[:d]
    return float(x.iloc[-1]) if len(x) else None


# ---------- الحالة ----------

def new_state(kind: str) -> dict:
    if kind == "A":
        return {"cash": CAPITAL, "positions": {}, "pending_entries": [], "pending_exits": [], "last_date": None}
    return {"cash": CAPITAL, "holdings": {}, "in_market": False, "pending": None, "last_date": None}


def load_state(root: Path, pid: str) -> dict:
    f = root / pid / "state.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else new_state(PORTFOLIOS[pid][1])


def save_state(root: Path, pid: str, st: dict) -> None:
    (root / pid).mkdir(parents=True, exist_ok=True)
    (root / pid / "state.json").write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def append_csv(path: Path, rows: list[dict]) -> None:
    if rows:
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(path, mode="a", header=not path.exists(), index=False, encoding="utf-8")


# ---------- (أ) المفاتيح ----------

def equity_a(st, raw, d):
    v = st["cash"]
    for s, pos in st["positions"].items():
        c = last_close(raw, s, d)
        v += pos["shares"] * (c if c is not None else pos["entry_price"])
    return v


def evaluate(sl: pd.DataFrame, market_up: bool) -> int:
    k1 = trend(sl, PARAMS) == "صاعد"
    k4 = k1 and support_status(sl, PARAMS)[0] == "دعم"
    keys = [k1, True, market_up, k4, above_sma(sl, PARAMS), macd_positive(sl, PARAMS)]   # المفتاح 2 لا ينطبق ← متحقق
    return sum(map(bool, keys))


def process_a(st, raw, sig_df, syms, d, market_up, log):
    acts = []
    # 1) أوامر الأمس بافتتاح اليوم: الخروج أولاً، ثم الدخول (يبقى معلّقاً إن لم يوجد سعر)
    for s in list(st["pending_exits"]):
        o = price_on(raw, s, d, "Open")
        if o is None or s not in st["positions"]:
            continue
        pos = st["positions"].pop(s)
        gross = pos["shares"] * o
        fee = gross * COST
        st["cash"] += gross - fee
        ret = (gross - fee) / pos["invested"] - 1
        st["pending_exits"].remove(s)
        log.append({"date": str(d.date()), "action": "بيع", "symbol": s, "price": o, "shares": pos["shares"],
                    "amount": round(gross, 2), "fee": round(fee, 2), "return": round(ret, 4),
                    "entry_date": pos["entry_date"], "max_drawdown": round(pos["max_dd"], 4)})
        acts.append(f"بيع {s} @ {o:,.4g} ({ret:+.2%})")
    still = []
    for s in st["pending_entries"]:
        o = price_on(raw, s, d, "Open")
        if s in st["positions"]:
            continue
        if o is None:
            still.append(s); continue
        prev = d - pd.Timedelta(days=1)
        amount = min(SLOT * equity_a(st, raw, prev), st["cash"])
        if amount <= 1:
            continue
        fee = amount * COST / (1 + COST)
        shares = (amount - fee) / o
        st["cash"] -= amount
        st["positions"][s] = {"shares": shares, "entry_date": str(d.date()), "entry_price": o,
                              "invested": amount, "max_dd": 0.0}
        log.append({"date": str(d.date()), "action": "شراء", "symbol": s, "price": o, "shares": shares,
                    "amount": round(amount - fee, 2), "fee": round(fee, 2), "return": "", "entry_date": str(d.date()),
                    "max_drawdown": ""})
        acts.append(f"شراء {s} @ {o:,.4g} ({amount:,.0f})")
    st["pending_entries"] = still
    # 2) التقييم على الإغلاق
    for s, pos in st["positions"].items():
        lo = price_on(raw, s, d, "Low")
        if lo is not None:
            pos["max_dd"] = min(pos["max_dd"], lo / pos["entry_price"] - 1)
    eq = equity_a(st, raw, d)
    # 3) إشارات الإغلاق ← أوامر الغد
    orders = []
    if d < END:
        for s in st["positions"]:
            sl = sig_df.get(s)
            if sl is not None and d in sl.index and s not in st["pending_exits"] and macd_negative_cross(sl, PARAMS):
                st["pending_exits"].append(s); orders.append(f"خروج {s}")
        used = len(st["positions"]) + len(st["pending_entries"])
        cands = []
        for s in syms:
            sl = sig_df.get(s)
            if s in st["positions"] or s in st["pending_entries"] or sl is None or d not in sl.index:
                continue
            if len(sl) <= WARMUP:   # 60 يوم بيانات على الأقل قبل يوم الإشارة
                continue
            if evaluate(sl, market_up) == 6:
                liq = float((sl["Close"] * sl["Volume"]).rolling(20, min_periods=5).mean().iloc[-1])
                cands.append((-liq, s))
        for _, s in sorted(cands):
            if used >= MAX_SLOTS:
                break
            st["pending_entries"].append(s); orders.append(f"دخول {s}"); used += 1
    st["last_date"] = str(d.date())
    return {"equity": eq, "cash": st["cash"], "acts": acts, "orders": orders,
            "holding": sorted(st["positions"])}


# ---------- (ب) الضابط ----------

def eligible_b(raw, syms, d_signal):
    """نفس pick في backtest_crypto.py: 60 يوم بيانات حتى يوم الإشارة، وسعر خلال آخر 5 أيام."""
    out = []
    for s in syms:
        r = raw.get(s)
        if r is None:
            continue
        h = r.loc[:d_signal]
        if len(h) >= WARMUP and (h.index > d_signal - pd.Timedelta(days=5)).any():
            out.append(s)
    return out


def px_b(raw, s, d, col):
    v = price_on(raw, s, d, col)
    return v if v is not None else last_close(raw, s, d)


def process_b(st, raw, syms, d, market_up, log):
    acts = []
    prev_d = d - pd.Timedelta(days=1)
    new_month = d.day == 1
    target = None
    if st["pending"] == "out" and st["in_market"]:
        fee_t = 0.0
        for s, sh in st["holdings"].items():
            p = px_b(raw, s, d, "Open")
            g = sh * p; fee = g * COST; fee_t += fee
            st["cash"] += g - fee
            log.append({"date": str(d.date()), "action": "بيع", "symbol": s, "shares": sh, "price": p,
                        "amount": round(g, 2), "fee": round(fee, 2)})
        st["holdings"], st["in_market"] = {}, False
        acts.append(f"خروج كامل (عمولة {fee_t:,.0f})")
    elif st["pending"] == "in" and not st["in_market"]:
        target = eligible_b(raw, syms, prev_d); st["in_market"] = True
        acts.append(f"دخول: {len(target)} عملات بأوزان متساوية")
    elif st["in_market"] and new_month:
        target = eligible_b(raw, syms, prev_d)
        acts.append(f"إعادة توازن شهرية: {len(target)} عملات")
    st["pending"] = None
    if target is not None:
        prices = {s: px_b(raw, s, d, "Open") for s in set(target) | set(st["holdings"])}
        prices = {s: p for s, p in prices.items() if p}
        target = [s for s in target if s in prices]
        cur = {s: st["holdings"].get(s, 0.0) * prices.get(s, 0.0) for s in st["holdings"]}
        V = st["cash"] + sum(cur.values())
        if target:
            tgt0 = V / len(target)
            turnover = sum(abs((tgt0 if s in target else 0.0) - cur.get(s, 0.0)) for s in set(target) | set(cur))
            tgt = (V - COST * turnover) / len(target)
            for s in sorted(set(target) | set(cur)):
                dv = (tgt if s in target else 0.0) - cur.get(s, 0.0)
                if abs(dv) > 0.01:
                    log.append({"date": str(d.date()), "action": "شراء" if dv > 0 else "بيع", "symbol": s,
                                "shares": abs(dv) / prices[s], "price": prices[s], "amount": round(abs(dv), 2),
                                "fee": round(COST * abs(dv), 2)})
            st["holdings"] = {s: tgt / prices[s] for s in target}
            st["cash"] = 0.0
        else:
            st["cash"], st["holdings"] = V, {}
    eq = st["cash"] + sum(sh * (last_close(raw, s, d) or 0.0) for s, sh in st["holdings"].items())
    orders = []
    if d < END:
        if market_up and not st["in_market"]:
            st["pending"] = "in"; orders.append("دخول السوق")
        elif not market_up and st["in_market"]:
            st["pending"] = "out"; orders.append("خروج من السوق")
    st["last_date"] = str(d.date())
    return {"equity": eq, "cash": st["cash"], "acts": acts, "orders": orders, "holding": sorted(st["holdings"])}


# ---------- الملخص ----------

def curve_stats(root: Path, pid: str):
    f = root / pid / "equity.csv"
    if not f.exists():
        return None
    e = pd.read_csv(f)
    eq = e["equity"]
    return {"eq": eq.iloc[-1], "ret": eq.iloc[-1] / CAPITAL - 1,
            "dd": float((eq / eq.cummax().clip(lower=CAPITAL) - 1).min()), "exp": e["exposure"].iloc[-1],
            "date": e["date"].iloc[-1]}


def table(root: Path) -> str:
    rows = ["| المحفظة | آخر يوم | الرصيد | منذ البداية | أسوأ تراجع | مستثمر |", "|---|---|---|---|---|---|"]
    for pid in PORTFOLIOS:
        s = curve_stats(root, pid)
        rows.append(f"| {PNAME[pid]} | {s['date']} | {s['eq']:,.0f} | {s['ret']:+.2%} | {s['dd']:.1%} | {s['exp']:.0%} |"
                    if s else f"| {PNAME[pid]} | – | – | – | – | – |")
    return "\n".join(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--root", help="مجلد بديل لـ crypto/paper (للاختبار فقط)")
    ap.add_argument("--test-start", help="بداية إشارات تجريبية — مسموح فقط مع --root")
    ap.add_argument("--test-until", help="آخر يوم يُعالج — للاختبار فقط مع --root")
    a = ap.parse_args()
    default_root = HERE / "paper"
    root = Path(a.root).resolve() if a.root else default_root
    if (a.test_start or a.test_until) and root == default_root:
        raise SystemExit("خطأ: --test-start و--test-until للاختبار فقط ويتطلبان --root لمجلد غير crypto/paper.")
    if a.status:
        print(table(root)); return
    start = pd.Timestamp(a.test_start) if a.test_start else SIGNAL_START
    if start is None:
        raise SystemExit("خطأ: SIGNAL_START غير محدد (None) في crypto/paper_crypto.py — التداول الورقي للعملات لم يُفعَّل بعد. "
                         "يُحدَّد عند التفعيل بعد مراجعة الاختبار التاريخي. لم يُعالج شيء.")
    start = pd.Timestamp(start)
    root.mkdir(parents=True, exist_ok=True)
    notes = []
    if not a.no_fetch:
        failed = fetch(root)
        if failed:
            notes.append(f"فشل تنزيل: {', '.join(failed)} — المعالجة تقف عند آخر يوم مكتمل لكل العملات")
    raw = load_raw(root)
    missing = [s for s in ALL_SYMS if s not in raw]
    if missing:
        raise SystemExit(f"لا بيانات محفوظة لـ: {', '.join(missing)} — لم يُعالج شيء")
    last_common = min(df.index[-1] for df in raw.values())
    limit = min(last_common, END)
    if a.test_until:
        limit = min(limit, pd.Timestamp(a.test_until))
    states = {pid: load_state(root, pid) for pid in PORTFOLIOS}
    lasts = {pid: pd.Timestamp(st["last_date"]) if st["last_date"] else start - pd.Timedelta(days=1)
             for pid, st in states.items()}
    if len(set(lasts.values())) != 1:
        raise SystemExit(f"خطأ: المحافظ الأربع غير متزامنة: {lasts}")
    last = next(iter(lasts.values()))
    days = list(pd.date_range(max(last + pd.Timedelta(days=1), start), limit, freq="D"))
    if not days:
        print("\n".join(notes))
        print("PAPER_ENDED" if last >= END else f"(عملات): لا يوم جديد بعد {last.date()} (آخر شمعة مكتملة لكل العملات {last_common.date()})")
        print("\n" + table(root))
        return
    reps = []
    for d in days:
        sig = {s: clean(raw[s].loc[:d]) for s in ALL_SYMS}      # تنظيف حتى يوم الإشارة فقط
        market_up = trend(sig[MARKET], PARAMS) == "صاعد"          # المفتاح 3: BTC على إغلاق نفس اليوم
        day = {"date": d, "market_up": market_up, "p": {}}
        for pid, (lst, kind) in PORTFOLIOS.items():
            log = []
            if kind == "A":
                r = process_a(states[pid], raw, sig, LISTS[lst], d, market_up, log)
            else:
                r = process_b(states[pid], raw, LISTS[lst], d, market_up, log)
            append_csv(root / pid / "equity.csv", [{"date": str(d.date()), "equity": round(r["equity"], 2),
                                                   "cash": round(r["cash"], 2),
                                                   "exposure": round(1 - r["cash"] / r["equity"], 4) if r["equity"] else 0}])
            append_csv(root / pid / "trades.csv", log)
            day["p"][pid] = r
        reps.append(day)
    for pid in PORTFOLIOS:
        save_state(root, pid, states[pid])
    L = [f"# التداول الورقي للعملات — {reps[-1]['date'].date()}", ""]
    if len(reps) > 1:
        L.append(f"عولجت {len(reps)} أيام: {reps[0]['date'].date()} ← {reps[-1]['date'].date()}")
        L.append("")
    for rp in reps:
        parts = []
        for pid, r in rp["p"].items():
            if r["acts"] or r["orders"]:
                parts.append(f"{PNAME[pid]}: " + "؛ ".join(r["acts"] + [f"أمر الغد: {o}" for o in r["orders"]]))
        L.append(f"- {rp['date'].date()} (BTC {'صاعد' if rp['market_up'] else 'غير صاعد'}): "
                 + (" | ".join(parts) if parts else "لا تنفيذ ولا أوامر"))
    L += ["", "**المحافظ الأربع:**", "", table(root), ""]
    held = [f"{PNAME[pid]}: {', '.join(r['holding']) or 'كاش'}" for pid, r in reps[-1]["p"].items()]
    L += ["**المراكز:** " + " | ".join(held), ""]
    L += [f"- ⚠ {n}" for n in notes]
    md = "\n".join(L) + "\n"
    (root / "daily").mkdir(exist_ok=True)
    (root / "daily" / f"{reps[-1]['date'].date()}.md").write_text(md, encoding="utf-8")
    print(md)
    if reps[-1]["date"] >= END:
        print("PAPER_ENDED — انتهت فترة التداول الورقي للعملات.")


if __name__ == "__main__":
    main()
