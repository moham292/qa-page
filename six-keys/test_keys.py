"""اختبارات منطق المفاتيح على بيانات مصطنعة ذات شكل معروف (ليست نتائج سوق)."""
import numpy as np
import pandas as pd

from keys import Params, macd_negative_cross, pivots, support_status, trend, above_sma, macd_positive


def make(closes, vol=1_000_000, wick=0.003):
    c = np.asarray(closes, dtype=float)
    o = np.r_[c[0], c[:-1]]
    hi = np.maximum(o, c) * (1 + wick)
    lo = np.minimum(o, c) * (1 - wick)
    idx = pd.bdate_range("2023-01-01", periods=len(c))
    return pd.DataFrame({"Open": o, "High": hi, "Low": lo, "Close": c, "Volume": vol}, index=idx)


def zigzag(points, steps=8):
    out = []
    for a, b in zip(points[:-1], points[1:]):
        out += list(np.linspace(a, b, steps, endpoint=False))
    out.append(points[-1])
    return out


P = Params(pivot_n=3)


def test_uptrend_staircase():
    # قاع 100، قمة 110، قاع 104، قمة 120 (اختراق > 3%)، قاع 112، ثم صعود
    df = make(zigzag([100, 110, 104, 120, 112, 118]))
    assert trend(df, P) == "صاعد"


def test_downtrend():
    df = make(zigzag([120, 110, 116, 100, 108, 102]))
    assert trend(df, P) == "هابط"


def test_sideways_equal_lows():
    # قمة أعلى لكن قاع مساوٍ ← عرضي (مثال خالد في المحاضرة 6)
    df = make(zigzag([100, 110, 100, 115, 100.2, 105]))
    assert trend(df, P) == "عرضي"


def test_weak_breakout_not_confirmed():
    # القمة الثانية أعلى بـ 1% فقط وبدون إغلاق ثانٍ فوقها ← لا يُعتبر صاعداً
    seq = zigzag([100, 110, 104, 111.1], steps=8)
    seq += [109, 106, 105, 107, 108]          # رجوع فوري تحت 110
    df = make(seq)
    assert trend(df, P) != "صاعد"


def test_support_after_pullback():
    df = make(zigzag([100, 110, 104, 120, 112, 113.5]))
    status, lvl = support_status(df, P)
    assert status == "دعم", (status, lvl)


def test_resistance_near_previous_high():
    df = make(zigzag([100, 110, 104, 120, 112, 119]))
    assert support_status(df, P)[0] == "مقاومة"


def test_role_reversal_broken_high_is_support():
    # القمة 110 اختُرقت، والسعر رجع قربها ← دعم
    df = make(zigzag([100, 110, 104, 118, 111]))
    status, lvl = support_status(df, P)
    assert status == "دعم" and abs(lvl - 110 * 1.003) < 1.5, (status, lvl)


def test_sma_and_macd():
    up = make(np.linspace(50, 100, 120))
    assert above_sma(up, P) and macd_positive(up, P)
    down = make(np.linspace(100, 50, 120))
    assert not above_sma(down, P) and not macd_positive(down, P)


def test_macd_negative_cross_detected_once():
    seq = list(np.linspace(50, 100, 80)) + list(np.linspace(100, 80, 40))
    df = make(seq)
    hits = [macd_negative_cross(df.iloc[:i], P) for i in range(30, len(df) + 1)]
    assert sum(hits) == 1


def test_pivots_no_lookahead():
    df = make(zigzag([100, 110, 104, 120, 112, 118]))
    full_h, full_l = pivots(df, 3)
    t = 30
    part_h, part_l = pivots(df.iloc[:t + 1], 3)
    assert [i for i in full_h if i + 3 <= t] == part_h
    assert [i for i in full_l if i + 3 <= t] == part_l


def test_candle_straddling_sma_counts_as_below():
    df = make(np.linspace(50, 100, 120))
    s = df["Close"].rolling(55).mean().iloc[-1]
    df.iloc[-1, df.columns.get_loc("Open")] = s * 0.99   # يفتح تحت المتوسط
    df.iloc[-1, df.columns.get_loc("Close")] = s * 1.02  # ويغلق فوقه
    assert not above_sma(df, P)
