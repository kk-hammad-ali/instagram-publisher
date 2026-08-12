#!/usr/bin/env bash
# Normalize DK Lighting stills for the Instagram Content Publishing API.
#
# The API accepts JPEG only, caps width at 1440px and rejects anything outside
# a 4:5 – 1.91:1 aspect window. Two of the infographics are 2:3 (0.667), which
# is below the 4:5 floor, so they get padded rather than cropped — cropping an
# infographic eats the text it exists to show. Pad colour is sampled from the
# source's own top-left pixel so the bars are invisible against the artwork.

set -euo pipefail

SRC="${1:-/Users/m1pro/Downloads/dk}"
OUT="${2:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/media/dk}"

MIN_RATIO=0.8      # 4:5
MAX_RATIO=1.91     # 1.91:1
MAX_W=1440

mkdir -p "$OUT"

# Read the top-left pixel as hex, for use as the letterbox colour.
sample_corner() {
  ffmpeg -v error -i "$1" -vf "crop=1:1:0:0" -f rawvideo -pix_fmt rgb24 - 2>/dev/null \
    | od -An -tx1 | tr -d ' \n' | cut -c1-6
}

# ffprobe emits fields in its own internal order, not the order they are asked
# for, so each dimension is queried on its own rather than parsed positionally.
probe() {
  ffprobe -v error -select_streams v:0 -show_entries "stream=$2" \
    -of csv=p=0 "$1" 2>/dev/null | tr -d ',\r\n'
}

slug() {
  echo "$1" \
    | tr '[:upper:]' '[:lower:]' \
    | sed -E 's/\.(png|jpe?g)$//; s/[^a-z0-9]+/-/g; s/^-+|-+$//g'
}

count=0; padded=0
for f in "$SRC"/*.png "$SRC"/*.jpeg "$SRC"/*.jpg; do
  [ -e "$f" ] || continue
  base="$(basename "$f")"
  name="$(slug "$base")"
  dest="$OUT/${name}.jpg"

  w="$(probe "$f" width)"
  h="$(probe "$f" height)"

  ratio=$(awk -v w="$w" -v h="$h" 'BEGIN{printf "%.4f", w/h}')

  # Downscale to the 1440px width ceiling, preserving aspect.
  vf="scale='min($MAX_W,iw)':-2"

  below=$(awk -v r="$ratio" -v m="$MIN_RATIO" 'BEGIN{print (r<m)?1:0}')
  above=$(awk -v r="$ratio" -v m="$MAX_RATIO" 'BEGIN{print (r>m)?1:0}')

  if [ "$below" = "1" ]; then
    # Too tall: widen the canvas to exactly 4:5, centring the artwork.
    bg="$(sample_corner "$f")"
    vf="${vf},pad=ceil(ih*${MIN_RATIO}/2)*2:ih:(ow-iw)/2:0:0x${bg}"
    padded=$((padded+1))
    note="padded to 4:5 on #${bg}"
  elif [ "$above" = "1" ]; then
    # Too wide: heighten the canvas to exactly 1.91:1.
    bg="$(sample_corner "$f")"
    vf="${vf},pad=iw:ceil(iw/${MAX_RATIO}/2)*2:0:(oh-ih)/2:0x${bg}"
    padded=$((padded+1))
    note="padded to 1.91:1 on #${bg}"
  else
    note="in range"
  fi

  ffmpeg -v error -y -i "$f" -vf "$vf" -q:v 2 -pix_fmt yuvj420p "$dest"

  nw="$(probe "$dest" width)"
  nh="$(probe "$dest" height)"
  kb=$(( $(stat -f%z "$dest" 2>/dev/null || stat -c%s "$dest") / 1024 ))

  printf '%-46s %sx%s (%.3f) -> %sx%s %skB  %s\n' \
    "$base" "$w" "$h" "$ratio" "$nw" "$nh" "$kb" "$note"
  count=$((count+1))
done

echo
echo "$count images normalized into $OUT ($padded needed aspect padding)"
