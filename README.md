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
ours (`state/schedule.json`) and GitHub Actions is the clock.

**Images need a public URL, reels do not.** The API fetches images itself, so each JPEG
must sit at a public HTTPS address — and Google Drive share links will not work, since
Drive answers with an HTML interstitial instead of image bytes. Reels take the resumable
upload path, pushing bytes straight from the runner, so the videos need no hosting.

**Cron drift is designed around.** GitHub's scheduler runs late by 5–15 minutes under
load. Slots already carry ±15 min of deliberate jitter (an exactly periodic posting
pattern is cheap for spam heuristics to spot), and the publisher has a 3-hour grace
window so a delayed run still posts. Past that window it skips — a runner that was down
overnight should not wake up and dump six posts at once.

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

Repo secrets: `META_ACCESS_TOKEN`, `MEDIA_BASE_URL`. Optional repo variable:
`GRAPH_VERSION` (defaults to `v23.0`).

Set the WhatsApp number in `config/brands.json` under `tokens.WHATSAPP`. Until it is set,
all 50 DK posts fail validation by design rather than publishing "WhatsApp  for the
trade list."
