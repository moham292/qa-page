#!/usr/bin/env bash
# يشغّل نسخ الاختبار التاريخي ويحفظ كل نتيجة في results/
set -e
cd "$(dirname "$0")"
mkdir -p results
run() { local tag=$1; shift; echo "== $tag ($*)"; python backtest.py --tag "_$tag" "$@" | tee "results/$tag.txt"; mv -f "trades_$tag.csv" "equity_$tag.csv" results/; }
run full      --start 2016-01-01
run full_five --start 2016-01-01 --allow-five
run p2016_2020 --start 2016-01-01 --end 2020-12-31
run p2021_now  --start 2021-01-01
