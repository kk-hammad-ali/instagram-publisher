#!/usr/bin/env python3
"""Build the posting queue.

Instagram's Content Publishing API has no scheduling of its own - unlike Facebook
Pages there is no scheduled_publish_time, so a post happens the moment the API is
called. This turns the caption file into one dated queue that the publisher walks
through, and a launchd agent on this Mac provides the clock.

Output: state/schedule.json, ordered by publish time.

Anything already in state/published.json is left out of the queue entirely rather
than queued-and-skipped. That matters now that posts go out in category blocks:
a published post left in the queue still consumes its day/slot, so the thirteen
already on the profile would buy a week of silence before the next new tile.
"""

import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKT = timezone(timedelta(hours=5))  # Pakistan has no DST; the offset is fixed.

# --launch-today re-dates the burst to today and respaces its slots between now
# and the evening. Without it the burst uses the date and slots in the config,
# which go stale the moment the launch slips a day - and a slot more than three
# hours old is skipped by publish.py rather than fired late, so a stale burst
# date silently drops most of day one.
LAUNCH_TODAY = "--launch-today" in sys.argv


def spread_remaining_today(n, last_hour=22, lead=12):
    """n slots, evenly spaced from a few minutes out to `last_hour`."""
    now = datetime.now(PKT) + timedelta(minutes=lead)
    end = now.replace(hour=last_hour, minute=0, second=0, microsecond=0)
    if end <= now:
        raise SystemExit(f"--launch-today: it is already past {last_hour}:00 PKT. "
                         f"Set launch.date to tomorrow and rebuild.")
    step = (end - now) / max(n - 1, 1)
    return [(now + step * k).strftime("%H:%M") for k in range(n)]


def load(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return json.load(f)


def jitter(post_id, spread):
    """Deterministic offset in [-spread, +spread] minutes, seeded by post id.

    Deterministic matters: rebuilding the schedule must not reshuffle times for
    posts that already went out, or the published-state check stops lining up.
    """
    h = hashlib.sha256(post_id.encode()).digest()
    return (int.from_bytes(h[:4], "big") % (spread * 2 + 1)) - spread


def order_by_block(posts, blocks):
    """Lay the run out one product category at a time.

    Instagram's grid is three tiles wide and fills newest-first from the top
    left, so a category only reads as a clean band across the profile if two
    things hold: its posts are consecutive, and the block boundaries land on a
    row boundary. Consecutive is what this function does. The row arithmetic is
    the config's job, and build() prints it on every run, so a block that has
    drifted off a boundary shows up here rather than three weeks later on the
    profile.

    Categories are taken in the order the block lists them, and posts within a
    category in id order. Id order is the visual rotation: ids were assigned so
    that consecutive posts step through the sub-families in the caption file's
    `group` field - A60, BS, T-series, A80 for the bulbs; square, round,
    D-shape, rod for the tubes. Sorting by id here is what keeps two
    near-identical graphics off adjacent tiles.
    """
    by_cat = {}
    for p in posts:
        by_cat.setdefault(p.get("category", "_"), []).append(p)

    out, used, layout = [], set(), []
    for b in blocks:
        block = []
        for cat in b.get("categories", []):
            if cat not in by_cat:
                raise SystemExit(f"block {b['name']!r} wants category {cat!r}, which "
                                 f"no live post carries. Known: {sorted(by_cat)}")
            for p in sorted(by_cat[cat], key=lambda x: x["id"]):
                if p["id"] not in used:
                    used.add(p["id"])
                    block.append(p)
        layout.append((b["name"], len(block)))
        out.extend(block)

    orphans = [p["id"] for p in posts if p["id"] not in used]
    if orphans:
        raise SystemExit("no block claims these live posts, so they would never go "
                         "out: " + ", ".join(orphans))
    return out, layout


def build():
    cfg = load("config/brands.json")
    start = datetime.strptime(cfg["start_date"], "%Y-%m-%d").replace(tzinfo=PKT)
    spread = cfg.get("jitter_minutes", 0)

    published = set()
    pub_path = os.path.join(ROOT, "state", "published.json")
    if os.path.exists(pub_path):
        with open(pub_path, encoding="utf-8") as f:
            published = {e["id"] for e in json.load(f).get("posts", [])}

    entries, report = [], []

    for key, brand in cfg["brands"].items():
        doc = load(brand["captions"])
        posts = [p for p in doc["posts"] if p.get("publish", True) and p.get("media")]
        held = [p for p in doc["posts"] if not p.get("publish", True)]

        layout = []
        if brand.get("order") == "category":
            posts, layout = order_by_block(posts, brand["blocks"])
        else:
            posts = sorted(posts, key=lambda p: p.get("post_no", 0))

        # Drop what is already on the profile. Done after ordering, so the block
        # layout reported below describes the finished grid rather than only the
        # tail of it still to come.
        already = [p for p in posts if p["id"] in published]
        posts = [p for p in posts if p["id"] not in published]

        slots = brand["slots"]
        pins = brand.get("pins", {})

        # A launch burst front-loads day one. The account is being repopulated
        # from zero before ads run against it, and two tiles is not a grid - so
        # the first day gets its own longer slot list and the steady 2/day
        # cadence starts the morning after.
        launch = brand.get("launch") or {}
        launch_slots = launch.get("slots", []) if launch.get("date") else []
        if LAUNCH_TODAY and launch_slots:
            launch = dict(launch, date=datetime.now(PKT).strftime("%Y-%m-%d"),
                          slots=spread_remaining_today(len(launch_slots)))
            launch_slots = launch["slots"]

        # Pull pinned posts out of the rolling sequence and place them by date.
        pinned, rolling = [], []
        for p in posts:
            pin = pins.get(str(p.get("post_no")))
            if pin:
                pinned.append((p, pin))
            else:
                rolling.append(p)

        taken = set()
        for p, pin in pinned:
            d = datetime.strptime(pin["date"], "%Y-%m-%d").replace(tzinfo=PKT)
            hh, mm = map(int, pin["slot"].split(":"))
            when = d.replace(hour=hh, minute=mm) + timedelta(minutes=jitter(p["id"], spread))
            taken.add((pin["date"], pin["slot"]))
            entries.append(make(key, brand, p, when, pinned=pin["reason"]))

        # Deal the rest into consecutive day/slot positions, skipping any a pin
        # already occupies so two posts never collide on one slot.
        burst, rest = rolling[:len(launch_slots)], rolling[len(launch_slots):]

        for n, p in enumerate(burst):
            day = datetime.strptime(launch["date"], "%Y-%m-%d").replace(tzinfo=PKT)
            hh, mm = map(int, launch_slots[n].split(":"))
            # No jitter on the burst. Its slots are already hand-spaced, and a
            # +/-15 minute nudge on six posts in one day can collide two of them.
            entries.append(make(key, brand, p, day.replace(hour=hh, minute=mm)))

        # The steady run starts the day after the burst, not on start_date.
        rolling_start = start
        if launch_slots:
            rolling_start = (datetime.strptime(launch["date"], "%Y-%m-%d")
                             .replace(tzinfo=PKT) + timedelta(days=1))

        i = 0
        for p in rest:
            while True:
                day = rolling_start + timedelta(days=i // len(slots))
                slot = slots[i % len(slots)]
                i += 1
                if (day.strftime("%Y-%m-%d"), slot) not in taken:
                    break
            hh, mm = map(int, slot.split(":"))
            when = day.replace(hour=hh, minute=mm) + timedelta(minutes=jitter(p["id"], spread))
            entries.append(make(key, brand, p, when))

        days = (len(rest) + len(slots) - 1) // len(slots) + (1 if launch_slots else 0)
        last = max((e["publish_at_pkt"] for e in entries if e["brand"] == key),
                   default="-")
        report.append((brand["name"], len(posts), len(slots), days, last,
                       layout, len(held), len(already), len(burst),
                       launch.get("date"), brand.get("kept_tiles", 0)))

    entries.sort(key=lambda e: e["publish_at_utc"])
    for e in entries:
        e["status"] = "published" if e["id"] in published else "pending"

    out = {
        "generated_note": "Generated by scripts/build_schedule.py - edit config/brands.json "
                          "or the caption files and rebuild, never hand-edit this file.",
        "timezone": cfg["timezone"],
        "posts": entries,
    }
    path = os.path.join(ROOT, "state", "schedule.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
        f.write("\n")

    for name, n, slots, days, last, layout, held, already, nburst, ldate, kept in report:
        if nburst:
            print(f"{name}: {nburst} on {ldate} (launch burst), then "
                  f"{n - nburst} at {slots}/day -> {days} days total, "
                  f"last on {last[:10]}")
        else:
            print(f"{name}: {n} still to post at {slots}/day -> {days} days, "
                  f"last on {last[:10]}")
        print(f"  {held} held back, {already} already on the profile")
        if layout:
            print("\n  Grid blocks, in POSTING order (3 tiles to a row):\n")
            # The kept post is the oldest thing on the account, so it sits at the
            # very bottom of the grid and takes the first tile position. Every
            # block boundary above it is therefore offset by that count - which
            # is why a block being a multiple of 3 is necessary but not
            # sufficient. What has to land on a boundary is the running total.
            pos = kept
            if kept:
                print(f"    {'(kept on profile)':<20} {kept:>3} tile   "
                      f"bottom row, oldest")
            straddling = []
            for bname, count in layout:
                pos += count
                rows, rem = divmod(pos, 3)
                if rem:
                    flag = f"   <-- ends mid-row ({rem} over)"
                    straddling.append(bname)
                else:
                    flag = ""
                print(f"    {bname:<20} {count:>3} tiles  {rows:>2} rows in{flag}")
            trows, trem = divmod(pos, 3)
            print(f"    {'-' * 20} {'-' * 3}        {'-' * 7}")
            print(f"    {'TOTAL':<20} {pos:>3} tiles  {trows:>2} rows"
                  + ("" if trem == 0 else f" + {trem} tile(s) over"))
            if straddling:
                print(f"\n  WARNING: these blocks do not end on a row boundary, so "
                      f"they share a\n  row with the next block: "
                      f"{', '.join(straddling)}")
            else:
                print("\n  Every block ends on a row boundary.")
            print(f"\n  The profile reads this list bottom-up: {layout[-1][0]} "
                  f"finishes at the top,\n  {layout[0][0]} at the bottom.")
    print(f"\n{len(entries)} queued -> state/schedule.json")


def make(key, brand, p, when, pinned=None):
    e = {
        "id": p["id"],
        "brand": key,
        "brand_name": brand["name"],
        "handle": brand["handle"],
        "ig_user_id": brand.get("ig_user_id"),
        "media_type": p.get("media_type", brand["media_type"]),
        "media": p["media"],
        "product": p.get("product", ""),
        "caption": p["caption"],
        "hashtags": p.get("hashtags", []),
        "publish_at_pkt": when.strftime("%Y-%m-%d %H:%M"),
        "publish_at_utc": when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if pinned:
        e["pinned_reason"] = pinned
    return e


if __name__ == "__main__":
    build()
