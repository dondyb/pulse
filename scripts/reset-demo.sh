#!/usr/bin/env sh
# DESTRUCTIVE: deletes every contact, campaign and delivery record (including
# anything you created), purges the delivery queue, then reseeds demo data.
# Never run automatically. Usage: ./scripts/reset-demo.sh [--yes]
set -eu
cd "$(dirname "$0")/.."

if [ "${1:-}" != "--yes" ]; then
  printf 'This permanently deletes ALL Pulse data and reseeds the demo. Type "reset" to continue: '
  read -r answer
  [ "$answer" = "reset" ] || { echo "Aborted."; exit 1; }
fi

docker compose run --rm init python -m app.cli reset --yes
echo "Demo data reset. A new scheduled campaign was created a few minutes from now."
