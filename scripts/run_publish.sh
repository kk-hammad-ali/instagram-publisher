#!/usr/bin/env bash
# Wrapper invoked by launchd. launchd does not read .env, so this sources it,
# then runs the publisher and appends to a rotating log.
#
# Failures are deliberately not recorded as published, so the next run (two
# minutes later) retries automatically. publish.py's 3-hour grace window bounds
# that: a post keeps being retried for three hours, then is skipped rather than
# fired absurdly late.

set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

mkdir -p state
LOG="state/publish.log"

# Keep the log from growing without bound on a machine that runs this every
# two minutes forever.
if [ -f "$LOG" ] && [ "$(wc -c < "$LOG")" -gt 2000000 ]; then
  mv "$LOG" "$LOG.1"
fi

out="$(/usr/bin/env python3 scripts/publish.py 2>&1)"
code=$?

# Only log runs that did something or failed. "nothing due" fires ~720 times a
# day and would bury the entries that matter.
if [ $code -ne 0 ] || ! printf '%s' "$out" | grep -q '^nothing due'; then
  printf '[%s] %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$out" >> "$LOG"
fi

exit $code
