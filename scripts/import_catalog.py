#!/usr/bin/env python3
"""Turn the supplied product catalogue into the posting media set.

    ~/Downloads/drive-download-.../<Category>/<Product>.png  ->  media/dk/<slug>.jpg

This replaces normalize_dk.sh + brand_dk.sh, both of which existed to fix
problems the August 2026 artwork no longer has:

  * It is already 1254x1254 square (175 of 178 files), so nothing needs padding
    to clear Instagram's 4:5 - 1.91:1 window, and nothing gets its sides lopped
    off by the square profile-grid thumbnail.
  * It already carries the DK lockup top left, so there is no logo to stamp.
    Stamping one anyway would double it up.

What is left is a format conversion: the API takes JPEG and the source is PNG.

Three files are not square and are padded to 1:1 against a blurred copy of
themselves - the same trick brand_dk.sh used, and for the same reason. A blur of
a flat background is that same flat colour, so on this artwork the padding is
invisible rather than reading as a letterbox.

Selection is one tile per product, from CATALOG.csv. The catalogue lists 178
image files for 122 products; the extras are alternate angles, and eight of them
are byte-identical duplicates. Posting all of them would put near-repeats
adjacent on the grid. Three alternates are pulled back in by hand - see EXTRAS -
purely to land three blocks on a row boundary.

Usage:
  python3 scripts/import_catalog.py [SRC_DIR] [--dry-run]
"""

import csv
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SRC = "/Users/m1pro/Downloads/drive-download-20260825T190330Z-1-001"
OUT = os.path.join(ROOT, "media", "dk")

# Alternate angles promoted to tiles of their own. Each is the most visually
# distinct alternate its product has (checked by SSIM against the primary), and
# each exists to take a block from n to a multiple of three. Adding a tile was
# preferred over holding a product back wherever a genuinely different angle
# existed - it keeps the product count whole.
EXTRAS = {
    "COB Light 13W": "COB Light 13W -2.png",
    "COB Light Moveable 7.5W": "COB Light Moveable 7.5W -2.png",
    "Downlight Smart 7W (105mm)": "Downlight Smart 7W (105mm) -2.png",
    "Downlight PL-Alum 13W": "Downlight PL-Alum 13W -2.png",
    "LED Tube Light D-Shape 10W 1.5FT": "LED Tube Light D-Shape 10W 1.5FT -2.png",
}

# Products held out of the run. Two are artwork faults found by reading the spec
# panel on every graphic; the rest are near-twins of a tile that does post. Each
# also happens to take its block to a multiple of three - see config/brands.json
# for the row arithmetic.
HELD = {
    # Artwork faults. Both would publish a wrong or blank spec to the feed.
    "COB Light 5W": "artwork reads 8W throughout - title, 112mm face, 3in cut-out - "
                    "so it is the 8W fitting under a 5W name, and COB Light 8W already posts it",
    "Downlight Smart 10W": "FACE DIAMETER is blank on the artwork, in both the left "
                           "column and the bottom bar; the 112mm and 120mm variants are unaffected",
    # Near-twins.
    "Bubble Light 13W (Indoor)": "near-twin of Bubble Light 13W; same 120mm face, same specs",
    "Solar Street Light Mono": "no wattage on the artwork, vaguest tile in the block",
    "Wall Light X155-12W White 12W": "same fitting as the X155 black in the same block",
}

MAX_W = 1440


def slug(name):
    s = re.sub(r"\.(png|jpe?g)$", "", name, flags=re.I).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def probe(path, field):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", f"stream={field}", "-of", "csv=p=0", path],
        capture_output=True, text=True)
    return int(out.stdout.strip().strip(","))


def convert(src, dest):
    w, h = probe(src, "width"), probe(src, "height")
    side = min(max(w, h), MAX_W)
    if w == h:
        vf = f"scale={side}:{side}"
        note = "square"
    else:
        # Blurred cover behind, whole image centred on top.
        vf = (f"[0:v]scale={side}:{side}:force_original_aspect_ratio=increase,"
              f"crop={side}:{side},boxblur=luma_radius=40:luma_power=2[bg];"
              f"[0:v]scale={side}:{side}:force_original_aspect_ratio=decrease[fg];"
              f"[bg][fg]overlay=(W-w)/2:(H-h)/2")
        note = f"padded {w}x{h} -> {side}x{side}"
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", src]
    cmd += (["-filter_complex", vf] if w != h else ["-vf", vf])
    cmd += ["-frames:v", "1", "-q:v", "2", "-pix_fmt", "yuvj420p", dest]
    subprocess.run(cmd, check=True)
    return note


def primary_file(files):
    """The un-suffixed file if there is one, else the first listed."""
    plain = [f for f in files if not re.search(r" -\d+\.\w+$", f)]
    return plain[0] if plain else files[0]


def resolve(src_dir, cat, fname):
    """Locate a catalogue entry on disk, tolerating a wrong extension.

    CATALOG.csv lists the neon flex hero as .jpeg and it is a .png on disk. One
    typo today, but the catalogue is hand-maintained, so the extension is
    treated as a hint rather than as fact.
    """
    direct = os.path.join(src_dir, cat, fname)
    if os.path.exists(direct):
        return direct
    stem = re.sub(r"\.\w+$", "", fname)
    for ext in (".png", ".jpg", ".jpeg", ".PNG", ".JPG", ".JPEG"):
        alt = os.path.join(src_dir, cat, stem + ext)
        if os.path.exists(alt):
            return alt
    return None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    src_dir = args[0] if args else DEFAULT_SRC

    rows = list(csv.DictReader(open(os.path.join(src_dir, "CATALOG.csv"),
                                    encoding="utf-8-sig")))
    if not dry:
        os.makedirs(OUT, exist_ok=True)

    made, skipped, padded = [], [], 0
    for r in rows:
        product, cat = r["Product"], r["Category"]
        if product in HELD:
            skipped.append((product, HELD[product]))
            continue
        files = [f.strip() for f in r["Files"].split(";")]
        picks = [primary_file(files)]
        if product in EXTRAS:
            picks.append(EXTRAS[product])

        for n, fname in enumerate(picks):
            src = resolve(src_dir, cat, fname)
            if src is None:
                print(f"MISSING  {cat}/{fname}", file=sys.stderr)
                continue
            name = slug(product) + ("" if n == 0 else f"-alt{n}")
            dest = os.path.join(OUT, name + ".jpg")
            note = "would convert" if dry else convert(src, dest)
            if note.startswith("padded"):
                padded += 1
            made.append((cat, product, name, note))

    for cat, product, name, note in made:
        print(f"{cat:<14} {product:<38} -> {name}.jpg  ({note})")
    print()
    for product, why in skipped:
        print(f"HELD  {product} - {why}")
    print(f"\n{len(made)} tiles written to media/dk "
          f"({padded} padded to square), {len(skipped)} products held back")


if __name__ == "__main__":
    main()
