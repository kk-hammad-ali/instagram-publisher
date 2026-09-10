#!/usr/bin/env python3
"""Queue the GOFTECH stories, five a day, and merge them into the schedule.

Three sets are rendered by the goftech-social studio and converted to JPEG by
scripts/import_stories.sh:

  clients - "we built this with <client>" logo cards   (40)
  review  - verbatim five-star Google reviews          (6)
  service - one card per service GOFTECH sells         (11)

They are interleaved rather than run in blocks. Each item is scored by its
fractional position within its own set, and the three sets are merged on that
score, so every set is spread evenly across the whole run: a day comes out as
roughly three client cards with a service and a review among them, instead of
eight consecutive days of logos followed by two days of services.

Idempotent: the merge order is fixed by set size, and the jitter is seeded by
post id, so re-running never re-dates a story that has already gone out.
Non-goftech posts in the schedule are preserved untouched.

  python3 scripts/build_stories.py [--start YYYY-MM-DD] [--dry]
"""

import hashlib
import json
import os
import sys
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRAND = "goftech"
SETS = ["clients", "review", "service"]  # tie-break order, biggest first
PKT = timedelta(hours=5)  # Pakistan is UTC+5 year-round, no DST

# Cosmetic only - these labels appear in the queue preview and the publish log,
# never on the artwork or on Instagram.
FIXES = {"it": "IT", "uk": "UK", "dqcb": "DQCB", "avw": "AVW", "gts": "GTS",
         "seo": "SEO", "ai": "AI", "l": "L"}
EXACT = {
    "ui-ux-design": "UI/UX Design",
    "wordpress-development": "WordPress Development",
    "qalb-e-saleem": "Qalb-e-Saleem",
    "fleamail": "FleaMail",
    "shehminas": "Shehmina's",
    "edutalent": "EduTalent",
    "muhammad-ubaidullah-saad-berg": "Muhammad Ubaidullah (Saad Berg)",
    "niazi-tours-and-travels": "Niazi Tours & Travels",
}


def jitter(post_id, spread):
    """Deterministic offset in [-spread, +spread] minutes, seeded by post id."""
    h = hashlib.sha256(post_id.encode()).digest()
    return (int.from_bytes(h[:4], "big") % (spread * 2 + 1)) - spread


def label(slug):
    if slug in EXACT:
        return EXACT[slug]
    return " ".join(FIXES.get(w, w.capitalize()) for w in slug.split("-") if w)


def interleave(sets):
    """Merge the sets so each is spread evenly over the combined run.

    An item's score is its fractional position within its own set, so the third
    of eleven services scores the same as the twelfth of forty clients and they
    land next to each other. Sorting on that score alone would be ambiguous
    wherever two scores coincide, hence the set index as a tie-break - it keeps
    the output stable across runs, which is what makes re-building safe.
    """
    scored = []
    for si, name in enumerate(SETS):
        items = sets[name]
        for i, item in enumerate(items):
            scored.append((((i + 0.5) / len(items)), si, name, item))
    scored.sort(key=lambda r: (r[0], r[1]))
    return [(name, item) for _, _, name, item in scored]


def main():
    start = sys.argv[sys.argv.index("--start") + 1] if "--start" in sys.argv else None
    dry = "--dry" in sys.argv

    with open(os.path.join(ROOT, "config", "brands.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    brand = cfg["brands"][BRAND]
    slots = brand["slots"]
    spread = cfg.get("jitter_minutes", 0)
    day0 = datetime.strptime(start or brand["start_date"], "%Y-%m-%d")

    sets = {}
    for name in SETS:
        d = os.path.join(ROOT, "media", BRAND, name)
        files = sorted(f for f in os.listdir(d) if f.endswith(".jpg")) if os.path.isdir(d) else []
        if not files:
            print(f"no JPEGs in media/{BRAND}/{name} - run scripts/import_stories.sh",
                  file=sys.stderr)
            return 1
        sets[name] = files

    posts = []
    for i, (name, fname) in enumerate(interleave(sets)):
        day, slot = divmod(i, len(slots))
        pid = f"{BRAND}-{name}-{fname[:2]}"
        hh, mm = (int(x) for x in slots[slot].split(":"))
        when = day0.replace(hour=hh, minute=mm) + timedelta(days=day)
        when += timedelta(minutes=jitter(pid, spread))
        posts.append({
            "id": pid,
            "brand": BRAND,
            "brand_name": brand["name"],
            "handle": brand["handle"],
            "ig_user_id": brand["ig_user_id"],
            "media_type": "STORIES",
            "set": name,
            "media": f"media/{BRAND}/{name}/{fname}",
            "label": label(fname[3:-4]),
            "publish_at_pkt": when.strftime("%Y-%m-%dT%H:%M:%S"),
            "publish_at_utc": (when - PKT).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })

    days = (len(posts) + len(slots) - 1) // len(slots)
    print(f"{len(posts)} stories over {days} days, {len(slots)}/day, "
          f"{posts[0]['publish_at_pkt'][:10]} to {posts[-1]['publish_at_pkt'][:10]} PKT")
    for name in SETS:
        print(f"  {name}: {sum(1 for p in posts if p['set'] == name)}")
    if dry:
        return 0

    sched_path = os.path.join(ROOT, "state", "schedule.json")
    with open(sched_path, encoding="utf-8") as f:
        sched = json.load(f)
    kept = [p for p in sched["posts"] if p["brand"] != BRAND]
    sched["posts"] = kept + posts
    with open(sched_path, "w", encoding="utf-8") as f:
        json.dump(sched, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"kept {len(kept)} non-{BRAND} post(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
