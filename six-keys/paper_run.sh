#!/usr/bin/env bash
# تشغيل مجدول للتداول الورقي: daily أو monthly. يحفظ النتائج في الفرع ويطبع الملخص.
#   bash six-keys/paper_run.sh daily|monthly
set -e
cd "$(dirname "$0")"
BRANCH=claude/eager-cerf-pue70b
git fetch -q origin "$BRANCH" && git checkout -q "$BRANCH" && git pull -q --ff-only origin "$BRANCH"
python -c "import pandas, yfinance" 2>/dev/null || pip install -q pandas numpy yfinance >/dev/null 2>&1
case "$1" in
  daily)   python paper_trade.py | tee /tmp/paper_out.txt ;;
  monthly) python paper_report.py | tee /tmp/paper_out.txt ;;
  *) echo "usage: paper_run.sh daily|monthly"; exit 2 ;;
esac
git add paper
if ! git diff --cached --quiet; then
  git commit -q -m "Paper trading: $1 update $(date -u +%F)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  for i in 1 2 3 4; do git push -q origin "$BRANCH" && break || sleep $((2**i)); done
fi
