#!/usr/bin/env bash
# Normalize Wegraphers reels for the Instagram Content Publishing API.
#
# Two problems in the source set:
#   - 13 of 26 files are HEVC (H.265). The API wants H.264; HEVC uploads either
#     fail outright or come back visibly re-compressed.
#   - Two files are 4K (169MB and 165MB). Instagram serves Reels at 1080p, so
#     the extra pixels only buy upload time and a longer container wait.
#
# Everything lands as 1080x1920 H.264 high/yuv420p + 48kHz stereo AAC, with the
# moov atom moved to the front so Instagram can start reading before it has the
# whole file.

set -euo pipefail

SRC="${1:-/Users/m1pro/Downloads/drive-download-20260811T112541Z-1-001}"
OUT="${2:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/media/wegraphers}"

mkdir -p "$OUT"

# ffprobe emits fields in its own internal order, not the order they are asked
# for, so each field is queried on its own rather than parsed positionally.
probe() {
  ffprobe -v error -select_streams v:0 -show_entries "stream=$2" \
    -of csv=p=0 "$1" 2>/dev/null | tr -d ',\r\n'
}

count=0
for f in "$SRC"/*.mp4; do
  [ -e "$f" ] || continue
  base="$(basename "$f")"

  # 22 / G3 carries a burned-in "NOT FOR ADVERTISMENT" watermark across its
  # whole runtime. It is excluded until a clean export replaces it.
  case "$base" in
    *"ON HOLD"*) echo "SKIP  $base  (watermarked, on hold)"; continue ;;
  esac

  # "01 - H3 - Inspire Home Store - Appliance Showroom.mp4" -> "01-h3"
  num="${base%% *}"
  tile="$(echo "$base" | awk -F' - ' '{print tolower($2)}')"
  dest="$OUT/${num}-${tile}.mp4"

  vcodec="$(probe "$f" codec_name)"
  w="$(probe "$f" width)"
  h="$(probe "$f" height)"

  ffmpeg -v error -y -i "$f" \
    -vf "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,setsar=1" \
    -c:v libx264 -profile:v high -level 4.1 -pix_fmt yuv420p \
    -crf 21 -preset medium -maxrate 8M -bufsize 16M -r 30 \
    -c:a aac -b:a 128k -ar 48000 -ac 2 \
    -movflags +faststart \
    "$dest"

  inmb=$(( $(stat -f%z "$f" 2>/dev/null || stat -c%s "$f") / 1048576 ))
  outmb=$(( $(stat -f%z "$dest" 2>/dev/null || stat -c%s "$dest") / 1048576 ))
  printf '%-58s %s %sx%s  %sMB -> h264 1080x1920 %sMB\n' \
    "$base" "$vcodec" "$w" "$h" "$inmb" "$outmb"
  count=$((count+1))
done

echo
echo "$count reels normalized into $OUT"
