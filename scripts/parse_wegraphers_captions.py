#!/usr/bin/env python3
"""Turn the hand-written Wegraphers CAPTIONS.md into the same JSON shape the
DK captions use, so one publisher can drive both brands.

The markdown is authored for humans: each post is an `### <n> · <TILE> — <title>`
heading followed by a fenced block holding the caption body and, on the last
lines, the hashtag block. This pulls those apart and matches each entry to its
normalized reel by the leading post number.
"""

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    ROOT, "content", "wegraphers", "CAPTIONS.md"
)
MEDIA_DIR = os.path.join(ROOT, "media", "wegraphers")
OUT = os.path.join(ROOT, "content", "wegraphers", "captions.json")

HEADING = re.compile(r"^###\s+(\d+)\s*[·.]\s*([A-H]\d)\s*[—-]\s*(.+?)\s*$")
ROW = re.compile(r"^##\s+ROW\s+([A-H])\s*[—-]\s*(.+?)\s*$")

text = open(SRC, encoding="utf-8").read()
lines = text.split("\n")

# post number -> normalized reel filename ("25-a4.mp4" -> 25)
reels = {}
if os.path.isdir(MEDIA_DIR):
    for f in os.listdir(MEDIA_DIR):
        m = re.match(r"^(\d+)-([a-h]\d)\.mp4$", f)
        if m:
            reels[int(m.group(1))] = f

posts, row_label, i = [], "", 0
while i < len(lines):
    line = lines[i]

    r = ROW.match(line)
    if r:
        row_label = r.group(2).strip()

    h = HEADING.match(line)
    if h:
        num, tile, title = int(h.group(1)), h.group(2), h.group(3)

        # Walk to the fenced block that follows the heading.
        j = i + 1
        while j < len(lines) and not lines[j].startswith("```"):
            j += 1
        body = []
        j += 1
        while j < len(lines) and not lines[j].startswith("```"):
            body.append(lines[j])
            j += 1

        # Trailing lines that are pure hashtags are the tag block; the rest is
        # the caption. Splitting from the end keeps any mid-caption "#" safe.
        tags, k = [], len(body) - 1
        while k >= 0 and (body[k].strip() == "" or body[k].strip().startswith("#")):
            if body[k].strip().startswith("#"):
                tags = re.findall(r"#(\w+)", body[k]) + tags
            k -= 1
        caption = "\n".join(body[: k + 1]).strip()

        on_hold = "ON HOLD" in title.upper() or num not in reels
        posts.append({
            "id": f"wg-{num:02d}",
            "post_no": num,
            "tile": tile,
            "media": f"media/wegraphers/{reels[num]}" if num in reels else None,
            "product": title,
            "group": f"row-{tile[0].lower()}",
            "row": row_label,
            "caption": caption,
            "hashtags": tags,
            "publish": not on_hold,
        })
        i = j
    i += 1

posts.sort(key=lambda p: p["post_no"])

doc = {
    "brand": "Wegraphers",
    "handle": "wegraphers4",
    "website": "wegraphers.com",
    "voice": ("We Create You Grow. Creative Content & Digital Marketing. "
              "Ads | Visual Story telling | Podcast. Let's Build Your Brand Together."),
    "notes": [
        "Captions were hand-written in thumbnails/CAPTIONS.md and are reproduced verbatim. "
        "This file is generated - edit the markdown, then re-run scripts/parse_wegraphers_captions.py.",
        "Each caption sells the production, not the product. That is a deliberate choice: it keeps "
        "a portfolio account clear of Instagram's health-claim rules on the supplement and pharma work.",
        "Post 22 (G3, Lushly Ice Pops) is withheld - the export carries a burned-in "
        "'NOT FOR ADVERTISMENT' watermark. Its caption is kept ready for a clean re-export.",
    ],
    "posts": posts,
}

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(doc, f, indent=2, ensure_ascii=False)
    f.write("\n")

publishable = [p for p in posts if p["publish"]]
missing_media = [p["id"] for p in posts if p["publish"] and not p["media"]]
no_caption = [p["id"] for p in posts if not p["caption"]]

print(f"parsed {len(posts)} captions from CAPTIONS.md")
print(f"publishable: {len(publishable)}")
print(f"withheld:    {[p['id'] + ' (' + p['tile'] + ')' for p in posts if not p['publish']]}")
print(f"reels on disk: {len(reels)}")
if missing_media:
    print(f"WARNING no reel matched: {missing_media}")
if no_caption:
    print(f"WARNING empty caption: {no_caption}")

have = {p["tile"] for p in posts}
want = {f"{r}{n}" for r in "ABCDEFGH" for n in (1, 2, 3)} | {"A4", "E4"}
print(f"tiles with no caption: {sorted(want - have) or 'none'}")
print(f"-> {OUT}")
