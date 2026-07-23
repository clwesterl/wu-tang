# TASKS.md

Working state for `clwesterl/wu-tang`. Update this at the end of a session, not
the start — the point is that the next session (or the other machine) can pick
up without re-deriving context.

---

## Now

- [ ] **First real sync run.** Start with one release to check the join before
      burning rate limit on all 84:
      `python3 sync_wu.py --release liquid-swords --dry-run`
      Then without `--dry-run`, then read `review_queue.json` before going wider.
- [ ] **Check the Discogs match logic.** `discogs_find_release` sorts by nearest
      year against the master search. Reissue-heavy artists may match wrong.
      Spot-check five releases, especially the Def Jam-era Ghostface run.
- [ ] **Verify the 36 Chambers seed.** Participants are probably right, verse
      order is guesswork. Liner notes or Genius; then move the corrections into
      `manual_overrides.json` so the sync can't undo them.

## Next

- [ ] Spine verification pass — years and labels are from memory. Consider
      having the sync write back Discogs' year/label to a `spine_diff.json`
      rather than overwriting, so you can review before accepting.
- [ ] Verse order from Genius section headers. See CLAUDE.md for the approach
      and the known snags. Headers only, never lyrics.
- [ ] Matrix improvements once coverage is real:
      - sort rows by total appearances instead of spine order
      - toggle to include production
      - filter to a date range (the Rae/Ghost cell should change shape by era)
- [ ] Guest tier is currently a flat bucket. Once the sync has run, there will
      be a long tail (Redman, Cappadonna pre-membership, Killa Bees). Decide
      whether to promote frequent guests to `affiliate`.

## Later / maybe

- [ ] Killa Bee extended universe: Killarmy, Sunz of Man, Shyheim, Streetlife,
      La the Darkman, Royal Fam. `tier` already supports it; it's a spine
      expansion, not a rebuild.
- [ ] Producer view — RZA vs Mathematics vs 4th Disciple vs outside boards.
      The data supports it already; nothing in the UI surfaces it.
- [ ] Cross-reference against the Discogs collection to mark what's owned,
      the way Now Jazz Now does. Would need the collection export.
- [ ] "GZA tracks not produced by RZA" style queries. Probably a saved-query
      panel rather than a general query builder.

## Done

- [x] Schema designed and shaken out against real data (36 Chambers seed).
- [x] Three-chamber drill-down viewer with hash routing.
- [x] Co-appearance matrix, on-mic only, click-through to shared tracks.
- [x] Release spine — 84 titles, core ten plus Gravediggaz and Czarface.
- [x] Sync script with Discogs → Genius → overrides merge order and a
      discrepancy review queue.
- [x] Split into `spine.json` / `data.json` / `manual_overrides.json`; viewer
      is now pure and holds no data.

---

## Open questions

- Should `data.json` be committed, or generated on a GitHub Action? Committed
  for now — it's the only thing making the Pages site work, and it's small.
  Revisit if it gets past a few MB.
- Cappadonna's discography is longer than what's in the spine and the
  boundaries are fuzzy (mixtapes, indie releases). Currently six entries.
- No decision yet on whether soundtrack releases (`Ghost Dog`, `Afro Samurai`)
  should count toward the coverage meter. They inflate the denominator and
  aren't really credit-graph material.
