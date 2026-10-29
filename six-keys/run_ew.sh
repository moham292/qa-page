#!/usr/bin/env bash
# نفس التشغيلات الرئيسية لكن المفتاح 3 من المؤشر متساوي الأوزان (معيار المقارنة يبقى KSA)
set -e
cd "$(dirname "$0")"
mkdir -p results
run() { local tag=$1; shift; echo "== $tag ($*)"; python backtest.py --tag "_$tag" "$@" | tee "results/$tag.txt"; mv -f "trades_$tag.csv" "equity_$tag.csv" results/; }
for lb in 125 250; do
  for u in all pure; do
    run ew_lb${lb}_${u}_2016_2017 --market ew --sr-lookback $lb --universe $u --start 2016-01-01 --end 2017-12-31
    run ew_lb${lb}_${u}_2018_now  --market ew --sr-lookback $lb --universe $u --start 2018-01-01
    run ew_lb${lb}_${u}_full      --market ew --sr-lookback $lb --universe $u --start 2016-01-01
  done
done
