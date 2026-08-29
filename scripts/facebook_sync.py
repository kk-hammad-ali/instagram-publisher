#!/usr/bin/env python3
"""Keep the Facebook Page in step with what is actually live on Instagram.

Two jobs, both driven by the same fact: Instagram posts get deleted by hand
after they go out, and nothing warns this repository when that happens.

  --backfill   Post the Instagram-only stills to Facebook. Every candidate is
               checked against the live Instagram account first, so anything
               deleted since it published is skipped rather than mirrored.

  --reconcile  The other direction. Find Facebook posts whose Instagram twin
               has since been deleted, and (with --apply) delete them too, so
               the two accounts do not drift apart.

Both are read-only until --apply is passed. Without it they print exactly what
they would do and change nothing.

Why this is a separate script from publish.py: the every-two-minute tick has a
three-hour grace window and is deliberately blind to anything older. These two
operations are the opposite - they run rarely, they look at the whole history,
and they make a live API call per post to find out what is really there.

Usage:
  python3 scripts/facebook_sync.py --status
  python3 scripts/facebook_sync.py --backfill [--limit N] [--delay S] [--apply]
  python3 scripts/facebook_sync.py --reconcile [--apply]
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import publish  # noqa: E402  - shares the token, the Graph helper and the caption builder

ROOT = publish.ROOT


def load(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return json.load(f)


def live_ig_media(ig_user_id):
    """Every media id currently on the account.

    Paged deliberately rather than fetched per-post: at 122 posts the per-post
    version is 122 round trips, and a deleted id is an error response rather
    than a clean answer, which is harder to tell apart from a transient fault.
    """
    ids, after = set(), None
    while True:
        params = {"fields": "id", "limit": 100}
        if after:
            params["after"] = after
        page = publish.api(f"{ig_user_id}/media", params)
        ids.update(m["id"] for m in page.get("data", []))
        after = page.get("paging", {}).get("cursors", {}).get("after")
        if not after or not page.get("data"):
            return ids


def rows():
    """Join published records to their schedule entries, in posting order."""
    cfg = load("config/brands.json")
    sched = {e["id"]: e for e in load("state/schedule.json")["posts"]}
    order = {pid: i for i, pid in enumerate(sched)}
    pub = load("state/published.json")["posts"]
    out = []
    for rec in sorted(pub, key=lambda r: order.get(r["id"], 1 << 30)):
        entry = sched.get(rec["id"])
        if entry is None:
            continue  # published from a schedule that has since been rebuilt
        if not rec.get("ig_media_id"):
            continue  # never reached Instagram; publish.py still owns the retry
        brand = cfg["brands"].get(rec["brand"], {})
        out.append((rec, entry, brand))
    return cfg, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--reconcile", action="store_true")
    ap.add_argument("--apply", action="store_true", help="actually post/delete; otherwise dry")
    ap.add_argument("--limit", type=int, default=0, help="cap how many posts to mirror in one run")
    ap.add_argument("--delay", type=float, default=45.0,
                    help="seconds between Facebook posts during a backfill (default 45)")
    args = ap.parse_args()
    if not (args.status or args.backfill or args.reconcile):
        ap.error("pick one of --status, --backfill, --reconcile")
    if not publish.TOKEN:
        print("META_ACCESS_TOKEN is not set", file=sys.stderr)
        return 1

    cfg, joined = rows()
    tokens = cfg.get("tokens", {})

    # One media listing per account, reused by every check below.
    live = {}
    for _, _, brand in joined:
        ig = brand.get("ig_user_id")
        if ig and ig not in live:
            live[ig] = live_ig_media(ig)

    def is_live(rec, brand):
        ids = live.get(brand.get("ig_user_id"), set())
        return rec.get("ig_media_id") in ids

    pub_path = os.path.join(ROOT, "state", "published.json")
    published = load("state/published.json")

    def flush():
        with open(pub_path, "w", encoding="utf-8") as f:
            json.dump(published, f, indent=2, ensure_ascii=False)
            f.write("\n")

    # ---------------------------------------------------------------- status
    if args.status:
        print(f"{'id':<8} {'instagram':<10} {'facebook':<10} product")
        gone = mirrored = only_ig = 0
        for rec, entry, brand in joined:
            ig_state = "live" if is_live(rec, brand) else "DELETED"
            fb_state = "posted" if rec.get("fb_post_id") else "-"
            if ig_state == "DELETED":
                gone += 1
            if rec.get("fb_post_id"):
                mirrored += 1
            elif ig_state == "live":
                only_ig += 1
            print(f"{rec['id']:<8} {ig_state:<10} {fb_state:<10} {entry.get('product','')}")
        print(f"\n{len(joined)} published, {gone} deleted from Instagram, "
              f"{mirrored} on Facebook, {only_ig} live on Instagram and awaiting Facebook")
        return 0

    # -------------------------------------------------------------- backfill
    if args.backfill:
        todo, skipped = [], []
        for rec, entry, brand in joined:
            if not brand.get("fb_page_id") or rec.get("fb_post_id"):
                continue
            (todo if is_live(rec, brand) else skipped).append((rec, entry, brand))

        for rec, entry, _ in skipped:
            print(f"SKIP  {rec['id']} deleted from Instagram - not mirrored ({entry.get('product','')})")
        if args.limit:
            todo = todo[:args.limit]
        if not todo:
            print(f"nothing to backfill ({len(skipped)} skipped as deleted)")
            return 0

        print(f"{len(todo)} post(s) to mirror to Facebook"
              f"{'' if args.apply else '  [dry run - pass --apply to post]'}")
        failures = 0
        for i, (rec, entry, brand) in enumerate(todo):
            page_id = brand["fb_page_id"]
            if not args.apply:
                print(f"DRY   {rec['id']} -> fb:{page_id}  {entry.get('product','')}")
                continue
            try:
                caption = publish.build_caption(entry, tokens)
                post_id = publish.publish_facebook(entry, page_id, caption)
                rec_live = next(r for r in published["posts"] if r["id"] == rec["id"])
                rec_live["fb_post_id"] = post_id
                rec_live["fb_page_id"] = page_id
                rec_live["fb_published_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                rec_live["fb_backfilled"] = True
                flush()
                print(f"OK    {rec['id']} -> fb:{page_id} post {post_id}")
            except Exception as exc:
                failures += 1
                print(f"FAIL  {rec['id']}: {exc}", file=sys.stderr)
            # Spacing matters here: a hundred photos posted to a Page inside a
            # minute is a cheap thing for spam heuristics to spot, and this is
            # the one run that would do exactly that.
            if i + 1 < len(todo) and args.delay:
                time.sleep(args.delay)
        return 1 if failures else 0

    # ------------------------------------------------------------- reconcile
    orphans = [(rec, entry, brand) for rec, entry, brand in joined
               if rec.get("fb_post_id") and not is_live(rec, brand)]
    if not orphans:
        print("Facebook and Instagram agree - no post is live on one and deleted on the other")
        return 0

    print(f"{len(orphans)} Facebook post(s) whose Instagram twin has been deleted"
          f"{'' if args.apply else '  [dry run - pass --apply to delete]'}")
    failures = 0
    for rec, entry, brand in orphans:
        if not args.apply:
            print(f"DRY   would delete fb:{rec['fb_post_id']}  {rec['id']}  {entry.get('product','')}")
            continue
        try:
            publish.api(rec["fb_post_id"], method="DELETE",
                        token=publish.page_token(rec["fb_page_id"]))
            rec_live = next(r for r in published["posts"] if r["id"] == rec["id"])
            rec_live["fb_deleted_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            rec_live.pop("fb_post_id", None)
            flush()
            print(f"OK    deleted fb post for {rec['id']}  {entry.get('product','')}")
        except Exception as exc:
            failures += 1
            print(f"FAIL  {rec['id']}: {exc}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
