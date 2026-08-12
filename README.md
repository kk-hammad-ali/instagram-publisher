# Instagram publisher — DK Lighting & Wegraphers

Schedules and publishes to two Instagram Business accounts from one queue.

| | DK Lighting | Wegraphers |
|---|---|---|
| Account | [@dklighitngpk](https://www.instagram.com/dklighitngpk/) | [@wegraphers4](https://www.instagram.com/wegraphers4/) |
| Media | 50 images | 25 reels |
| Cadence | 2/day — 11:30, 20:30 PKT | 3/day — 13:00, 18:30, 21:45 PKT |
| Runway | 25 days | 9 days |

## Why the pieces are shaped this way

**Instagram has no scheduling API.** Facebook Pages accept a `scheduled_publish_time`;
Instagram does not — a post happens the moment you call the endpoint. So the schedule is
ours (`state/schedule.json`) and a launchd agent on this Mac is the clock, firing every
two minutes.

**Images need a public URL, reels do not.** This asymmetry drives the whole setup. The
API does not accept an image upload — you give it an `image_url` and Meta's servers fetch
it, so every JPEG must sit at a public HTTPS address. (Google Drive share links do not
work: Drive answers with an HTML interstitial instead of image bytes.) Reels are the
opposite — resumable upload pushes bytes straight from this machine, so the 666MB of
video never leaves it and is not in git.

That is the only reason a GitHub repo exists here. It is not running anything; it is
serving `media/dk/*.jpg` over `raw.githubusercontent.com` so Instagram can fetch them.
Any static public host would do the same job.

**Misses are designed around.** The agent retries every two minutes, and a failed post is
simply not recorded as published, so the next tick picks it up. `publish.py` carries a
3-hour grace window: a slot missed while the Mac was asleep still goes out once it wakes,
but anything older is skipped rather than fired absurdly late — a machine that was off
overnight should not wake up and dump six posts at once. Slots also carry ±15 min of
deliberate jitter, since an exactly periodic posting pattern is cheap for spam heuristics
to spot.

## Layout

```
config/brands.json          slots, timezone, start date, pins, {{WHATSAPP}}
content/dk/captions.json    50 captions, hand-written
content/wegraphers/
  CAPTIONS.md               source of truth, hand-written
  captions.json             generated from it
media/dk/*.jpg              normalized stills
media/wegraphers/*.mp4      normalized reels
state/schedule.json         the queue (generated)
state/published.json        what has gone out (written by the runner)
scripts/                    normalizers, parser, schedule builder, publisher
```

## Commands

```bash
./scripts/normalize_dk.sh                  # PNG -> JPEG, fix aspect ratios
./scripts/normalize_reels.sh               # HEVC -> H.264, 4K -> 1080p
python3 scripts/parse_wegraphers_captions.py   # CAPTIONS.md -> captions.json
python3 scripts/build_schedule.py          # -> state/schedule.json
python3 scripts/publish.py --validate      # check every caption + media file
DRY_RUN=1 python3 scripts/publish.py       # resolve accounts, publish nothing
python3 scripts/publish.py                 # publish what is due
```

Edit captions or slots, then re-run `build_schedule.py`. It never re-queues anything
already in `state/published.json`, and jitter is seeded from the post id so rebuilding
does not reshuffle times for posts that already went out.

## What the media pipeline fixed

**DK** — 49 of 50 files were PNG; the API accepts JPEG only. Two infographics were 2:3
(0.667), below Instagram's 4:5 floor, so they are padded rather than cropped — cropping
an infographic eats the text it exists to show. Pad colour is sampled from each image's
own corner pixel, so the bars are invisible.

**Wegraphers** — 13 of 26 reels were HEVC, which the API either rejects or visibly
re-compresses; all are now H.264. Two were 4K (169MB and 165MB) and are downscaled to
1080p, which is what Instagram serves anyway — 157MB became 30MB.

## Content notes

**Reel order is load-bearing.** The file numbering (01=H3, 02=H2, 03=H1 …) encodes the
grid layout described in `CAPTIONS.md`: Instagram fills newest-first from the top left,
so posting the right-hand tile of each row first is what makes the finished profile grid
read left to right. `build_schedule.py` preserves it — re-sorting scrambles the grid.

**Reel 22 (G3, Lushly Ice Pops) is withheld.** Its export carries a burned-in
"NOT FOR ADVERTISMENT" watermark across the full runtime. The caption is written and
waiting; drop in a clean export, re-run the normalizer and the builder, and it queues
itself. Note that its absence leaves row G with two tiles instead of three, which shifts
the grid from that point on.

**Reel 25 (A4) is pinned to 14 August.** It is the Azadi Sale promo. In strict post order
it would have landed around 21 August, advertising a finished sale.

**DK captions are interleaved by product group** so the six near-identical 15W panel
images never run on consecutive days.

## Posting times

Current slots are informed starting positions, not measured truth — the rationale for
each is in `config/brands.json`. Once `instagram_manage_insights` has 2–3 weeks of data,
pull audience-online-by-hour and reach-per-post and rewrite the slots to fit these
followers specifically.

Worth knowing for that exercise: **@dklighitngpk follows 4 accounts against 8,771
followers.** That ratio often indicates a bought audience, which would not be genuinely
online at any particular hour. Trust the Insights reach data over the follower count.

## Setup

1. Meta app: **Other → Business**, linked to the Business Portfolio that owns both Pages
   and both Instagram accounts. Add the **Instagram** and **Facebook Login for Business**
   products.
2. Both Instagram accounts must be **Business** (not Creator) and linked to their Page.
3. Permissions: `instagram_basic`, `instagram_content_publish`, `instagram_manage_insights`,
   `pages_show_list`, `pages_read_engagement`, `business_management`.
4. Generate a **System User token** (Business Settings → Users → System Users) with both
   Pages and both Instagram accounts assigned. It does not expire; a Page token dies
   every 60 days.
5. No App Review needed — with an admin role on the app, Development mode covers your
   own accounts.

Put the token in `.env` as `META_ACCESS_TOKEN` (the file is gitignored). `MEDIA_BASE_URL`
is already set to the raw.githubusercontent prefix.

## The scheduler

A launchd agent runs the publisher every two minutes.

**The project lives at `~/ig-publisher`, not in `~/Documents`, and must stay there.**
macOS TCC blocks launchd agents from Documents, Desktop and Downloads — an agent pointed
at a Documents path dies with `Operation not permitted` (exit 126) until `/bin/bash` is
granted Full Disk Access. A folder directly in `$HOME` is unprotected, so no grant is
needed. There is a symlink at the old Documents path for convenience; do not move the
real directory back.

```bash
launchctl load  ~/Library/LaunchAgents/com.dkwegraphers.igpublisher.plist   # start
launchctl unload ~/Library/LaunchAgents/com.dkwegraphers.igpublisher.plist  # stop
launchctl list | grep igpublisher                                          # check
tail -f state/publish.log                                                  # watch
```

The log only records runs that published something or failed — "nothing due" fires around
720 times a day and would bury everything that matters.

`.github/workflows/publish.yml` is present but its cron is **commented out**. Two
schedulers would double-post, because each keeps its own `state/published.json` and
neither would see the other's. It is kept as a documented fallback for a stretch where
the Mac will be off.
