#!/usr/bin/env bash
# يشغّل نسخ الاختبار التاريخي ويحفظ كل نتيجة في results/
#   نافذة الدعم/المقاومة (125 = 6 أشهر، 250 = سنة) × (كل السوق، النقية فقط) × الفترات
#   + النقية بسريان صارم من تاريخ نشر القائمة
set -e
cd "$(dirname "$0")"
mkdir -p results
run() { local tag=$1; shift; echo "== $tag ($*)"; python backtest.py --tag "_$tag" "$@" | tee "results/$tag.txt"; mv -f "trades_$tag.csv" "equity_$tag.csv" results/; }
for lb in 125 250; do
  for u in all pure; do
    run lb${lb}_${u}_2016_2017 --sr-lookback $lb --universe $u --start 2016-01-01 --end 2017-12-31
    run lb${lb}_${u}_2018_now  --sr-lookback $lb --universe $u --start 2018-01-01
    run lb${lb}_${u}_full      --sr-lookback $lb --universe $u --start 2016-01-01
    run lb${lb}_${u}_full_five --sr-lookback $lb --universe $u --start 2016-01-01 --allow-five
  done
  run lb${lb}_pure_2016_2017_strict --sr-lookback $lb --universe pure --strict-sharia --start 2016-01-01 --end 2017-12-31
  run lb${lb}_pure_full_strict      --sr-lookback $lb --universe pure --strict-sharia --start 2016-01-01
done
