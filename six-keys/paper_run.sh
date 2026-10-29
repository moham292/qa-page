#!/usr/bin/env bash
# تشغيل مجدول للتداول الورقي: daily أو monthly. يحفظ النتائج في الفرع ويطبع الملخص.
#   bash six-keys/paper_run.sh daily|monthly
set -e
cd "$(dirname "$0")"
BRANCH=claude/eager-cerf-pue70b
git fetch -q origin "$BRANCH"
git checkout -q -B "$BRANCH" "origin/$BRANCH"   # الجلسة الجديدة قد تبدأ على فرع آخر
# نفس مفسّر بايثون الذي يشغّل السكربت (pip وحده قد يثبّت لنسخة أخرى)
python -c "import numpy, pandas, yfinance" 2>/dev/null || python -m pip install -q numpy pandas yfinance >/dev/null 2>&1
python -c "import numpy, pandas, yfinance" || { echo "فشل تثبيت المكتبات"; exit 1; }
export PYTHONWARNINGS=ignore   # تحذيرات المكتبات تملأ المخرجات بلا فائدة
case "$1" in
  daily)   script=paper_trade.py ;;
  monthly) script=paper_report.py ;;
  *) echo "usage: paper_run.sh daily|monthly"; exit 2 ;;
esac
if ! python "$script" 2>/tmp/paper_err.txt; then
  echo "فشل التشغيل — آخر سطور الخطأ:"; tail -15 /tmp/paper_err.txt; exit 1
fi
git add paper
if ! git diff --cached --quiet; then
  git commit -q -m "Paper trading: $1 update $(date -u +%F)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  pushed=0
  for i in 1 2 3 4; do git push -q origin "$BRANCH" && { pushed=1; break; } || sleep $((2**i)); done
  [ $pushed = 1 ] && echo "تم الحفظ والرفع إلى $BRANCH" || { echo "فشل الرفع إلى $BRANCH — السجلات محفوظة محلياً فقط"; exit 1; }
else
  echo "لا تغييرات للحفظ"
fi
