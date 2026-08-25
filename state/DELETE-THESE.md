# Posts to delete from @dklightingpk

Checked live against the Graph API on **2026-08-26**. The account holds **15
posts**: 13 stills, and 2 reels. Fourteen of them go; one stays.

Instagram's Graph API is read-only for published media — there is no DELETE
endpoint, and the call returns `(#10) Insufficient permissions` for every
account regardless of scopes. So this is by hand, in the app: open each link,
**...** menu, Delete.

---

## KEEP — do not touch

| posted | what | link |
|---|---|---|
| 2026-08-25 | **All-in-One Lighting Solution** — reel, 9 likes, 2 comments | https://www.instagram.com/reel/DcdjLwMMlCd/ |

This is the one video that stays. It is also load-bearing for the grid: as the
oldest surviving post it sits at the bottom-right of the finished profile and
takes one tile of the bottom row, which is why launch day is **8** posts and not
9. Eight new tiles plus this reel is exactly three rows.

Delete it and every band on the profile shifts by one tile — say so before you
do, and the schedule can be rebuilt around it.

---

## DELETE — all 14

**The reel**

| # | posted | what | link |
|---|---|---|---|
| 1 | 2026-08-13 | Happy Independence Day 14th August — seasonal, four months stale | https://www.instagram.com/reel/Db_i3KEMZGN/ |

**The stills** — all 13, oldest first

| # | posted | product | link |
|---|---|---|---|
| 2 | 2026-08-13 | AK Downlight 7W (112mm cutout) | https://www.instagram.com/p/Db-FEwDESDo/ |
| 3 | 2026-08-13 | Adjustable Panel Light 15W | https://www.instagram.com/p/Db_Fw4WEetd/ |
| 4 | 2026-08-14 | COB Light 3W | https://www.instagram.com/p/DcBtqLjEXYl/ |
| 5 | 2026-08-15 | Adjustable Panel Light 24W | https://www.instagram.com/p/DcEQz2Lmsxe/ |
| 6 | 2026-08-16 | Bubble Light 10W | https://www.instagram.com/p/DcGFG7hEdbm/ |
| 7 | 2026-08-16 | COB downlight — studio render | https://www.instagram.com/p/DcGxOsSFT-C/ |
| 8 | 2026-08-17 | COB Light Moveable 5W | https://www.instagram.com/p/DcIal5TCtKc/ |
| 9 | 2026-08-17 | 2835 Strip Light 6.8mm — 100m roll | https://www.instagram.com/p/DcJdmR8CgEH/ |
| 10 | 2026-08-18 | COB Light Deluxe 5W | https://www.instagram.com/p/DcK9buvikj5/ |
| 11 | 2026-08-18 | COB Neon Flex 8mm 10W | https://www.instagram.com/p/DcL9j81CuZk/ |
| 12 | 2026-08-19 | COB Light Sunflower 5W | https://www.instagram.com/p/DcNnXkTCnKs/ |
| 13 | 2026-08-19 | Downlight Alpha 7W | https://www.instagram.com/p/DcOic7mCguo/ |
| 14 | 2026-08-20 | Adjustable Panel Light 15W | https://www.instagram.com/p/DcQIV9HirGE/ |

---

## Timing

Delete before the first new post goes out at **10:00 PKT on 27 August**, so the
profile is never a mix of the old set and the new one. If the deletions run
late, the new posts still publish correctly — the grid just reads wrong until
the old tiles are gone.

Nothing in this repository depends on the deletions having happened.
`state/published.json` is already empty, so `build_schedule.py` queues the full
122 regardless.
