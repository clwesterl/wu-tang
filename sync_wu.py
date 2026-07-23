#!/usr/bin/env python3
"""
sync_wu.py — fill the Wu-Tang credit map's tracks and appearances.

Merge order, last writer wins:
    1. spine.json            hand-maintained releases (never touched by this script)
    2. Discogs               tracklist, positions, durations, release metadata
    3. Genius                per-track roster: featured artists, producers, writers
    4. manual_overrides.json your corrections — applied last, never clobbered

Anything the two sources disagree about goes to review_queue.json instead of
being silently merged. That queue is where uncredited guest verses live.

Env:
    DISCOGS_TOKEN     personal access token
    GENIUS_TOKEN      client access token

Usage:
    python sync_wu.py --all
    python sync_wu.py --release liquid-swords
    python sync_wu.py --release liquid-swords --dry-run
"""

import argparse, json, os, re, sys, time, unicodedata
from pathlib import Path
from urllib.parse import quote

import requests

HERE = Path(__file__).parent
SPINE = HERE / "spine.json"
OVERRIDES = HERE / "manual_overrides.json"
OUT = HERE / "data.json"
REVIEW = HERE / "review_queue.json"

DISCOGS_TOKEN = os.environ.get("DISCOGS_TOKEN", "")
GENIUS_TOKEN = os.environ.get("GENIUS_TOKEN", "")
UA = "WuCreditMap/0.1 +https://github.com/clwesterl"

# Discogs allows 60 authenticated req/min; Genius is undocumented, be polite.
DISCOGS_SLEEP = 1.1
GENIUS_SLEEP = 0.4


# ---------------------------------------------------------------- utilities
def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    return re.sub(r"[\s_-]+", "-", s) or "untitled"


def norm_title(s: str) -> str:
    """Loose key for joining a Discogs track to a Genius song."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\(feat[^)]*\)|\[feat[^\]]*\]", "", s)      # drop feature parens
    s = re.sub(r"\b(interlude|skit|intro|outro)\b", "", s)
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


def get(url, **kw):
    for attempt in range(4):
        r = requests.get(url, timeout=30, **kw)
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", 5)) * (attempt + 1)
            print(f"   rate limited, sleeping {wait}s", file=sys.stderr)
            time.sleep(wait)
            continue
        if r.ok:
            return r
        if r.status_code == 404:
            return None
        r.raise_for_status()
    return None


# ------------------------------------------------------------------ discogs
def discogs_find_release(title, artist_name, year):
    """Prefer the master release so we get the canonical tracklist."""
    r = get(
        "https://api.discogs.com/database/search",
        params={"release_title": title, "artist": artist_name, "type": "master",
                "token": DISCOGS_TOKEN},
        headers={"User-Agent": UA},
    )
    time.sleep(DISCOGS_SLEEP)
    if not r:
        return None
    results = r.json().get("results", [])
    if not results:
        return None
    # nearest year wins; Discogs search relevance is unreliable for reissues
    results.sort(key=lambda x: abs(int(x.get("year") or 0) - year) if x.get("year") else 999)
    return results[0]


def discogs_tracklist(master_id):
    r = get(f"https://api.discogs.com/masters/{master_id}",
            params={"token": DISCOGS_TOKEN}, headers={"User-Agent": UA})
    time.sleep(DISCOGS_SLEEP)
    if not r:
        return [], []
    body = r.json()
    tracks, extra = [], []
    pos = 0
    for t in body.get("tracklist", []):
        if t.get("type_") and t["type_"] != "track":
            continue                                    # skip headings/indexes
        pos += 1
        tracks.append({
            "position": pos,
            "title": t.get("title", "").strip(),
            "duration": t.get("duration") or None,
        })
        # Discogs sometimes carries track-level credits. Coverage is uneven,
        # but when it's there it's usually right, so keep it.
        for ea in t.get("extraartists", []) or []:
            extra.append({
                "position": pos,
                "name": ea.get("name", "").strip(),
                "role": ea.get("role", "").strip(),
            })
    return tracks, extra


DISCOGS_ROLE_MAP = {
    "producer": "producer", "co-producer": "producer",
    "featuring": "performer", "vocals": "performer", "rap": "performer",
    "scratches": "scratches", "dj mix": "scratches",
    "written-by": "writer", "songwriter": "writer",
}


def map_discogs_role(role):
    key = re.sub(r"\[.*?\]", "", role).strip().lower()
    return DISCOGS_ROLE_MAP.get(key)


# ------------------------------------------------------------------- genius
def genius_search(title, artist_name):
    r = get("https://api.genius.com/search",
            params={"q": f"{artist_name} {title}"},
            headers={"Authorization": f"Bearer {GENIUS_TOKEN}", "User-Agent": UA})
    time.sleep(GENIUS_SLEEP)
    if not r:
        return None
    want = norm_title(title)
    for hit in r.json().get("response", {}).get("hits", []):
        song = hit.get("result", {})
        if norm_title(song.get("title", "")) == want:
            return song
    return None


def genius_song(song_id):
    r = get(f"https://api.genius.com/songs/{song_id}",
            headers={"Authorization": f"Bearer {GENIUS_TOKEN}", "User-Agent": UA})
    time.sleep(GENIUS_SLEEP)
    return r.json().get("response", {}).get("song") if r else None


def genius_roster(song):
    """Structured credits only. Verse order is NOT in the API — it lives in the
    lyrics page section headers, which is a scrape, not an API call. Left out
    deliberately; see notes at the bottom of this file."""
    out = []
    for a in song.get("featured_artists", []) or []:
        out.append((a["name"], "performer"))
    for a in song.get("producer_artists", []) or []:
        out.append((a["name"], "producer"))
    for a in song.get("writer_artists", []) or []:
        out.append((a["name"], "writer"))
    for perf in song.get("custom_performances", []) or []:
        label = (perf.get("label") or "").lower()
        role = ("producer" if "produc" in label
                else "scratches" if "scratch" in label
                else "performer" if any(k in label for k in ("vocal", "rap", "feat"))
                else None)
        if role:
            for a in perf.get("artists", []) or []:
                out.append((a["name"], role))
    return out


# --------------------------------------------------------------------- sync
def sync(spine, only=None, dry=False):
    artists = {a["id"]: a for a in spine["artists"]}
    name_to_id = {a["name"].lower(): a["id"] for a in spine["artists"]}
    for a in spine["artists"]:
        for k in a.get("aka", []):
            name_to_id.setdefault(k.lower(), a["id"])

    tracks, appearances, review = [], [], []

    for rel in spine["releases"]:
        if only and rel["id"] != only:
            continue
        if rel["kind"] == "unreleased":
            continue

        lead = artists.get(rel["artist_id"], {}).get("name", "")
        print(f"→ {rel['title']} ({rel['year']})")

        found = discogs_find_release(rel["title"], lead, rel["year"])
        if not found:
            review.append({"release": rel["id"], "issue": "no discogs master found"})
            print("   ! no discogs match")
            continue
        rel["discogs_id"] = found["id"]

        dtracks, dextra = discogs_tracklist(found["id"])
        if not dtracks:
            review.append({"release": rel["id"], "issue": "discogs master has no tracklist"})
            continue

        extra_by_pos = {}
        for e in dextra:
            extra_by_pos.setdefault(e["position"], []).append(e)

        for dt in dtracks:
            tid = f"{rel['id']}--{slug(dt['title'])}"
            tracks.append({
                "id": tid, "release_id": rel["id"],
                "position": dt["position"], "title": dt["title"],
                "duration": dt["duration"],
            })

            seen = set()

            def add(name, role, note=None):
                aid = name_to_id.get(name.lower())
                if not aid:
                    aid = slug(name)
                    if aid not in artists:                # auto-create guests
                        artists[aid] = {"id": aid, "name": name, "aka": [],
                                        "type": "mc", "tier": "guest"}
                        name_to_id[name.lower()] = aid
                key = (aid, role)
                if key in seen:
                    return
                seen.add(key)
                appearances.append({"track_id": tid, "artist_id": aid, "role": role,
                                    "slot": None, "credited": True, "note": note})

            # the lead artist is on their own track unless proven otherwise
            if rel["kind"] in ("solo", "group"):
                add(lead, "performer")

            for e in extra_by_pos.get(dt["position"], []):
                role = map_discogs_role(e["role"])
                if role:
                    add(e["name"], role, note="discogs")

            gsong = genius_search(dt["title"], lead)
            if gsong:
                full = genius_song(gsong["id"]) or gsong
                groster = genius_roster(full)
                for name, role in groster:
                    add(name, role, note="genius")

                # discrepancy detection — this is the useful part
                d_names = {e["name"].lower() for e in extra_by_pos.get(dt["position"], [])}
                g_names = {n.lower() for n, _ in groster}
                only_genius = g_names - d_names - {lead.lower()}
                if only_genius:
                    review.append({
                        "release": rel["id"], "track": tid, "title": dt["title"],
                        "issue": "on genius but not in discogs credits",
                        "names": sorted(only_genius),
                    })
            else:
                review.append({"release": rel["id"], "track": tid,
                               "title": dt["title"], "issue": "no genius match"})

    spine["artists"] = list(artists.values())
    return tracks, appearances, review


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--release")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.all and not args.release:
        ap.error("pass --all or --release <id>")
    for var, val in (("DISCOGS_TOKEN", DISCOGS_TOKEN), ("GENIUS_TOKEN", GENIUS_TOKEN)):
        if not val:
            sys.exit(f"{var} is not set")

    spine = json.loads(SPINE.read_text())
    tracks, appearances, review = sync(spine, only=args.release, dry=args.dry_run)

    data = {
        "meta": {"generated": time.strftime("%Y-%m-%d"), "credits_verified": False},
        "artists": spine["artists"],
        "releases": spine["releases"],
        "tracks": tracks,
        "appearances": appearances,
    }

    # ---- overrides last, and they win outright -------------------------
    if OVERRIDES.exists():
        ov = json.loads(OVERRIDES.read_text())
        for tr in ov.get("tracks", []):
            data["tracks"] = [t for t in data["tracks"] if t["id"] != tr["id"]] + [tr]
        # a track listed in overrides has its scraped appearances discarded
        # entirely, so a manual entry is never half-merged with a bad scrape
        owned = {a["track_id"] for a in ov.get("appearances", [])}
        data["appearances"] = [a for a in data["appearances"] if a["track_id"] not in owned]
        data["appearances"] += ov.get("appearances", [])
        for rid in ov.get("drop_releases", []):
            data["releases"] = [r for r in data["releases"] if r["id"] != rid]

    data["tracks"].sort(key=lambda t: (t["release_id"], t["position"]))

    if args.dry_run:
        print(json.dumps({"tracks": len(data["tracks"]),
                          "appearances": len(data["appearances"]),
                          "review": len(review)}, indent=2))
        return

    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    REVIEW.write_text(json.dumps(review, indent=1, ensure_ascii=False))
    SPINE.write_text(json.dumps(spine, indent=1, ensure_ascii=False))
    print(f"\n{len(data['tracks'])} tracks, {len(data['appearances'])} appearances, "
          f"{len(review)} items for review")


if __name__ == "__main__":
    main()

# ---------------------------------------------------------------------------
# On verse order, since you'll come back to this:
#
# The Genius API returns who is on a song but not who raps when. Verse
# attribution lives in the bracketed section headers of the lyrics page
# ([Verse 2: Raekwon]), which means fetching the HTML and regexing
# r'^\[([^\]]+)\]' out of it, keeping the bracket contents and discarding every
# line between them. Your JSON then never contains a lyric, which is both a
# smaller file and a cleaner posture with respect to Genius's terms.
#
# Known snags when you do: multi-name brackets that need splitting on & , +
# and "with"; unattributed [Verse 2] with no colon; ad-libs that never appear
# in a header at all; numbering that restarts mid-posse-cut.
# ---------------------------------------------------------------------------
