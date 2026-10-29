# سجل التقدم (جلسة 2026-10-29)

## المرحلة 1 — البيئة والرموز ✓
- الاختبارات: 11/11 ناجحة.
- Yahoo يعمل من هذه البيئة عبر `yfinance` (نقطة chart)، لكن `.info` محجوب (401، بلا crumb). الأسماء أُخذت من `history_metadata`.
- **الرموز العشرة كلها صحيحة:**

| الرمز | الاسم في Yahoo | أول يوم |
|---|---|---|
| 1120 | Al Rajhi Banking and Investment Corporation | 2010-03-03 |
| 4030 | The National Shipping Company of Saudi Arabia (البحري) | 2010-03-04 |
| 1140 | Bank Albilad | 2010-03-04 |
| 4200 | Aldrees Petroleum and Transport Services | 2010-03-04 |
| 1810 | Seera Holding Group | 2012-06-10 |
| 4050 | Saudi Automotive Services Company (ساسكو) | 2010-03-04 |
| 4300 | Dar Al Arkan Real Estate Development | 2010-03-04 |
| 2382 | ADES Holding Company | 2023-10-19 |
| 1211 | Saudi Arabian Mining Company (Maaden) | 2010-03-03 |
| 4162 | Almunajem Foods Company | 2021-12-21 |

- **مشكلة: مؤشر تاسي (`^TASI.SR`) في Yahoo يعيد يوماً واحداً فقط** (جُرّب 1d/1wk/1mo و period=max). موقع تداول وstooq وKaggle محجوبة من الشبكة.
