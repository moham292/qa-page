"""الاختبار التاريخي للعملات: (أ) المفاتيح، (ب) الضابط، والمعياران — لكل قائمة على حدة. القواعد في CRYPTO_RULES.md.

يعيد استخدام دوال six-keys كما هي (signals/simulate/trend_series من backtest.py، run_b من control_b/run_b.py،
net_curve/rebalanced/stats من final_checks.py، match_weight/blend من dd_match/cash_yield) مع توجيه
مسارات الملفات والعمولة إلى قيم العملات بإسناد متغيرات الوحدات وقت التشغيل (لا يُعدَّل أي ملف في six-keys).
  python crypto/backtest_crypto.py   ← crypto/results/*
"""
from __future__ import annotations

import sys
from dataclasses import asdict

import numpy as np
import pandas as pd

import common
from common import COST, HERE, LIST_NAMES, LISTS, MARKET, PARAMS, START, WARMUP, clean, load_csv

sys.path.insert(0, str(common.SIX / "control_b"))
import run_b as rb          # noqa: E402  (يقرأ ملفاً من six-keys/results عند الاستيراد — قراءة فقط)
import cash_yield as cy     # noqa: E402
import dd_match as ddm      # noqa: E402
import final_checks as fc   # noqa: E402
from backtest import signals, simulate, trend_series  # noqa: E402

RES = HERE / "results"
RES.mkdir(exist_ok=True)
# توجيه الوحدات المستوردة: الملفات إلى crypto/results والعمولة 0.1%
fc.R = cy.R = rb.R = RES
rb.COST = ddm.COST = COST
stats, md_table, rebalanced, yearly = fc.stats, fc.md_table, fc.rebalanced, rb.yearly


def load_all():
    return {s: clean(load_csv(HERE / "data" / f"{s}.csv")) for s in {x for v in LISTS.values() for x in v} | {MARKET}}


def market_up(btc: pd.DataFrame) -> pd.Series:
    """المفتاح 3: اتجاه BTC-USD بنفس الدالة، على إغلاق نفس اليوم (بلا تأخير)."""
    return trend_series(btc, PARAMS) == "صاعد"


def make_pick(closes_full: pd.DataFrame):
    hist = closes_full.notna().cumsum()

    def pick(d):   # نفس pure_on بلا الفلتر الشرعي: سعر في آخر 5 أيام، و60 يوم بيانات قبل يوم الإشارة
        prev = closes_full.index[closes_full.index < d]
        if not len(prev):
            return []
        ok = closes_full.loc[prev[-5:]].notna().any() & (hist.loc[prev[-1]] >= WARMUP)
        return ok.index[ok].tolist()
    return pick


def episodes(eq: pd.Series, inv: pd.Series) -> list[dict]:
    """فترات وجود (ب) في السوق كـ«صفقات»: العائد من قيمة المحفظة قبل الدخول إلى قيمتها في آخر يوم (شاملاً العمولات)."""
    on = (inv > 0.01).to_numpy()
    out, i = [], 0
    while i < len(on):
        if on[i]:
            j = i
            while j + 1 < len(on) and on[j + 1]:
                j += 1
            start = eq.iloc[i - 1] if i else eq.iloc[0]
            k = min(j + 1, len(eq) - 1)        # يوم الخروج (بافتتاحه) ضمن الصفقة
            seg = eq.iloc[i:k + 1]
            out.append({"ret": seg.iloc[-1] / start - 1, "dd": float((seg / start).min() - 1)})
            i = j + 1
        else:
            i += 1
    return out


def run_list(key: str, prices: dict, up: pd.Series) -> dict:
    syms = LISTS[key]
    tag = f"{key}_A"
    # (أ) المفاتيح
    sigs = {s: signals(s, prices[s], up, None, None, PARAMS, warmup=WARMUP) for s in syms}
    sigs = {s: x.loc[START:] for s, x in sigs.items()}
    sigs = {s: x for s, x in sigs.items() if len(x)}
    px = {s: prices[s] for s in syms}
    eq, trades = simulate(sigs, px, allow_five=False)
    pd.DataFrame([asdict(t) for t in trades]).to_csv(RES / f"trades_{tag}.csv", index=False, encoding="utf-8-sig")
    eq.to_csv(RES / f"equity_{tag}.csv", header=["equity"])
    closes_full = pd.DataFrame({s: prices[s]["Close"] for s in syms})
    netA, cashA, infoA = rb.b125_info(tag, closes_full)
    # أوامر دخول سقطت لغياب سعر يوم التنفيذ (simulate يُسقطها بدل تعليقها)
    dropped = []
    for s, x in sigs.items():
        for d in x.index[x["score"] == 6]:
            nd = d + pd.Timedelta(days=1)
            if nd <= eq.index[-1] and nd not in prices[s].index:
                dropped.append(f"{s} {d.date()}")
    # (ب) الضابط
    c = closes_full.loc[START:]
    c = c.reindex(pd.date_range(c.index[0], c.index[-1], freq="D"))
    o = pd.DataFrame({s: prices[s]["Open"] for s in syms}).reindex(c.index)
    upB = up.reindex(up.index.union(c.index)).ffill().fillna(False).astype(bool).reindex(c.index)
    pick = make_pick(closes_full.reindex(pd.date_range(closes_full.index[0], c.index[-1], freq="D")))
    B, bi = rb.run_b(o, c, upB, pick, 0.0)
    B.to_csv(RES / f"equity_{key}_B.csv", header=["equity"])
    # المعياران
    basket, _ = rebalanced(c, pick, "M", COST)
    basket = pd.concat([pd.Series([1.0], index=[c.index[0]]), basket])
    btc = prices[MARKET]["Close"].loc[START:]
    btc = btc / btc.iloc[0] * (1 - COST)
    btc.iloc[0] = 1.0
    return {"A": netA, "cashA": cashA, "infoA": infoA, "trades": trades, "dropped": dropped,
            "B": B, "bi": bi, "basket": basket, "btc": btc, "sigs": sigs}


def pct(x):
    return f"{x:+.1%}"


def report(key: str, r: dict) -> tuple[list[str], dict]:
    A, B, tr, bi, ia = r["A"], r["B"], r["trades"], r["bi"], r["infoA"]
    L = [f"## القائمة {LIST_NAMES[key]}: {'، '.join(LISTS[key])}", "",
         f"الفترة: {A.index[0].date()} ← {A.index[-1].date()}. كل الأرقام بعد العمولات ({COST:.1%} لكل جهة)، الكاش بلا عائد.", ""]
    # 1) الجدول الموحد
    ra = np.array([(1 + t.ret) * (1 - COST) ** 2 - 1 for t in tr])
    dda = np.array([t.max_drawdown for t in tr])
    n_open = sum(t.exit_date is None for t in tr)
    epi = episodes(B, bi["inv"])
    rbE = np.array([e["ret"] for e in epi]); ddb = np.array([e["dd"] for e in epi])
    rows = []
    def row(name, s, time_in, avg_inv, ntr, win, avg, wdd, comm):
        st = stats(s)
        rows.append([name, pct(st["العائد"]), f"{st['سنوياً']:+.1%}", f"{st['أسوأ تراجع']:.1%}", time_in, avg_inv,
                     ntr, win, avg, wdd, comm])
    row("(أ) المفاتيح", A, f"{ia['time_in']:.0%}", f"{ia['avg_inv']:.0%}",
        f"{len(tr)}" + (f" ({n_open} مفتوحة)" if n_open else ""), f"{(ra > 0).mean():.0%}", f"{ra.mean():+.1%}",
        f"{dda.min():.1%}", f"{ia['comm']:.1%}")
    row("(ب) الضابط", B, f"{(bi['inv'] > 0.01).mean():.0%}", f"{bi['inv'].mean():.0%}",
        f"{bi['entries']} دخول / {bi['exits']} خروج", f"{(rbE > 0).mean():.0%}", f"{rbE.mean():+.1%}",
        f"{ddb.min():.1%}", f"{bi['comm']:.1%}")
    row("سلة القائمة (شراء واحتفاظ، توازن شهري)", r["basket"], "100%", "100%", "–", "–", "–", "–", "≈ضئيلة")
    row("BTC (شراء واحتفاظ)", r["btc"], "100%", "100%", "1", "–", "–", "–", f"{COST:.1%}")
    L += ["### 1. الجدول الموحد", "",
          "«الوقت في السوق» = نسبة الأيام بأي استثمار. «متوسط الاستثمار» = متوسط نسبة المحفظة خارج الكاش. "
          "صفقات (أ) لكل عملة؛ «صفقات» (ب) = فترات وجود المحفظة كاملة في السوق. متوسط الصفقة ونسبة الرابحة بعد العمولة. "
          "«أسوأ نزول داخل صفقة» في (أ) من سعر الدخول إلى أدنى سعر (Low)، وفي (ب) من قيمة المحفظة قبل الدخول إلى أدنى إغلاق خلال الفترة. "
          "العمولات = مجموع ما دُفع كنسبة من رأس المال الابتدائي.", "",
          md_table(["المحفظة", "العائد الكلي", "سنوياً", "أسوأ تراجع", "الوقت في السوق", "متوسط الاستثمار",
                    "الصفقات", "الرابحة", "متوسط الصفقة", "أسوأ نزول داخل صفقة", "العمولات"], rows), "",
          f"(ب): {bi['rebal']} إعادة توازن شهرية إضافة إلى الدخول.", ""]
    # 2) تساوي التراجع
    mA = stats(A)
    w, bst = ddm.match_weight(B, 0.0, mA["أسوأ تراجع"])
    mix = cy.blend(B, 0.0, w, COST)
    diff = mA["سنوياً"] - bst["سنوياً"]
    L += ["### 2. (أ) مقابل (ب) عند تساوي التراجع (طريقة dd_match)", "",
          "الخليط = w × (ب) + (1−w) × كاش بلا عائد، توازن شهري، عمولة على المنقول. w بحيث يساوي تراجع الخليط تراجع (أ)، بحد أعلى 100% (بلا رافعة).", "",
          md_table(["تراجع (أ)", "تراجع (ب) كاملاً", "w في (ب)", "تراجع الخليط", "(أ) سنوياً", "الخليط سنوياً", "فرق (أ)"],
                   [[f"{mA['أسوأ تراجع']:.1%}", f"{stats(B)['أسوأ تراجع']:.1%}", f"{w:.0%}", f"{bst['أسوأ تراجع']:.1%}",
                     f"{mA['سنوياً']:+.2%}", f"{bst['سنوياً']:+.2%}", f"{diff:+.2%}"]]), ""]
    # 3) سنة بسنة
    yA, yB, yM, yK, yC = (yearly(s) for s in (A, B, mix, r["basket"], r["btc"]))
    rows, wins = [], 0
    for y in yA.index:
        d = yA[y] - yM[y]; wins += d > 0
        rows.append([str(y) + (" (جزئية)" if y == A.index[-1].year else ""), pct(yA[y]), pct(yB[y]), pct(yM[y]),
                     f"{d:+.1%}", "(أ)" if d > 0 else "(ب)", pct(yK[y]), pct(yC[y])])
    L += ["### 3. سنة بسنة", "", f"«(ب) مطابق» = خليط (ب) بنفس تراجع (أ) (w = {w:.0%}).", "",
          md_table(["السنة", "(أ)", "(ب) كاملاً", "(ب) مطابق", "فرق (أ)", "الأعلى", "السلة", "BTC"], rows), "",
          f"(أ) أعلى من (ب) المطابق في {wins} من {len(yA)} سنة.", ""]
    if diff <= 0:
        lab = "لا تضيف"
    elif diff >= 0.02 and wins > len(yA) / 2:
        lab = "المفاتيح تضيف قيمة في العملات"
    else:
        lab = "غير حاسمة"
    if r["dropped"]:
        L += [f"أوامر دخول 6/6 لم تُنفّذ لغياب شمعة يوم التنفيذ (simulate يُسقطها): {'، '.join(r['dropped'])}", ""]
    else:
        L += ["لا توجد أوامر دخول سقطت لغياب شمعة يوم التنفيذ.", ""]
    return L, {"diff": diff, "wins": int(wins), "years": len(yA), "label": lab, "w": w}


if __name__ == "__main__":
    prices = load_all()
    up = market_up(prices[MARKET])
    up.to_csv(RES / "btc_up.csv", header=["up"])
    out = ["# نتائج الاختبار التاريخي للعملات (مولَّدة آلياً)", ""]
    verdicts = {}
    for key in LISTS:
        r = run_list(key, prices, up)
        L, v = report(key, r)
        verdicts[key] = v
        out += L
        print("\n".join(L), flush=True)
    v = verdicts["core"]
    out += ["## تطبيق معيار الحكم المثبت (القائمة الأساسية فقط)", "",
            f"فرق (أ) على (ب) المطابق: {v['diff']:+.2%} سنوياً؛ (أ) أعلى في {v['wins']}/{v['years']} سنة ← **{v['label']}**", "",
            f"للاطلاع فقط (لا حكم عليها): الملحق فرق {verdicts['ext']['diff']:+.2%}، (أ) أعلى في "
            f"{verdicts['ext']['wins']}/{verdicts['ext']['years']} سنة ← بنفس المعيار: {verdicts['ext']['label']}", ""]
    (RES / "results.md").write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out[-5:]))
