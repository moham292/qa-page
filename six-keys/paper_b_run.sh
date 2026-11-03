#!/usr/bin/env bash
# تشغيل مجدول للمسار (ب) بعد paper_run.sh daily (يستخدم الأسعار التي نزّلها). منفصل عن تجربة (أ).
#   bash six-keys/paper_b_run.sh          ← يعالج الأيام الجديدة ويحفظ ويرفع
#   bash six-keys/paper_b_run.sh status   ← مقارنة (أ) و(ب) بلا معالجة
set -e
cd "$(dirname "$0")"
BRANCH=claude/eager-cerf-pue70b
export PYTHONWARNINGS=ignore
if [ "$1" = status ]; then python paper_b.py --status; exit 0; fi
if ! python paper_b.py 2>/tmp/paper_b_err.txt; then
  echo "فشل تشغيل (ب) — آخر سطور الخطأ:"; tail -15 /tmp/paper_b_err.txt; exit 1
fi
git add paper_b paper/data/raw
if ! git diff --cached --quiet; then
  git commit -q -m "Paper trading (B): daily update $(date -u +%F)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  pushed=0
  for i in 1 2 3 4; do git push -q origin "$BRANCH" && { pushed=1; break; } || sleep $((2**i)); done
  [ $pushed = 1 ] && echo "(ب): تم الحفظ والرفع إلى $BRANCH" || { echo "(ب): فشل الرفع — السجلات محلية فقط"; exit 1; }
else
  echo "(ب): لا تغييرات للحفظ"
fi
