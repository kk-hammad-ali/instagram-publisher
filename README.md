# Instagram + Facebook publisher — DK Lighting

Schedules and publishes stills to [@dklightingpk](https://www.instagram.com/dklightingpk/)
and to the matching [DK Lighting Facebook Page](https://www.facebook.com/103512834602763).

| | |
|---|---|
| Media | 122 stills, one per product, from the 25 August 2026 catalogue |
| Cadence | 8 on launch day, then 3/day — 11:30, 16:30, 20:30 PKT |
| Runway | 39 days, 27 August → 4 October |
| Accounts | Instagram from 26 August; Facebook from **29 August** (dk-015 onward) |
| Audience | 12 followers on Instagram, 870 fans on Facebook |

The previous 51-post set was retired on 2026-08-26 along with its captions, its
media and the two-stage normalize/brand pipeline that produced it. Git history

## Why the pieces are shaped this way

**Instagram has no scheduling API.** Facebook Pages accept a
`scheduled_publish_time`; Instagram does not — a post happens the moment you call
the endpoint. So the schedule is ours (`state/schedule.json`) and a launchd agent
on this Mac is the clock, firing every two minutes.

**Images need a public URL.** The API does not accept an image upload — you give
it an `image_url` and Meta's servers fetch it, so every JPEG must sit at a public
HTTPS address. (Google Drive share links do not work: Drive answers with an HTML
interstitial instead of image bytes.) That is the only reason a GitHub repo
exists here. It is not running anything; it is serving `media/dk/*.jpg` over
`raw.githubusercontent.com`. Any static public host would do the same job.

A useful consequence: Instagram fetches the image once, at publish time, and
keeps its own copy. Re-running the import never alters a post already out.

**Misses are designed around.** The agent retries every two minutes, and a failed
post is simply not recorded as published, so the next tick picks it up.
`publish.py` carries a 3-hour grace window: a slot missed while the Mac was
asleep still goes out once it wakes, but anything older is skipped rather than
fired absurdly late. Slots also carry ±12 min of deterministic jitter, since an
exactly periodic posting pattern is cheap for spam heuristics to spot.

## Facebook

The Page went live on 29 August, part-way through the run. `fb_start_date` in
`config/brands.json` is the cut-off: posts scheduled on or after it are mirrored
in the same tick that publishes them to Instagram, and the 14 that went out
before it are left to `facebook_sync.py --backfill` at the end of the run.

That split is not cosmetic. The tick has a three-hour grace window and skips
anything older, so without the cut-off it would re-examine every early post on
every two-minute run and log nothing but grace-window skips forever.

**The two platforms are tracked separately.** One record per post in
`state/published.json`, carrying an `ig_media_id` and an `fb_post_id`. Either
can be absent. A post that reaches Instagram and then fails on Facebook keeps
its Instagram id, so the retry two minutes later posts only the Facebook half —
the one failure mode here that cannot be undone is a duplicate, and that is what
prevents it.

**Facebook uses `/photos`, not `/feed`.** `/feed` with a link renders a link
preview card; `/photos` makes the image the post, which is what the Instagram
side does. Meta fetches `MEDIA_BASE_URL` exactly as Instagram does, so Facebook
needs no hosting of its own.

### Posts get deleted by hand, and nothing tells this repo

Stills are removed from the Instagram account after they publish — two already
have been (dk-004 and dk-007, both Adjustable Panel Lights). More will be. The
deletions happen *after* the post is live, so there is nothing to decide up
front and no way for the scheduler to know in advance.

So it is reconciled after the fact instead, and the rule is **Facebook shows
what is live on Instagram**:

- `--backfill` checks every candidate against the live Instagram account before
  mirroring it. Anything deleted since it published is skipped, not carried over.
- `--reconcile` covers the other direction — a post that went out to both and
  was then deleted from Instagram only. Facebook, unlike Instagram, *does* have
  a delete endpoint, so with `--apply` the orphaned Page post is removed too.

Both are read-only until `--apply` is passed. Run `--reconcile` every week or so
during the run, and once more after the backfill.

The backfill also spaces its posts (`--delay`, default 45s). A hundred photos
posted to a Page inside a minute is a cheap thing for spam heuristics to spot,
and it is the one run that would otherwise do exactly that.

## The grid is the layout unit

The run goes out **one product category at a time**, and two rules make a
category read as a clean band on the profile:

1. **Its posts are consecutive.** `order: "category"` in `config/brands.json`
   does this; blocks are listed there in posting order.
2. **The running tile total lands on a multiple of three.** Instagram's grid is
   three wide. A block being a multiple of 3 is necessary but not sufficient —
   what has to land on a boundary is the cumulative count, because one post is
   being kept and it occupies the first tile position.

```
(kept reel)            1 tile     bottom row, oldest
Panel Lights           8 tiles    3 rows in     <- 8, not 9, to absorb the reel
Flood Lights          12 tiles    7 rows in
COB Lights             9 tiles   10 rows in
Downlights            18 tiles   16 rows in
Tube Lights           24 tiles   24 rows in
LED Bulbs             18 tiles   30 rows in
Bubble Lights          3 tiles   31 rows in
Track Lights           3 tiles   32 rows in
Street Lights          3 tiles   33 rows in
Solar Lights           6 tiles   35 rows in
Strip & Neon Flex      9 tiles   38 rows in
Wall Lights            9 tiles   41 rows in
                     123 tiles   41 rows exactly
```

`build_schedule.py` prints this on every run and warns on any block that ends
mid-row, so a drift shows up there rather than three weeks later on the profile.

**The profile reads this list bottom-up.** Instagram fills the grid newest-first
from the top left, so the block posted *last* finishes at the *top*. Panel and
Flood lead because ad spend starts on day one and they are the most visually
varied blocks; Wall Lights and Strip & Neon are held to the end because they are
the most decorative and end up at the top of the finished profile. The three
small blocks sit in the middle where they are least conspicuous.

**Within a block, order rotates sub-families rather than climbing wattage.**
This catalogue's one real grid problem is that DK's spec-sheet template makes
every graphic in a category look alike — eighteen bulbs on the same teal layout
read as one smear. Ids were assigned so consecutive posts step through the
`group` field in the caption file: A60, BS, T-series, A80 for the bulbs; square,
round, D-shape, rod, T5, T8 for the tubes. `build_schedule.py` sorts by id
within a block, so that rotation is what reaches the grid.

## Launch burst

Day one is 8 posts — the whole Panel Lights block, hand-spaced 10:00 to 21:45.
The account is being repopulated from zero before ad spend points at it, and a
grid two tiles deep converts badly. No jitter is applied to these; the slots are
already spaced, and ±12 minutes on eight posts in a day can collide two of them.

`build_schedule.py --launch-today` re-dates the burst to today and respaces its
slots between now and 22:00. Use it if the launch slips: a slot more than three
hours old is skipped rather than fired late, so a stale launch date silently
drops most of day one.

## Layout

```
config/brands.json          slots, launch burst, block order, row arithmetic
content/dk/captions.json    122 posts, hand-written
media/dk/*.jpg              1254x1254, served over raw.githubusercontent.com
media/dk/*.mp4              the old unused commercial; gitignored
state/schedule.json         the queue (generated)
state/published.json        what has gone out, per platform (written by the runner)
state/DELETE-THESE.md       the 14 old posts to remove by hand, and the 1 to keep
```

## Commands

```bash
python3 scripts/import_catalog.py [SRC]    # catalogue -> media/dk/*.jpg
python3 scripts/build_schedule.py          # -> state/schedule.json, prints row maths
python3 scripts/publish.py --validate      # check every caption + media file
DRY_RUN=1 python3 scripts/publish.py       # resolve accounts, publish nothing
python3 scripts/publish.py                 # publish what is due, both platforms

python3 scripts/facebook_sync.py --status     # per-post: live on IG? mirrored to FB?
python3 scripts/facebook_sync.py --backfill   # mirror the Instagram-only posts (dry)
python3 scripts/facebook_sync.py --backfill --apply
python3 scripts/facebook_sync.py --reconcile  # FB posts whose IG twin was deleted (dry)
python3 scripts/facebook_sync.py --reconcile --apply
```

`facebook_sync.py` makes no changes without `--apply`.

Edit captions or blocks, then re-run `build_schedule.py`. It leaves out anything
already in `state/published.json` — queued-and-skipped would still consume a
day/slot and buy days of silence before the next new tile.

## The media pipeline

`import_catalog.py` replaced `normalize_dk.sh` and `brand_dk.sh`, both of which
existed to fix problems the August 2026 artwork does not have:

- **Aspect.** The new graphics are already 1254×1254, inside Instagram's 4:5 –
  1.91:1 window and square for the profile thumbnail. Three of 178 files are not
  square; two of those are used, and they are padded to 1:1 against a blurred
  copy of themselves — invisible on a flat background.
- **Branding.** The artwork already carries the DK lockup top left. Stamping one
  would double it up, so the whole logo pipeline (`prep_logo.py`,
  `config/dk-logo.png`) is gone.
- **Format.** Still needed: the source is PNG and the API takes JPEG only.

Selection is one tile per product. The catalogue lists 178 files for 122
products; the extras are alternate angles and eight are byte-identical
duplicates. Posting all of them would put near-repeats side by side.

## Content notes

**Five products are held back**, each with a written reason in
`import_catalog.py`. Two are artwork faults found by reading the spec panel on
every graphic:

- **COB Light 5W** — the artwork reads 8W throughout: title, 112mm face, 3in
  cut-out. It is the 8W fitting under a 5W name, and COB Light 8W already posts
  it. (The same fault was present in the previous catalogue.)
- **Downlight Smart 10W** — FACE DIAMETER is blank on the graphic, in both the
  left column and the bottom bar. The 112mm and 120mm variants are unaffected.

The other three are near-twins of a tile that does post. Three alternate angles
were promoted to tiles of their own to keep the count at 122 and the blocks on
row boundaries.

**`LED Tube Light 24W 6FT Square`** is listed in CATALOG.csv as the 6FT unit and
its artwork's length icon reads 4FT / 1.2M. The caption states no length until
that is settled.

**Every caption claim comes from that product's own spec panel.** No lumen, IP,
lm/W, colour-temperature or warranty figure appears in a caption unless it is
printed on the graphic it is attached to.

## Posting times

Current slots are informed starting positions, not measured truth — the rationale
for each is in `config/brands.json`. The 16:30 slot is the weakest of the three
on paper and the one to move first. Once `instagram_manage_insights` has 2–3
weeks of data, pull audience-online-by-hour and reach-per-post and rewrite the
slots to fit these followers specifically.

Worth knowing for that exercise: **@dklightingpk is a relaunch account** — 8
followers. For the first few weeks nearly all reach will be non-follower reach
from hashtags and Explore, so slot timing matters far less than it will later.

The older **@dklighitngpk** (8,771 followers, misspelled handle) is not being
posted to. It follows only 4 accounts against those 8,771 followers, a ratio that
often indicates a bought audience — so if you ever switch back, trust Insights
reach over follower count.

## Setup

1. Meta app: **Other → Business**, linked to the Business Portfolio that owns the
   Page and the Instagram account. Add the **Instagram** and **Facebook Login for
   Business** products.
2. The Instagram account must be **Business** (not Creator) and linked to its Page.
3. Assign **both** assets to the system user in Business Settings → Users →
   System Users → *Social-Up* → Add Assets: the Instagram account, and the Page
   with at least the **Create content** task. Assigning only the Instagram
   account is what the `id_note` in `config/brands.json` describes — Page-based
   discovery through `/me/accounts` returns nothing, and `publish.py` falls back
   to the pinned ids. The Page was assigned on 2026-08-28.
4. Token scopes. Instagram alone needs `instagram_basic`,
   `instagram_content_publish`, `pages_show_list`, `pages_read_engagement` and
   `business_management`. Facebook publishing additionally needs
   **`pages_manage_posts`** — without it the Page endpoints return
   `(#200) Permissions error` however the assets are assigned. Scopes are fixed
   when the token is issued, so adding one means **regenerating the system user
   token**, not re-assigning the asset.

The token is a system user token and does not expire. `.env` is gitignored;
the previous token is kept at `.env.bak.20260828` until the new one has run a
few days clean.
