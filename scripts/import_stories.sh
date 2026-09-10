#!/usr/bin/env bash
# Convert the goftech-social studio's story PNGs into the JPEGs the Graph API
# accepts. Instagram rejects PNG on a STORIES container outright.
#
# Three sets, each into its own subdirectory so the queue builder can rotate
# between them rather than running eight straight days of the same template:
#
#   clients - "we built this with <client>" logo cards
#   review  - five-star Google reviews, verbatim
#   service - one card per service GOFTECH sells
#
# Re-runnable: wipes and rebuilds media/goftech wholesale. The studio output is
# the master; nothing under media/goftech is edited by hand. Files starting with
# "_" are studio contact sheets (e.g. service-stories/_all.jpg at 1598x930), not
# stories, and are skipped.
set -euo pipefail
SRC="${1:-/Users/m1pro/Documents/goftech/goftech-social/out}"
DST="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/media/goftech"

total=0
# "set:studio-directory" - the media/goftech subdir is named for the set, the
# source directory for whatever the studio calls it.
for pair in clients:client-stories review:review-stories service:service-stories; do
  set="${pair%%:*}"
  src="$SRC/${pair##*:}"
  [ -d "$src" ] || { echo "missing $src" >&2; exit 1; }
  out="$DST/$set"
  rm -rf "$out"; mkdir -p "$out"
  n=0
  for f in "$src"/*.png; do
    b="$(basename "$f" .png)"
    case "$b" in _*) continue ;; esac
    # q88 keeps these gradient-heavy cards clean and lands each well under the
    # API's 8MB image ceiling - the largest comes out around 200KB.
    sips -s format jpeg -s formatOptions 88 "$f" --out "$out/$b.jpg" >/dev/null
    n=$((n+1))
  done
  echo "  $set: $n"
  total=$((total+n))
done
echo "$total story JPEGs in media/goftech"
