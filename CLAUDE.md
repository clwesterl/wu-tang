# CLAUDE.md

Wu-Tang Credit Map — a static site that answers "who is on what" across the Wu
catalog. Click a rapper, get every track they touch; click a release, get its
tracklist; click a track, get everyone credited on it.

Repo: `clwesterl/wu-tang` · served by GitHub Pages from the repo root.

## Architecture

Same pattern as Two Spins and Now Jazz Now, with one deliberate difference:
**this repo is public and the data file is read with a plain `fetch()`.** There
is no PAT, no GitHub Contents API, no write path from the browser. The site is
read-only; all writes happen locally through `sync_wu.py`.

No build step. No bundler. Open `index.html` over HTTP and it works.

```
spine.json ──┐
             ├─► sync_wu.py ──► data.json ──► index.html
Discogs API ─┤                     ▲
Genius API ──┘                     │
manual_overrides.json ─────────────┘  (applied last, wins outright)
```

## Files

| File | Owner | Edit by hand? |
|---|---|---|
| `spine.json` | you | **yes** — this is the one you curate |
| `manual_overrides.json` | you | **yes** — corrections that survive re-syncs |
| `data.json` | `sync_wu.py` | **no** — regenerated every run, edits are lost |
| `review_queue.json` | `sync_wu.py` | no — read it, act on it, don't edit it |
| `index.html` | you | yes — viewer only, holds no data |
| `sync_wu.py` | you | yes |

## Data model

A tripartite graph. One join table does all the work.

```
artist ←── appearance ──► track ──► release
```

- **artists** — `id, name, aka[], type (mc|group), tier (core|affiliate|guest)`
  `tier: "guest"` is assigned automatically by the sync when it meets a name
  that isn't in the spine. That's intended; don't pre-populate guests by hand.
- **releases** — `id, title, artist_id, year, label, kind, discogs_id`
  `kind` = `group | solo | collab | soundtrack | unreleased`.
  The sync skips `unreleased`.
- **tracks** — `id, release_id, position, title, duration`
  Track IDs are `{release_id}--{slug(title)}`, generated. Don't invent them.
- **appearances** — `track_id, artist_id, role, slot, credited, note`
  - `role` = `performer | hook | producer | writer | scratches | skit | sample`
  - `slot` = verse number for performers, `null` otherwise
  - `credited: false` marks an uncredited guest verse — very common on Wu
    records and the whole reason the review queue exists

## Invariants

Break these and things go quietly wrong rather than loudly wrong:

1. **`data.json` is generated.** If you find yourself editing it, you want
   `manual_overrides.json` instead.
2. **Overrides replace, they don't merge.** If a `track_id` appears in the
   overrides' `appearances`, *every* scraped appearance for that track is
   dropped first. Half-merging a hand-fixed track with a bad scrape produces a
   file that looks right and isn't.
3. **The viewer never writes.** If a feature seems to need a write path,
   it belongs in the sync script.
4. **Production is excluded from the co-appearance matrix.** `ON_MIC` in
   `index.html` is the switch. Including RZA's board work makes his row solid
   gold and tells you nothing.
5. **The lead artist is auto-added as a performer** on solo and group releases.
   Wrong for skits and instrumentals — those get fixed via overrides.

## Commands

```bash
# serve locally — required, file:// will fail CORS on the fetch
python3 -m http.server 8000

# sync one release while iterating
python3 sync_wu.py --release liquid-swords

# see what a run would produce without writing
python3 sync_wu.py --release liquid-swords --dry-run

# full run — slow, rate-limited, expect 30+ minutes for 80 releases
python3 sync_wu.py --all
```

Needs `DISCOGS_TOKEN` and `GENIUS_TOKEN` in the environment. Both are read-only
tokens; neither is in the repo.

## Known state / caveats

- **Verse order (`slot`) is unverified everywhere.** The 36 Chambers seed was
  hand-entered from memory. Participants are probably right; verse *ordering*
  is guesswork. Don't build analysis on `slot` until it's checked.
- **Verse order is not in the Genius API.** It lives in the bracketed section
  headers of the lyrics page (`[Verse 2: Raekwon]`), which is a scrape, not an
  API call. If implemented: keep only the bracket contents, discard every line
  between them, so no lyrics ever enter the repo. Snags — multi-name brackets
  needing splits on `&` `,` `+` `with`; unattributed `[Verse 2]`; ad-libs that
  never appear in a header; numbering that restarts mid-posse-cut.
- **Spine years and labels are from memory.** The sync overwrites `discogs_id`
  but not year/label. A verification pass against Discogs is unwritten.
- **Discogs track-level `extraartists` coverage is uneven** for hip-hop. Genius
  is the better source for features. Discogs is the better source for
  tracklists and durations. The script uses each for what it's good at.
- **`review_queue.json` is the interesting output**, not an error log. Entries
  reading "on genius but not in discogs credits" are candidate uncredited
  verses. Expect a lot from *Liquid Swords* and *Ironman*.

## Conventions

- Single-file viewer. CSS and JS stay inline in `index.html`.
- Palette is fixed in `:root` — aged brass `#C8A227` on `#0B0B0C`, bone `#E6E1D3`
  body text, `#8C1C13` reserved for production credits and warnings only.
- Type: Big Shoulders Display / Archivo / IBM Plex Mono.
- Hash routing: `#/artist/:id`, `#/release/:id`, `#/track/:id`, `#/matrix`.
  Every view is linkable; keep it that way.
