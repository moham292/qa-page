"""المفاتيح الستة — ترجمة قواعد دورة "المهارات الأساسية للاستثمار والمضاربة" إلى كود.

كل الدوال تعمل على بيانات يومية: DataFrame فهرسه التاريخ وأعمدته
Open, High, Low, Close, Volume. القرار يُبنى على إغلاق آخر يوم في البيانات.

ما لم تحدده الدورة بالأرقام مجعول هنا "معاملات" (Params) قابلة للتعديل،
وكل معامل موثق بالمصدر أو بأنه اجتهاد.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class Params:
    # القمة/القاع: شمعة أعلاها (أدناها) هو الأعلى (الأدنى) بين pivot_n شمعة قبلها وبعدها.
    # الدورة: "أقل حاجة شمعتين" والتحديد بالعين — الرقم اجتهاد ويُختبر بعدة قيم.
    pivot_n: int = 3
    # قمتان/قاعان "متساويان تقريباً" لا يصنعان اتجاهاً (محاضرة 6: "القيعان تقريباً متساوية ← عرضي").
    # الفرق المطلوب ليُعتبر أعلى/أدنى — اجتهاد.
    equal_tol: float = 0.01
    # شروط الاختراق (محاضرة 6): يكفي واحد من ثلاثة.
    breakout_pct: float = 0.03          # إغلاق فوق القمة السابقة بـ 3% أو أكثر
    big_candle_body_mult: float = 2.0   # "شمعة كبيرة": جسمها ≥ ضعف متوسط الأجسام (اجتهاد)
    big_candle_vol_mult: float = 1.5    # "حجم تداول مرتفع": ≥ 1.5 × متوسط الحجم (اجتهاد)
    avg_window: int = 20
    # "عند الدعم": السعر فوق مستوى الدعم بما لا يزيد عن هذه النسبة (اجتهاد — لم يُحدد).
    support_tol: float = 0.03
    # المفتاح 5 (محاضرة 7): متوسط متحرك بسيط 55 يوماً.
    sma_len: int = 55
    # المفتاح 6 (محاضرة 7): MACD بالإعدادات الافتراضية.
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    # "state": الخط الأزرق فوق الأحمر الآن — حسمتها محاضرة (8): "حاصل من بدري ولكن ما زال... فهياخد واحد".
    # "event" (تقاطع حديث فقط) مُبقى للمقارنة.
    macd_mode: str = "state"
    macd_event_days: int = 3


# ---------- أدوات أساسية ----------

def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def macd(close: pd.Series, fast=12, slow=26, signal=9):
    ema_f = close.ewm(span=fast, adjust=False).mean()
    ema_s = close.ewm(span=slow, adjust=False).mean()
    line = ema_f - ema_s
    sig = line.ewm(span=signal, adjust=False).mean()
    return line, sig


def pivots(df: pd.DataFrame, n: int):
    """القمم والقيعان المؤكدة: لا تُعرف القمة إلا بعد مرور n شمعة بعدها (بدون نظر للمستقبل)."""
    hi, lo = df["High"].to_numpy(), df["Low"].to_numpy()
    highs, lows = [], []
    for i in range(n, len(df) - n):
        win_h = hi[i - n:i + n + 1]
        win_l = lo[i - n:i + n + 1]
        if hi[i] == win_h.max() and np.argmax(win_h) == n:
            highs.append(i)
        if lo[i] == win_l.min() and np.argmin(win_l) == n:
            lows.append(i)
    return highs, lows


def _confirmed_breakout(df: pd.DataFrame, level: float, start: int, p: Params, up: bool) -> bool:
    """هل تأكد اختراق (أو كسر) المستوى بعد الشمعة start؟ يكفي شرط واحد من الثلاثة."""
    c, o, v = df["Close"].to_numpy(), df["Open"].to_numpy(), df["Volume"].to_numpy()
    body = np.abs(c - o)
    if "_avg_body" in df:  # محسوبة مسبقاً في الاختبار التاريخي للسرعة
        avg_body, avg_vol = df["_avg_body"].to_numpy(), df["_avg_vol"].to_numpy()
    else:
        avg_body = pd.Series(body).rolling(p.avg_window, min_periods=5).mean().to_numpy()
        avg_vol = pd.Series(v).rolling(p.avg_window, min_periods=5).mean().to_numpy()
    for i in range(start + 1, len(df)):
        beyond = c[i] > level if up else c[i] < level
        if not beyond:
            continue
        pct = (c[i] - level) / level if up else (level - c[i]) / level
        if pct >= p.breakout_pct:                                   # الشرط 2
            return True
        direction_ok = c[i] > o[i] if up else c[i] < o[i]
        if (direction_ok and not np.isnan(avg_body[i - 1]) and avg_vol[i - 1] > 0
                and body[i] >= p.big_candle_body_mult * avg_body[i - 1]
                and v[i] >= p.big_candle_vol_mult * avg_vol[i - 1]):  # الشرط 1
            return True
        if i + 1 < len(df):
            nxt = c[i + 1] > level if up else c[i + 1] < level
            if nxt:                                                 # الشرط 3
                return True
    return False


# ---------- المفتاح 1 و 3: الاتجاه ----------

def trend(df: pd.DataFrame, p: Params, piv=None) -> str:
    """صاعد: قاع أعلى من قاع وقمة أعلى من قمة (آخر قمتين وآخر قاعين)، والقمة الأحدث اختُرقت قمتها السابقة باختراق مؤكد.
    هابط: العكس. غير ذلك: عرضي."""
    highs, lows = piv if piv is not None else pivots(df, p.pivot_n)
    if len(highs) < 2 or len(lows) < 2:
        return "غير كافٍ"
    h1, h2 = highs[-2], highs[-1]
    l1, l2 = lows[-2], lows[-1]
    H, L = df["High"].to_numpy(), df["Low"].to_numpy()
    c_last = df["Close"].iloc[-1]

    e = p.equal_tol
    up = L[l2] > L[l1] * (1 + e) and H[h2] > H[h1] * (1 + e)
    down = H[h2] < H[h1] * (1 - e) and L[l2] < L[l1] * (1 - e)

    if up:
        # تأكيد أن القمة الأحدث صنعت اختراقاً مؤكداً للقمة السابقة
        if not _confirmed_breakout(df.iloc[:h2 + p.pivot_n + 1], H[h1], h1, p, up=True):
            return "عرضي"
        # "الاتجاه مستمر إلى أن يثبت العكس": إن كُسر القاع الأخير بكسر مؤكد فلم يعد صاعداً
        if c_last < L[l2] and _confirmed_breakout(df, L[l2], l2, p, up=False):
            return "عرضي"
        return "صاعد"
    if down:
        if not _confirmed_breakout(df.iloc[:l2 + p.pivot_n + 1], L[l1], l1, p, up=False):
            return "عرضي"
        if c_last > H[h2] and _confirmed_breakout(df, H[h2], h2, p, up=True):
            return "عرضي"
        return "هابط"
    return "عرضي"


# ---------- المفتاح 4: الدعم ----------

def support_status(df: pd.DataFrame, p: Params, piv=None) -> tuple[str, float | None]:
    """الدعوم: القيعان المؤكدة + القمم التي اختُرقت (تبادل الأدوار).
    المقاومات: القمم المؤكدة + القيعان التي كُسرت.
    "عند دعم" = السعر فوق أقرب دعم بحد أقصى support_tol، وليس عند مقاومة.
    """
    highs, lows = piv if piv is not None else pivots(df, p.pivot_n)
    H, L = df["High"].to_numpy(), df["Low"].to_numpy()
    c = df["Close"].iloc[-1]
    supports, resistances = [], []
    for i in lows:
        (supports if c >= L[i] else resistances).append(L[i])
    for i in highs:
        (supports if c > H[i] else resistances).append(H[i])
    below = [s for s in supports if s <= c]
    above = [r for r in resistances if r >= c]
    near_s = max(below) if below else None
    near_r = min(above) if above else None
    at_s = near_s is not None and (c - near_s) / near_s <= p.support_tol
    at_r = near_r is not None and (near_r - c) / c <= p.support_tol
    if at_s and not at_r:
        return "دعم", near_s
    if at_r and not at_s:
        return "مقاومة", near_r
    if at_s and at_r:
        return "بين دعم ومقاومة متقاربين", near_s
    return "لا شيء", near_s


# ---------- المفتاحان 5 و 6 ----------

def above_sma(df: pd.DataFrame, p: Params) -> bool:
    """محاضرة (8): العبرة بإغلاق الشمعة فوق المتوسط، والذيل لا يُحتسب،
    و"الشمعة اللي ماشية في النص" (المتوسط يقطع جسمها) تُعتبر تحت المتوسط ← جسم الشمعة كله فوقه."""
    s = sma(df["Close"], p.sma_len)
    if np.isnan(s.iloc[-1]):
        return False
    body_low = min(df["Open"].iloc[-1], df["Close"].iloc[-1])
    return bool(body_low > s.iloc[-1])


def macd_positive(df: pd.DataFrame, p: Params) -> bool:
    line, sig = macd(df["Close"], p.macd_fast, p.macd_slow, p.macd_signal)
    if p.macd_mode == "state":
        return bool(line.iloc[-1] > sig.iloc[-1])
    diff = (line - sig).to_numpy()
    k = p.macd_event_days
    for i in range(len(diff) - k, len(diff)):
        if i > 0 and diff[i - 1] <= 0 < diff[i]:
            return diff[-1] > 0
    return False


def macd_negative_cross(df: pd.DataFrame, p: Params) -> bool:
    """قاعدة الخروج الوحيدة في الدورة: الخط الأزرق ينزل تحت الأحمر."""
    line, sig = macd(df["Close"], p.macd_fast, p.macd_slow, p.macd_signal)
    d = (line - sig).to_numpy()
    return len(d) > 1 and d[-2] >= 0 > d[-1]


# ---------- التقييم الكامل ----------

@dataclass
class Evaluation:
    trend: str
    profitable: bool | None
    market_trend: str
    sr: str
    sr_level: float | None
    above_sma55: bool
    macd_pos: bool
    keys: list[int] = field(default_factory=list)

    @property
    def score(self) -> int:
        return sum(self.keys)


def evaluate(stock: pd.DataFrame, tasi: pd.DataFrame, net_income_positive: bool | None,
             p: Params = Params()) -> Evaluation:
    t = trend(stock, p)
    mt = trend(tasi, p)
    sr, lvl = support_status(stock, p)
    a = above_sma(stock, p)
    m = macd_positive(stock, p)
    keys = [
        int(t == "صاعد"),
        int(bool(net_income_positive)),
        int(mt == "صاعد"),
        int(sr == "دعم"),
        int(a),
        int(m),
    ]
    return Evaluation(t, net_income_positive, mt, sr, lvl, a, m, keys)
