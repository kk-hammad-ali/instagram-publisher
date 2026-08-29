#!/usr/bin/env python3
"""Publish any post that is due, then record it.

Run on a cron. Everything due at or before "now" (minus a grace window) that has
not already gone out gets published; everything else is left alone.

Two publishing paths, because Instagram treats the media types differently:

  IMAGE  - the API fetches the file itself, so the JPEG must sit at a public
           HTTPS URL. Google Drive share links do not work here; Drive answers
           with an HTML interstitial rather than image bytes.
  REELS  - supports resumable upload, so the file is pushed straight from this
           runner. No hosting needed for the videos at all.

A brand carrying "fb_page_id" is mirrored to its Facebook Page in the same tick,
from the same MEDIA_BASE_URL. The two platforms are tracked separately in
state/published.json - one record per post, with an ig_media_id and an
fb_post_id - so a failure on one does not block or re-fire the other.

Facebook only applies from the brand's "fb_start_date". Posts older than that
went out on Instagram alone and belong to scripts/facebook_sync.py --backfill,
which checks each is still live on Instagram before mirroring it. Without that
cut-off the tick would re-examine all of them every two minutes and log nothing
but grace-window skips.

Environment:
  META_ACCESS_TOKEN   required - system user token preferred (does not expire)
  MEDIA_BASE_URL      required for images - public HTTPS prefix for media/
  GRAPH_VERSION       optional - defaults to v23.0
  DRY_RUN=1           resolve accounts and validate, publish nothing
"""

import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRAPH = f"https://graph.facebook.com/{os.environ.get('GRAPH_VERSION', 'v23.0')}"
RUPLOAD = f"https://rupload.facebook.com/ig-api-upload/{os.environ.get('GRAPH_VERSION', 'v23.0')}"

TOKEN = os.environ.get("META_ACCESS_TOKEN", "").strip()
MEDIA_BASE = os.environ.get("MEDIA_BASE_URL", "").strip().rstrip("/")
# Reels are too large to keep in git, so they are published as GitHub Release
# assets and referenced by URL. When this is unset the resumable path is used
# instead, which uploads a local file - that is how local testing works.
REELS_BASE = os.environ.get("REELS_BASE_URL", "").strip().rstrip("/")
DRY = os.environ.get("DRY_RUN", "") not in ("", "0", "false")
# Brands listed here are held back: their posts are neither published nor
# reported late, and the rest of the queue carries on untouched. Set when one
# account needs to stop while another keeps running. Clearing the variable
# resumes, but slots that passed while paused are outside the grace window by
# then - rebuild the schedule to re-date them rather than expecting a catch-up.
PAUSED = {b.strip().lower() for b in os.environ.get("PAUSED_BRANDS", "").split(",") if b.strip()}

# A post is published if it is due now or fell due within this window. Anything
# older is skipped rather than fired late - GitHub Actions cron can be delayed,
# and a runner that was down for a day should not wake up and dump six posts.
GRACE = timedelta(hours=3)


def api(path, params=None, data=None, method=None, timeout=120, token=None):
    # token overrides the system user token. Page endpoints want a Page access
    # token, which is fetched once per run by page_token() below.
    tok = token or TOKEN
    url = f"{GRAPH}/{path.lstrip('/')}"
    params = dict(params or {})
    params["access_token"] = tok
    body = None
    if data is not None:
        payload = dict(data)
        payload["access_token"] = tok
        body = urllib.parse.urlencode(payload).encode()
    else:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, data=body, method=method or ("POST" if body else "GET"))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise RuntimeError(f"Graph API {e.code} on {path}: {detail}") from None


def resolve_accounts():
    """Map each Facebook Page to the Instagram account linked to it."""
    out = {}
    pages = api("me/accounts", {"fields": "id,name,instagram_business_account{id,username}"})
    for page in pages.get("data", []):
        ig = page.get("instagram_business_account")
        if ig:
            out[ig["username"].lower()] = {
                "ig_id": ig["id"],
                "page": page["name"],
                "page_id": page["id"],
            }
    return out


def upload_reel(ig_id, path, caption):
    """Resumable upload: open a container, push the bytes, return the container.

    The caption goes in at creation time. A resumable container will not accept
    a later POST of its fields - that comes back as "does not support this
    operation" - so there is no second chance to attach it.
    """
    container = api(f"{ig_id}/media", data={
        "media_type": "REELS",
        "upload_type": "resumable",
        "caption": caption,
    })
    cid = container["id"]

    size = os.path.getsize(path)
    with open(path, "rb") as f:
        body = f.read()

    req = urllib.request.Request(
        f"{RUPLOAD}/{cid}",
        data=body,
        method="POST",
        headers={
            "Authorization": f"OAuth {TOKEN}",
            "offset": "0",
            "file_size": str(size),
            "Content-Type": mimetypes.guess_type(path)[0] or "video/mp4",
        },
    )
    with urllib.request.urlopen(req, timeout=900) as r:
        r.read()
    return cid


def wait_ready(cid, timeout=900):
    """Poll until Instagram has finished ingesting the container."""
    deadline = time.time() + timeout
    delay = 5
    while time.time() < deadline:
        st = api(cid, {"fields": "status_code,status"})
        code = st.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"container {cid} -> {code}: {st.get('status')}")
        time.sleep(delay)
        delay = min(delay * 1.5, 30)
    raise RuntimeError(f"container {cid} not ready after {timeout}s")


_PAGE_TOKENS = {}


def page_token(page_id):
    """Fetch (and cache for this run) the Page access token for a Page.

    Page publishing will not accept the system user token directly. The Page
    token is derived from it, so it carries the same scopes and the same
    non-expiry, and it is never written to disk.
    """
    if page_id not in _PAGE_TOKENS:
        _PAGE_TOKENS[page_id] = api(page_id, {"fields": "access_token"})["access_token"]
    return _PAGE_TOKENS[page_id]


def publish_facebook(entry, page_id, caption):
    """Post one still to a Facebook Page and return its post id.

    /photos rather than /feed: /feed with a link renders a link preview card,
    /photos uploads the image as the post itself, which is what the Instagram
    side is doing. Meta fetches the URL, exactly as Instagram does, so this
    needs no hosting beyond MEDIA_BASE_URL.

    The response carries both an id (the photo) and a post_id (the Page post).
    post_id is the one that can be read back from /{page}/posts and deleted, so
    that is what gets recorded.
    """
    if entry["media_type"] != "IMAGE":
        raise RuntimeError(
            f"{entry['id']} is {entry['media_type']}; the Facebook path handles "
            f"IMAGE only. All 122 DK posts are stills - if that changes, add the "
            f"/videos endpoint here rather than letting this fall through."
        )
    if not MEDIA_BASE:
        raise RuntimeError("MEDIA_BASE_URL is not set; Facebook photo posts need a public HTTPS URL")
    res = api(f"{page_id}/photos", data={
        "url": f"{MEDIA_BASE}/{entry['media']}",
        "caption": caption,
        "published": "true",
    }, token=page_token(page_id))
    return res.get("post_id") or res["id"]


def facebook_page_for(entry, brands):
    """The Page id this post should mirror to, or None.

    None means "not Facebook's problem": the brand has no Page configured, or
    the post is scheduled before the brand started on Facebook and so belongs
    to the backfill instead.
    """
    cfg = brands.get(entry["brand"]) or {}
    page_id = cfg.get("fb_page_id")
    if not page_id:
        return None
    start = cfg.get("fb_start_date")
    if start and entry["publish_at_pkt"][:10] < start:
        return None
    return page_id


def build_caption(entry, tokens):
    text = entry["caption"]
    for k, v in tokens.items():
        # An empty value is left unsubstituted on purpose, so the placeholder
        # survives to trip the check below. Substituting "" would quietly ship
        # "WhatsApp  for the trade list." to 8.7k followers.
        if k.startswith("_") or not str(v).strip():
            continue
        text = text.replace("{{" + k + "}}", str(v))
    tags = entry.get("hashtags") or []
    if tags:
        text += "\n\n" + " ".join("#" + t for t in tags)
    if "{{" in text:
        leftover = text[text.index("{{"): text.index("{{") + 40]
        raise RuntimeError(f"unresolved placeholder in {entry['id']}: {leftover!r}")
    if len(text) > 2200:
        raise RuntimeError(f"caption for {entry['id']} is {len(text)} chars (limit 2200)")
    return text


def publish_one(entry, accounts, tokens):
    handle = entry["handle"].lower()
    # Prefer the id pinned in config. Page-based discovery only works when the
    # Facebook Page is assigned to the system user, and here only the Instagram
    # accounts are, so Page-based discovery returns nothing for DK.
    ig_id = entry.get("ig_user_id")
    if not ig_id:
        acct = accounts.get(handle)
        if not acct:
            raise RuntimeError(
                f"@{handle} is not reachable from this token and no ig_user_id "
                f"is pinned in config/brands.json. Visible via Pages: "
                f"{sorted(accounts) or 'none'}."
            )
        ig_id = acct["ig_id"]
    caption = build_caption(entry, tokens)
    path = os.path.join(ROOT, entry["media"])

    if entry["media_type"] == "REELS":
        if REELS_BASE:
            cid = api(f"{ig_id}/media", data={
                "media_type": "REELS",
                "video_url": f"{REELS_BASE}/{os.path.basename(entry['media'])}",
                "caption": caption,
            })["id"]
        else:
            if not os.path.exists(path):
                raise RuntimeError(
                    f"missing {entry['media']} and REELS_BASE_URL is not set - "
                    f"reels are not kept in git, so the runner needs the release URL"
                )
            cid = upload_reel(ig_id, path, caption)
        wait_ready(cid)
    else:
        if not os.path.exists(path):
            raise RuntimeError(f"missing media file: {entry['media']}")
        if not MEDIA_BASE:
            raise RuntimeError("MEDIA_BASE_URL is not set; image posts need a public HTTPS URL")
        cid = api(f"{ig_id}/media", data={
            "image_url": f"{MEDIA_BASE}/{entry['media']}",
            "caption": caption,
        })["id"]
        wait_ready(cid)

    res = api(f"{ig_id}/media_publish", data={"creation_id": cid})
    return res.get("id"), ig_id


def main():
    with open(os.path.join(ROOT, "config", "brands.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    tokens = cfg.get("tokens", {})
    brands = cfg.get("brands", {})

    sched_path = os.path.join(ROOT, "state", "schedule.json")
    with open(sched_path, encoding="utf-8") as f:
        sched = json.load(f)

    pub_path = os.path.join(ROOT, "state", "published.json")
    published = {"posts": []}
    if os.path.exists(pub_path):
        with open(pub_path, encoding="utf-8") as f:
            published = json.load(f)
    # One record per post id, carrying both platforms. Records written before
    # Facebook existed have no fb_post_id, which is exactly how the backfill
    # finds them.
    by_id = {e["id"]: e for e in published["posts"]}

    # --validate checks every queued post's caption and media up front, without
    # a token and without waiting for anything to fall due.
    if "--validate" in sys.argv:
        bad = 0
        for e in sched["posts"]:
            problems = []
            try:
                build_caption(e, tokens)
            except RuntimeError as exc:
                problems.append(str(exc))
            # Reels live as Release assets rather than in git, so on a CI
            # checkout their absence is expected once REELS_BASE_URL is set.
            served_remotely = e["media_type"] == "REELS" and REELS_BASE
            if not served_remotely and not os.path.exists(os.path.join(ROOT, e["media"])):
                problems.append(f"missing media {e['media']}")
            for p in problems:
                bad += 1
                print(f"FAIL  {e['id']}: {p}", file=sys.stderr)
        total = len(sched["posts"])
        print(f"{total - bad}/{total} posts valid" if bad else f"all {total} posts valid")
        return 1 if bad else 0

    now = datetime.now(timezone.utc)
    due, late, held = [], [], []
    todo = {}  # post id -> ["ig", "fb"], whichever it still owes
    for e in sched["posts"]:
        rec = by_id.get(e["id"])
        want = []
        if not (rec and rec.get("ig_media_id")):
            want.append("ig")
        if facebook_page_for(e, brands) and not (rec and rec.get("fb_post_id")):
            want.append("fb")
        if not want:
            continue
        when = datetime.strptime(e["publish_at_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if when > now:
            continue
        todo[e["id"]] = want
        # Held before the late check on purpose: a paused brand must not accrue
        # SKIP lines on every tick, and its posts stay unpublished either way.
        if e["brand"] in PAUSED:
            held.append(e)
        elif now - when <= GRACE:
            due.append(e)
        else:
            late.append(e)

    for e in late:
        print(f"SKIP  {e['id']} [{'+'.join(todo[e['id']])}] was due {e['publish_at_pkt']} PKT, "
              f"outside the {GRACE} grace window")

    # Appended to the nothing-due line rather than printed on its own, so the
    # wrapper's "nothing due" filter still keeps a paused brand out of the log.
    note = f" ({len(held)} held: {', '.join(sorted(PAUSED))})" if held else ""

    if not due:
        print(f"nothing due at {now:%Y-%m-%d %H:%M} UTC{note}")
        return 0

    if held:
        print(f"HELD  {len(held)} post(s) for paused brand(s): {', '.join(sorted(PAUSED))}")

    if not TOKEN:
        print("META_ACCESS_TOKEN is not set", file=sys.stderr)
        return 1

    # Informational only - every brand pins its ig_user_id, so a Page listing
    # that comes back short (or fails) is not fatal.
    try:
        accounts = resolve_accounts()
    except RuntimeError as exc:
        accounts = {}
        print(f"note: Page listing unavailable ({exc}); using pinned ig_user_ids")
    print(f"via Pages: {', '.join('@' + h for h in sorted(accounts)) or 'none'}; "
          f"pinned: {', '.join(sorted({e['handle'] for e in due if e.get('ig_user_id')}))}")

    if DRY:
        for e in due:
            caption = build_caption(e, tokens)
            targets = [f"@{e['handle']}" if t == "ig" else f"fb:{facebook_page_for(e, brands)}"
                       for t in todo[e["id"]]]
            print(f"DRY   {e['id']} -> {' + '.join(targets)} ({e['media_type']}) "
                  f"{len(caption)} chars, {e['media']}")
        return 0

    failures = 0
    for e in due:
        rec = by_id.get(e["id"])
        # A brand-new record is held back until something actually publishes.
        # Appending it up front would leave an id-less stub behind whenever
        # Instagram fails, and facebook_sync.py reads a record with no
        # ig_media_id as a post that was deleted from the account.
        fresh = rec is None
        if fresh:
            rec = {
                "id": e["id"],
                "brand": e["brand"],
                "handle": e["handle"],
                "scheduled_pkt": e["publish_at_pkt"],
            }

        # Each platform is attempted independently and recorded the moment it
        # succeeds. A post that reaches Instagram and then fails on Facebook
        # keeps its ig_media_id, so the retry two minutes later posts only the
        # Facebook half - the one failure here that cannot be undone is a
        # duplicate, and this is what prevents it.
        for target in todo[e["id"]]:
            try:
                caption = build_caption(e, tokens)
                if target == "ig":
                    media_id, ig_id = publish_one(e, accounts, tokens)
                    rec["ig_media_id"] = media_id
                    rec["ig_user_id"] = ig_id
                    rec["published_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    print(f"OK    {e['id']} -> @{e['handle']} media {media_id}")
                    if fresh:
                        by_id[e["id"]] = rec
                        published["posts"].append(rec)
                        fresh = False
                else:
                    page_id = facebook_page_for(e, brands)
                    post_id = publish_facebook(e, page_id, caption)
                    rec["fb_post_id"] = post_id
                    rec["fb_page_id"] = page_id
                    rec["fb_published_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    print(f"OK    {e['id']} -> fb:{page_id} post {post_id}")
                    if fresh:
                        by_id[e["id"]] = rec
                        published["posts"].append(rec)
                        fresh = False
            except Exception as exc:  # keep going; one bad post must not stall the queue
                failures += 1
                print(f"FAIL  {e['id']} [{target}]: {exc}", file=sys.stderr)
                # Instagram failing means there is nothing to mirror yet.
                if target == "ig":
                    break

        # Flushed inside the loop, not after it: a crash or a launchd kill
        # between two posts must not lose the ids of the ones already out.
        with open(pub_path, "w", encoding="utf-8") as f:
            json.dump(published, f, indent=2, ensure_ascii=False)
            f.write("\n")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
