"""التداول الورقي للضابط (ب): سلة النقية + شرط السوق. القواعد في PAPER_B_RULES.md و control_b/B_RULES.md ولا تُعدَّل.

مسار مستقل عن تجربة المفاتيح (paper_trade.py): لا يكتب في paper/ إلا أسعار أسهم يملكها (ب) وخرجت من قائمة A.
يقرأ الأسعار الخام التي نزّلها paper_trade.py في نفس التشغيل (paper/data/raw)، ويكتب في paper_b/.
  python paper_b.py            # يعالج أيام التداول الجديدة (يشغَّل بعد paper_trade.py)
  python paper_b.py --status   # مقارنة (أ) و(ب) منذ البداية بلا معالجة
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import pandas as pd

import data
from keys import trend
from paper_trade import (CAPITAL, COST, END, PARAMS, SIGNAL_START, last_close,
                         load_all, price_on, pure_symbols, update_raw)

ROOT = Path(__file__).parent
PB = ROOT / "paper_b"
PA = ROOT / "paper"


def append_csv(name: str, rows: list[dict]) -> None:
    if not rows:
        return
    f = PB / name
    pd.DataFrame(rows).to_csv(f, mode="a", header=not f.exists(), index=False, encoding="utf-8")


def load_state() -> dict:
    f = PB / "state.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return {"cash": CAPITAL, "holdings": {}, "in_market": False, "pending": None, "last_date": None}


def save_state(st: dict) -> None:
    (PB / "state.json").write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def eligible(raw: dict, sharia, d_signal: pd.Timestamp, days: list) -> list[str]:
    """B_RULES: نقي يوم الإشارة، وله سعر خلال آخر 5 أيام تداول، و60 يوم تداول على الأقل."""
    recent = [x for x in days if x <= d_signal][-5:]
    out = []
    for s in pure_symbols(sharia, d_signal):
        r = raw.get(s)
        if r is None:
            continue
        h = r.loc[:d_signal]
        if len(h) >= 60 and h.index.isin(recent).any():
            out.append(s)
    return out


def px(raw, s, d, col):
    """سعر اليوم، أو آخر إغلاق معروف إن لم يتداول (تقريب B_RULES)."""
    v = price_on(raw, s, d, col)
    return v if v is not None else last_close(raw, s, d)


def process_day(st, raw, ksa, sharia, d, prev_d, days, log):
    actions, warns = [], []
    # 0) التوزيعات ← كاش
    for s, sh in st["holdings"].items():
        dv = price_on(raw, s, d, "Dividends")
        if dv:
            st["cash"] += sh * dv
            log.append({"date": str(d.date()), "action": "توزيع", "symbol": s, "shares": round(sh, 4),
                        "price": dv, "amount": round(sh * dv, 2), "fee": 0})
    # 1) أوامر الأمس بافتتاح اليوم
    new_month = prev_d is not None and d.month != prev_d.month
    target = None
    if st["pending"] == "out" and st["in_market"]:
        fee_t = 0.0
        for s, sh in st["holdings"].items():
            p = px(raw, s, d, "Open")
            g = sh * p; fee = g * COST; fee_t += fee
            st["cash"] += g - fee
            log.append({"date": str(d.date()), "action": "بيع", "symbol": s, "shares": round(sh, 4), "price": round(p, 4),
                        "amount": round(g, 2), "fee": round(fee, 2)})
        st["holdings"], st["in_market"] = {}, False
        actions.append(f"خروج كامل من السوق (عمولة {fee_t:,.0f})")
    elif st["pending"] == "in" and not st["in_market"]:
        target = eligible(raw, sharia, prev_d, days); st["in_market"] = True
        actions.append(f"دخول السوق: {len(target)} سهماً بأوزان متساوية")
    elif st["in_market"] and new_month:
        target = eligible(raw, sharia, prev_d, days)
        actions.append(f"إعادة توازن شهرية: {len(target)} سهماً")
    st["pending"] = None
    if target is not None:
        prices = {s: px(raw, s, d, "Open") for s in set(target) | set(st["holdings"])}
        prices = {s: p for s, p in prices.items() if p}
        target = [s for s in target if s in prices]
        cur = {s: st["holdings"].get(s, 0.0) * prices.get(s, 0.0) for s in set(st["holdings"])}
        V = st["cash"] + sum(cur.values())
        if target:
            tgt0 = V / len(target)
            turnover = sum(abs((tgt0 if s in target else 0.0) - cur.get(s, 0.0)) for s in set(target) | set(cur))
            fee_t = COST * turnover
            tgt = (V - fee_t) / len(target)
            for s in sorted(set(target) | set(cur)):
                new_v = tgt if s in target else 0.0
                dv = new_v - cur.get(s, 0.0)
                if abs(dv) > 0.01:
                    log.append({"date": str(d.date()), "action": "شراء" if dv > 0 else "بيع", "symbol": s,
                                "shares": round(abs(dv) / prices[s], 4), "price": round(prices[s], 4),
                                "amount": round(abs(dv), 2), "fee": round(COST * abs(dv), 2)})
            st["holdings"] = {s: tgt / prices[s] for s in target}
            st["cash"] = 0.0
        else:
            st["cash"], st["holdings"] = V, {}
            warns.append("لا أسهم مؤهلة يوم التنفيذ ← بقيت المحفظة كاشاً")
    # 2) الإغلاق
    eq = st["cash"] + sum(sh * (last_close(raw, s, d) or 0.0) for s, sh in st["holdings"].items())
    missing = [s for s in st["holdings"] if price_on(raw, s, d, "Close") is None]
    if len(missing) > 0.1 * max(len(st["holdings"]), 1):   # أقل من 10% أمر عادي (أسهم لم تتداول) فلا يُنبَّه
        warns.append(f"{len(missing)} سهماً مملوكاً بلا سعر اليوم (قُيّمت بآخر إغلاق)")
    # 3) إشارة الإغلاق ← أمر الغد (نفس المفتاح 3 في paper_trade.py)
    order = None
    if d < END:
        up = trend(ksa.loc[:d - pd.Timedelta(days=1)], PARAMS) == "صاعد"
        st["market_up"] = up
        if up and not st["in_market"]:
            st["pending"] = order = "in"
        elif not up and st["in_market"]:
            st["pending"] = order = "out"
    st["last_date"] = str(d.date())
    return {"date": d, "equity": eq, "cash": st["cash"], "actions": actions, "warns": warns, "order": order}


def curve_stats(path: Path) -> tuple[float, float, float] | None:
    if not path.exists():
        return None
    e = pd.read_csv(path)["equity"]
    return e.iloc[-1], e.iloc[-1] / CAPITAL - 1, float((e / e.cummax().clip(lower=CAPITAL) - 1).min())


def comparison() -> str:
    rows = []
    for name, f in (("(أ) المفاتيح الستة", PA / "equity.csv"), ("(ب) سلة النقية + شرط السوق", PB / "equity.csv")):
        s = curve_stats(f)
        rows.append(f"| {name} | {s[0]:,.0f} | {s[1]:+.2%} | {s[2]:.1%} |" if s else f"| {name} | – | – | – |")
    return "\n".join(["| المسار | الرصيد | منذ البداية | أسوأ تراجع |", "|---|---|---|---|", *rows])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    PB.mkdir(exist_ok=True)
    if a.status:
        print(comparison()); return
    st = load_state()
    sharia = data.load_sharia()
    today = pd.Timestamp(date.today())
    # أسهم يملكها (ب) وليست في قائمة (أ) اليوم ← تُنزَّل هنا (paper_trade.py لا ينزّلها)
    universe_a = set(pure_symbols(sharia, min(today, END)))
    notes = []
    for s in sorted(set(st["holdings"]) - universe_a):
        ok, _, _ = update_raw(s)
        if not ok:
            notes.append(f"فشل تنزيل {s} (مملوك في (ب))")
    universe = sorted(universe_a | set(st["holdings"]))   # نفس قائمة (أ) + ما يملكه (ب)
    raw, _, ksa = load_all(universe)
    counts = pd.Series([d for df in raw.values() for d in df.index]).value_counts()
    days = sorted(counts[counts >= 0.5 * len(raw)].index)
    last = pd.Timestamp(st["last_date"]) if st["last_date"] else None
    todo = [d for d in days if (last is None or d > last) and SIGNAL_START <= d <= END]
    if not todo:
        print("\n".join(notes))
        print("PAPER_ENDED" if last is not None and last >= END else f"(ب): لا يوم تداول جديد بعد {last.date() if last else '-'}")
        return
    log, reps = [], []
    for d in todo:
        prev = [x for x in days if x < d]
        r = process_day(st, raw, ksa, sharia, d, prev[-1] if prev else None, days, log)
        append_csv("equity.csv", [{"date": str(d.date()), "equity": round(r["equity"], 2), "cash": round(r["cash"], 2),
                                   "exposure": round(1 - r["cash"] / r["equity"], 4) if r["equity"] else 0}])
        reps.append(r)
    append_csv("trades.csv", log)
    save_state(st)
    L = []
    for r in reps:
        act = "؛ ".join(r["actions"]) or "لا تنفيذ"
        order = {"in": "دخول السوق بافتتاح الغد", "out": "خروج من السوق بافتتاح الغد", None: "لا شيء"}[r["order"]]
        L.append(f"- {r['date'].date()}: {act} | الرصيد {r['equity']:,.0f} | أمر الغد: {order}")
        L += [f"  - ⚠ {w}" for w in r["warns"]]
    L += [f"- {n}" for n in notes]
    up = "صاعد" if st.get("market_up") else "غير صاعد"
    md = "\n".join([f"# المسار (ب) — {reps[-1]['date'].date()}", "",
                    f"**الحالة:** {'في السوق: ' + str(len(st['holdings'])) + ' سهماً' if st['in_market'] else 'كاش'} — اتجاه السوق (KSA): {up}",
                    "", *L, "", "**المقارنة منذ 2026-10-29:**", "", comparison(), ""])
    (PB / "daily").mkdir(exist_ok=True)
    (PB / "daily" / f"{reps[-1]['date'].date()}.md").write_text(md, encoding="utf-8")
    print(md)
    if reps[-1]["date"] >= END:
        print("PAPER_ENDED — انتهت فترة (ب).")


if __name__ == "__main__":
    main()
