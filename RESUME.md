# Resuming DK Lighting

The 25 August catalogue is built. **122 posts are queued and validated**, every
block lands on a row boundary, and publishing is paused. Three steps left.

---

### 1. Delete the 14 old posts

The list with direct links is in [`state/DELETE-THESE.md`](state/DELETE-THESE.md).
By hand, in the app: Instagram's Graph API is read-only for published media —
there is no delete endpoint, and calling it returns `(#10) Insufficient
permissions` no matter what scopes the token carries.

**Keep the All-in-One Lighting Solution reel**
(https://www.instagram.com/reel/DcdjLwMMlCd/, posted 25 August). It is the only
survivor, and it is load-bearing: as the oldest post it takes one tile of the
bottom row, which is why launch day is 8 posts and not 9.

Nothing here depends on the deletions having happened — `state/published.json`
is empty, so the full 122 queue regardless.

### 2. Push, so Instagram can fetch the images

`MEDIA_BASE_URL` points at `raw.githubusercontent.com/.../main`, so an image that
is not pushed cannot be published.

```bash
git add -A
git commit -m "Replace DK set with the August 2026 catalogue: 122 posts in 12 category blocks"
git push origin main
curl -sI "https://raw.githubusercontent.com/kk-hammad-ali/instagram-publisher/main/media/dk/adjustable-panel-light-15w.jpg" | head -1   # want 200
```

### 3. Un-pause

If the day has moved on since this was built, re-date the burst first — a slot
more than three hours old is skipped rather than fired late:

```bash
python3 scripts/build_schedule.py --launch-today
```

Then cut `dk` from `PAUSED_BRANDS` in `.env` so it reads `PAUSED_BRANDS=`, and
confirm before the launchd agent's next two-minute tick:

```bash
set -a && . ./.env && set +a && DRY_RUN=1 python3 scripts/publish.py
```

---

## The calendar

**Day one — 8 posts, 27 August.** The whole Panel Lights block, hand-spaced.
With the kept reel that is three full rows on the profile before ad spend points
at it.

| | | |
|---|---|---|
| 10:00 | `dk-001` | Adjustable Panel Light 15W |
| 11:45 | `dk-002` | Panel Light 60W (600×600mm) |
| 13:30 | `dk-003` | Open Panel Light 18W |
| 15:15 | `dk-004` | Adjustable Panel Light 20W |
| 17:00 | `dk-005` | Panel Light 40W (300×1200mm) |
| 18:45 | `dk-006` | Open Panel Light 24W |
| 20:15 | `dk-007` | Adjustable Panel Light 24W |
| 21:45 | `dk-008` | Panel Light 50W (600×600mm) |

**From 28 August — 3 a day**, 11:30 / 16:30 / 20:30 PKT ±12 min, finishing
4 October.

| block | tiles | rows | dates |
|---|---|---|---|
| Panel Lights | 8 | 3 (with the reel) | 27 Aug |
| Flood Lights | 12 | 4 | 28–31 Aug |
| COB Lights | 9 | 3 | 1–3 Sep |
| Downlights | 18 | 6 | 4–9 Sep |
| Tube Lights | 24 | 8 | 10–17 Sep |
| LED Bulbs | 18 | 6 | 18–23 Sep |
| Bubble Lights | 3 | 1 | 24 Sep |
| Track Lights | 3 | 1 | 25 Sep |
| Street Lights | 3 | 1 | 26 Sep |
| Solar Lights | 6 | 2 | 27–28 Sep |
| Strip & Neon Flex | 9 | 3 | 29 Sep – 1 Oct |
| Wall Lights | 9 | 3 | 2–4 Oct |
| | **122** | **41 rows** | |

Blocks are ordered so **Wall Lights finish at the top of the profile** — the grid
reads newest-first, so the last block posted is the first one seen. Panel and
Flood lead because ad spend starts on day one.

## Five images are held back

Set by `HELD` in `scripts/import_catalog.py`, each with a written reason. Two are
artwork faults, three are near-twins. Flipping one back changes a block's tile
count, so re-check the rows `build_schedule.py` prints.

| product | why |
|---|---|
| COB Light 5W | artwork reads 8W throughout — title, 112mm face, 3in cut-out |
| Downlight Smart 10W | FACE DIAMETER is blank on the artwork |
| Bubble Light 13W (Indoor) | near-twin of Bubble Light 13W |
| Solar Street Light Mono | no wattage on the artwork |
| Wall Light X155-12W White | same fitting as the X155 black, which posts |

Three alternate angles were promoted to tiles of their own to keep the count at
122 — a second view of the COB 13W, the Downlight Smart 7W (105mm) and the
D-Shape 10W tube. Set by `EXTRAS` in the same file.

## One thing left open

**`LED Tube Light 24W 6FT Square`** — CATALOG.csv calls it the 6FT unit; the
length icon on its artwork reads 4FT / 1.2M. The caption states no length at all
until that is settled. Worth checking against stock, then adding the length back.

## The old commercial

`media/dk/DK LIghting Video Commercial.mp4` (95MB) is still on disk and
gitignored. It is in no queue and was never published. It is not deleted only
because it is not recoverable from git if it turns out to be wanted.
