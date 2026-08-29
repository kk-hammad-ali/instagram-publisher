#!/usr/bin/env bash
# Wrapper invoked by launchd, three times a day. Mirrors ONE already-published
# Instagram still to the Facebook Page per firing.
#
# Why one at a time rather than one run of the whole backlog: the Page normally
# sees three posts a day, and the backlog emptied in a single run would put a
# dozen photos on it inside ten minutes. Three firings a day at --limit 1 give
# Facebook the same rhythm Instagram already has, so the two accounts post
# alongside each other with Instagram always ahead.
#
# facebook_sync.py re-reads the live Instagram account on every run, so a still
# deleted by hand between firings is skipped rather than mirrored. That check is
# the whole point of backfilling slowly instead of in one shot.

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

# Jitter, so the Page does not post at the same three clock times every day.
# launchd only fires on a fixed calendar, so the variation has to happen here:
# each firing waits a random 0-60 minutes before doing anything. The Instagram
# side gets the same effect from build_schedule.py's +/-12 min, which is why its
# slots read 11:39 one day and 11:37 the next.
#
# Its jitter is deterministic (seeded by post id) because rebuilding a schedule
# must not move posts that already went out. Nothing here is rebuilt, so plain
# randomness is fine and gives a wider spread.
#
# BEFORE the lock, never after. Sleeping with the lock held would stall the
# every-two-minute publisher for up to an hour, which is the one thing this
# script must not do.
JITTER=$(( RANDOM * 3600 / 32768 ))
sleep "$JITTER"

# The SAME lock run_publish.sh takes, and for a sharper reason than that script
# has. facebook_sync.py writes state/published.json without a lock of its own,
# so a firing that overlapped a publishing tick could read the file, be
# overtaken, and write back a copy missing the id the tick had just recorded.
# The lost id reads as "never posted", and the next run posts it again. A
# duplicate is the one failure here that cannot be undone.
#
# The calendar times sit between the Instagram slots and stay there across the
# full hour of jitter above (12:45-13:45, 17:30-18:30, 21:45-22:45 PKT against
# Instagram's 11:18-11:42, 16:18-16:42, 20:18-20:42), so this should never
# contend. This is the guarantee, not the plan.
LOCK="state/.publish.lock"
locked=""
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if mkdir "$LOCK" 2>/dev/null; then
    locked=1
    break
  fi
  # A tick holds the lock for seconds, so a short wait clears a genuine overlap.
  # Anything older than 30 minutes is a crash or a hard reboot, not a run.
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +30 2>/dev/null)" ]; then
    rmdir "$LOCK" 2>/dev/null
  fi
  sleep 20
done

# Give up rather than force it. A skipped firing costs a few hours; the next
# slot mirrors the same post, because nothing has been recorded as done.
if [ -z "$locked" ]; then
  printf '[%s] fb backfill: lock busy, skipping this slot\n' \
    "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" >> "$LOG"
  exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT INT TERM

# --limit 1: one post per firing. Three firings a day, so Facebook moves at the
# same three-a-day pace as Instagram and never in a burst.
out="$(/usr/bin/env python3 scripts/facebook_sync.py --backfill --apply --limit 1 2>&1)"
code=$?

# Once the backlog is empty this fires three times a day forever saying so.
# Worth keeping rather than unloading: it is also the safety net for any post
# whose Facebook half failed and then aged out of publish.py's grace window.
if [ $code -ne 0 ] || ! printf '%s' "$out" | grep -q '^nothing to backfill'; then
  printf '[%s] %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$out" >> "$LOG"
fi

exit $code
