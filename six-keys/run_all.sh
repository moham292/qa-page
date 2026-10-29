#!/usr/bin/env bash
# كل تشغيلات الاختبار التاريخي، 3 مجموعات بالتوازي. كل مجموعة = (تركيبة، مؤشر السوق، الأسهم) تشغّل فتراتها
# بالتتابع لتستفيد من ذاكرة الإشارات المؤقتة. النتائج في results/<الوسم>.txt
#   التركيبات: A125 = pivot_n 3 نافذة 125 | A250 = pivot_n 3 نافذة 250 | B125 = pivot_n 8 دعم 5% نافذة 125
cd "$(dirname "$0")"
mkdir -p results
group() {  # cfg market universe
  local cfg=$1 mk=$2 u=$3 args
  case $cfg in
    A125) args="--pivot-n 3 --support-tol 0.03 --sr-lookback 125";;
    A250) args="--pivot-n 3 --support-tol 0.03 --sr-lookback 250";;
    B125) args="--pivot-n 8 --support-tol 0.05 --sr-lookback 125";;
  esac
  local uargs="--universe $u" ut=$u
  [ "$u" = strict ] && uargs="--universe pure --strict-sharia"
  local pers="2016_2017 2018_now full"
  [ "$mk" = ksa ] && [ "$u" != strict ] && pers="$pers full_five"
  [ "$u" = strict ] && pers="2016_2017 full"
  for per in $pers; do
    local pa
    case $per in
      2016_2017) pa="--start 2016-01-01 --end 2017-12-31";;
      2018_now)  pa="--start 2018-01-01";;
      full)      pa="--start 2016-01-01";;
      full_five) pa="--start 2016-01-01 --allow-five";;
    esac
    local tag=${mk}_${cfg}_${ut}_${per}
    python backtest.py --tag "_$tag" --market $mk $args $uargs $pa > "results/$tag.txt" 2>&1 \
      && mv -f "trades_$tag.csv" "equity_$tag.csv" results/ && echo "done $tag" || echo "FAILED $tag"
  done
}
export -f group
for cfg in A125 A250 B125; do for mk in ksa ew; do for u in all pure strict; do echo "$cfg $mk $u"; done; done; done \
  | xargs -P 3 -L 1 bash -c 'group "$0" "$1" "$2"'
echo ALL_DONE
