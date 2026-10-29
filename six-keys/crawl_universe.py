"""بناء قائمة أسهم السوق الرئيسية من Yahoo بفحص نطاقات رموز تداول، وتنزيل تاريخ كل رمز موجود.

لماذا الفحص: مواقع القوائم (تداول، stockanalysis، ...) محجوبة في بيئة التشغيل، وYahoo وحده متاح.
نومو (الرموز 9xxx) مستبعد عمداً. طلب واحد لكل رمز، مع انتظار عند حد الطلبات، واستئناف من حيث توقف.

  python crawl_universe.py            # يكتب data/prices/<الرمز>.csv و data/universe.csv
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

import yfinance as yf
from yfinance.exceptions import YFRateLimitError

logging.getLogger("yfinance").setLevel(logging.CRITICAL)
yf.config.debug.hide_exceptions = False

ROOT = Path(__file__).parent / "data"
OUT = ROOT / "prices"
STATE = ROOT / "crawl_state.json"
RANGES = [(1010, 1835), (2001, 2400), (3001, 3100), (4001, 4350), (5110, 5110),
          (6001, 6100), (7010, 7250), (8010, 8320)]


def main(start: str = "2015-01-01") -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    state = json.loads(STATE.read_text()) if STATE.exists() else {"done": [], "names": {}}
    done = set(state["done"])
    for c in (c for a, b in RANGES for c in range(a, b + 1)):
        if c in done:
            continue
        h = None
        for attempt in range(8):
            try:
                t = yf.Ticker(f"{c}.SR")
                h = t.history(start=start, auto_adjust=True)
                break
            except Exception as e:
                if not (isinstance(e, YFRateLimitError) or "Rate" in str(e) or "429" in str(e)):
                    break  # رمز غير موجود
                print(f"حد الطلبات عند {c} — انتظار", flush=True)
                time.sleep(60 * (attempt + 1))
        else:
            sys.exit(f"توقف عند {c}: حد الطلبات مستمر")
        if h is not None and len(h):
            h.index = h.index.tz_localize(None)
            h.index.name = "Date"
            h[["Open", "High", "Low", "Close", "Volume"]].to_csv(OUT / f"{c}.csv")
            m = t.history_metadata
            state["names"][str(c)] = m.get("longName") or m.get("shortName")
            print(c, len(h), state["names"][str(c)], flush=True)
            time.sleep(0.7)  # الرمز غير الموجود يستغرق ~1.3 ثانية بذاته
        state["done"].append(c)
        done.add(c)
        STATE.write_text(json.dumps(state, ensure_ascii=False))
    rows = "\n".join(f'{k},"{v}"' for k, v in sorted(state["names"].items()))
    (ROOT / "universe.csv").write_text("symbol,name\n" + rows + "\n", encoding="utf-8")
    print("انتهى:", len(state["names"]), "رمزاً", flush=True)


if __name__ == "__main__":
    main()
