#!/bin/bash
# Fetch NBA data and push it to GitHub.
#
# Runs on a residential connection (your Mac). stats.nba.com blackholes cloud
# IPs, so GitHub Actions cannot do this -- the repo is storage only.
#
#   ./scripts/run_and_push.sh pregame
#   ./scripts/run_and_push.sh results
#
# Exits non-zero on failure so launchd records it and the log says why.

set -uo pipefail

MODE="${1:-auto}"

# "auto" lets a single launchd job cover both daily runs: a morning run grades
# last night, an evening run snapshots tonight.
if [ "$MODE" = "auto" ]; then
  if [ "$(date +%H)" -lt 12 ]; then MODE="results"; else MODE="pregame"; fi
  echo "auto -> $MODE"
fi

case "$MODE" in
  pregame|results) ;;
  *) echo "FATAL: mode must be pregame, results or auto (got '$MODE')"; exit 1 ;;
esac

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOGDIR="$REPO/logs/run"
STAMP="$(date +%Y-%m-%d_%H%M%S)"
LOG="$LOGDIR/${STAMP}_${MODE}.log"

mkdir -p "$LOGDIR"
exec > >(tee -a "$LOG") 2>&1

echo "=== $(date) | mode=$MODE | repo=$REPO ==="

cd "$REPO" || { echo "FATAL: cannot cd to $REPO"; exit 1; }

PY="$(command -v python3)"
[ -z "$PY" ] && { echo "FATAL: python3 not found"; exit 1; }

if ! "$PY" -c "import nba_api, pandas" 2>/dev/null; then
  echo "Installing dependencies..."
  "$PY" -m pip install --quiet --user nba_api pandas || {
    echo "FATAL: dependency install failed"; exit 1; }
fi

# Pull first so the push is a fast-forward. Failure here is not fatal; worst
# case the push below is rejected and says so.
git pull --rebase --quiet origin main || echo "WARN: pull failed, continuing"

echo "--- fetching"
"$PY" scripts/fetch_nba_data.py --mode "$MODE" --out data
FETCH_RC=$?

if [ $FETCH_RC -eq 2 ]; then
  echo "FATAL: nothing fetched. See the message above -- usually a blocked IP"
  echo "or stats.nba.com being down. Nothing to push."
  exit 2
elif [ $FETCH_RC -ne 0 ]; then
  echo "WARN: partial fetch (rc=$FETCH_RC). Pushing what we got."
fi

echo "--- committing"
git add data logs
if git diff --staged --quiet; then
  echo "No changes to commit."
  exit $FETCH_RC
fi

git -c user.name="nba-data-bot" -c user.email="$(git config user.email || echo nba-data-bot@local)" \
    commit -q -m "snapshot: $MODE $(date -u +%Y-%m-%d)"

echo "--- pushing"
if git push --quiet origin main; then
  echo "Pushed. $(git log --oneline -1)"
else
  echo "FATAL: push failed. Commit is local only; next run will retry."
  exit 1
fi

echo "=== done $(date) ==="
exit $FETCH_RC
