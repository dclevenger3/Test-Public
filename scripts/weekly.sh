#!/usr/bin/env bash
# Run the whole weekly cycle. Schedule with cron, e.g. Sundays at 6pm:
#   0 18 * * 0 /path/to/school-planner/scripts/weekly.sh
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -d .venv ]; then source .venv/bin/activate; fi
school-planner weekly "$@"
open "data/outbox/week-$(date +%F)" 2>/dev/null || xdg-open "data/outbox/week-$(date +%F)" 2>/dev/null || true
