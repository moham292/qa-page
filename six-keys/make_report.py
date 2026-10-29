"""يجمع ملفات results/*.txt في جداول مقارنة: results/summary.md"""
from __future__ import annotations

import re
from pathlib import Path

R = Path(__file__).parent / "results"


def parse(f: Path) -> dict:
    d = {}
    for line in f.read_text(encoding="utf-8").splitlines():
        if ": " in line:
            k, v = line.split(": ", 1)
            d[k.strip()] = v.strip()
    return d


def pct(s: str | None) -> str:
    if not s:
        return "–"
    m = re.match(r"(-?[\d.]+%)(?: \(سنوياً (-?[\d.]+%)\))?", s)
    return f"{m.group(1)} ({m.group(2)}/سنة)" if m and m.group(2) else (m.group(1) if m else s)


def row(tag: str) -> list[str] | None:
    f = R / f"{tag}.txt"
    if not f.exists():
        return None
    d = parse(f)
    bench = next((v for k, v in d.items() if k.startswith("عائد KSA") or k.startswith("عائد تاسي")), None)
    ew = d.get("عائد كل الأسهم بأوزان متساوية", "")
    n = d.get("عدد الصفقات", "0").split()[0]
    warn = " ⚠" if int(n) < 30 else ""
    return [pct(d.get("عائد المحفظة")), pct(bench), pct(ew.split("،")[0]) if ew else "–",
            d.get("أسوأ تراجع للمحفظة", "–"), n + warn, d.get("نسبة الصفقات الرابحة", "–"),
            d.get("متوسط عائد الصفقة", "–"), d.get("أسوأ نزول داخل صفقة (بلا وقف خسارة)", "–"),
            d.get("متوسط نسبة الاستثمار (الباقي كاش)", "–").split(" —")[0]]


HEAD = ["التشغيل", "المحفظة", "KSA", "سلة متساوية", "أسوأ تراجع", "الصفقات", "الرابحة", "متوسط الصفقة",
        "أسوأ نزول داخل صفقة", "متوسط الاستثمار"]


def table(title: str, tags: list[tuple[str, str]]) -> str:
    lines = [f"### {title}", "", "| " + " | ".join(HEAD) + " |", "|" + "---|" * len(HEAD)]
    for label, tag in tags:
        r = row(tag)
        if r:
            lines.append("| " + " | ".join([label, *r]) + " |")
    return "\n".join(lines) + "\n"


CFG = {"A125": "pivot_n 3، نافذة الدعم 125 يوماً (6 أشهر)", "A250": "pivot_n 3، نافذة الدعم 250 يوماً (سنة)",
       "B125": "pivot_n 8، دعم 5%، نافذة 125 يوماً (الأعلى تطابقاً 9/11)"}
UNI = {"all": "كل السوق", "pure": "النقية", "strict": "النقية (سريان صارم)"}
PER = {"2016_2017": "2016–2017", "2018_now": "2018–اليوم", "full": "2016–اليوم", "full_five": "2016–اليوم + 5/6"}


if __name__ == "__main__":
    out = ["# ملخص الاختبار التاريخي", "",
           "⚠ = أقل من 30 صفقة: لا يكفي للحكم. «سلة متساوية» = متوسط الأسهم المسموحة في نفس التشغيل (كل السوق أو النقية)، "
           "أوزان متساوية بإعادة توازن يومية. «KSA» = صندوق iShares MSCI Saudi Arabia (شامل التوزيعات).", ""]
    for mk, mn in (("ksa", "المفتاح 3 من KSA"), ("ew", "المفتاح 3 من المؤشر متساوي الأوزان")):
        for cfg, cn in CFG.items():
            tags = [(f"{un} {pn}", f"{mk}_{cfg}_{u}_{per}") for u, un in UNI.items() for per, pn in PER.items()]
            out.append(table(f"{mn} — {cn}", tags))
    (R / "summary.md").write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))
