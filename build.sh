#!/usr/bin/env bash
# Render build step: install, collect static files, migrate, seed.
set -o errexit
set -o pipefail

pip install --upgrade pip
pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate --no-input

# Real College Scorecard data (#24/#32). Render's free plan has no Shell, so
# the import runs here. It reads the CSVs committed under core/data (no
# network) and is idempotent, but upserting ~68k rows takes a while, so it runs
# only when the database has just the seed sample, or when
# FORCE_SCORECARD_IMPORT=1 is set in Render (after the snapshot changes).
if python manage.py help import_scorecard >/dev/null 2>&1; then
  if [ "${FORCE_SCORECARD_IMPORT:-0}" = "1" ] || python manage.py shell -c "import sys; from core.models import Institution; sys.exit(0 if Institution.objects.count() < 100 else 1)"; then
    python manage.py import_scorecard
  else
    echo "Scorecard data already imported; skipping (set FORCE_SCORECARD_IMPORT=1 to re-import)."
  fi
fi

# D's seed command (grader accounts + demo data). It must be safe to run on
# every deploy. Skipped until the command exists.
if python manage.py help seed >/dev/null 2>&1; then
  python manage.py seed
else
  echo "No seed command yet; skipping."
fi
