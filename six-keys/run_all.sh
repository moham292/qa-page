#!/usr/bin/env bash
# يشغّل نسخ الاختبار التاريخي ويحفظ كل نتيجة في results/
#   كل السوق مقابل النقية فقط × فترتان (2016–2017 هبوط، 2018 حتى اليوم) + الفترة كاملة + استثناء 5/6
set -e
cd "$(dirname "$0")"
mkdir -p results
run() { local tag=$1; shift; echo "== $tag ($*)"; python backtest.py --tag "_$tag" "$@" | tee "results/$tag.txt"; mv -f "trades_$tag.csv" "equity_$tag.csv" results/; }
for u in all pure; do
  run ${u}_2016_2017 --universe $u --start 2016-01-01 --end 2017-12-31
  run ${u}_2018_now  --universe $u --start 2018-01-01
  run ${u}_full      --universe $u --start 2016-01-01
  run ${u}_full_five --universe $u --start 2016-01-01 --allow-five
done
run pure_2016_2017_strict --universe pure --strict-sharia --start 2016-01-01 --end 2017-12-31
run pure_full_strict --universe pure --strict-sharia --start 2016-01-01
