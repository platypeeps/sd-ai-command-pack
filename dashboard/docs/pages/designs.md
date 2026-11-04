# Designs

Designs is at `/designs` (sd:2126): the design's lamps, filter and ledger
over every drawn page in the ui-design checkout, grouped by product, plus one
row per product with a brief and no page. `GET /api/designs`
(`designs.ledger`) is the document the design's `data/designs-data.js` holds,
read live: each page's kind, title, size and last commit, its screenshots and
which of them are stale, and whether the working tree changed it. Details
opens the page and its 1440 px screenshot at `/designs/<path>`, where the tab
serves them sandboxed, as before. Read brief is copy only: the dashboard runs
no git, no `shots.mjs` and no pager.
Each row's act is Hide, or Unhide under Show hidden (sd:5457). History and
Retake screenshots are gone (sd:5530): the operator takes both by hand.
The filters are Activity's bar (sd:5463): the state as a segment with its
counts, the product as a pick, Show hidden as a toggle that lists the hidden
rows instead (sd:5753; it was the Hidden view, and `#view=hidden`,
`?show=hidden` and `?f=hidden` links land on it as `?hidden=1`), a pressed
lamp and the query as tokens, then Clear all; the count sits on the title line.
The lamp row starts with Open (sd:7361): it counts the rows not hidden, as
the bar's Open does, and pressing it sets that same Open filter. It is no
predicate of its own, so `?f=` never names it. It is pressed when the bar's
Open is, the URL keeps `?hidden=1` for Hidden and nothing for Open, and a
second press changes nothing, Open being the default. The other lamps count
the rows the current view shows.
Changed: Any | 7 d | 30 d (sd:7361) is a segment after the state. It keeps
the rows whose last commit is under that many days old, counted from the
reading as the Changed 7 d lamp counts. A row with no commit, such as a
brief-only product, leaves while an age is set. It combines with the lamps,
Open | Hidden, the state, the product and the query, shows as a token, and
Clear all drops it. The URL keeps `?age=7` or `?age=30`; Any writes nothing,
and any other value is ignored. The Changed 7 d lamp is unchanged.
Observed rereads `/api/designs`. The page reads through the shell's reader,
`read.js`. The old listing was retired in sd:3402.
