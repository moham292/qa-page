#!/usr/bin/env bash
# تشغيل مجدول للتداول الورقي للعملات (أربع محافظ). منفصل عن تجربة الأسهم، ويُشغَّل بعدها (الأحد–الخميس)،
# ويعوّض الجمعة والسبت وأي يوم فائت تلقائياً. يرفض العمل إن لم يُحدَّد SIGNAL_START في paper_crypto.py.
#   bash crypto/paper_run.sh          ← ينزّل الأسعار، يعالج الأيام الجديدة، يحفظ ويرفع
#   bash crypto/paper_run.sh status   ← جدول المحافظ الأربع بلا معالجة
set -e
cd "$(dirname "$0")"
BRANCH=claude/eager-cerf-pue70b
python -c "import numpy, pandas, yfinance" 2>/dev/null || python -m pip install -q numpy pandas yfinance >/dev/null 2>&1
python -c "import numpy, pandas, yfinance" || { echo "فشل تثبيت المكتبات"; exit 1; }
export PYTHONWARNINGS=ignore
if [ "$1" = status ]; then python paper_crypto.py --status; exit 0; fi
if ! python paper_crypto.py 2>/tmp/paper_crypto_err.txt; then
  echo "فشل تشغيل العملات — آخر سطور الخطأ:"; tail -15 /tmp/paper_crypto_err.txt; exit 1
fi
git add paper
if ! git diff --cached --quiet; then
  git commit -q -m "Paper trading (crypto): daily update $(date -u +%F)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  pushed=0
  for i in 1 2 3 4; do git push -q origin "$BRANCH" && { pushed=1; break; } || sleep $((2**i)); done
  [ $pushed = 1 ] && echo "(عملات): تم الحفظ والرفع إلى $BRANCH" || { echo "(عملات): فشل الرفع — السجلات محلية فقط"; exit 1; }
else
  echo "(عملات): لا تغييرات للحفظ"
fi
