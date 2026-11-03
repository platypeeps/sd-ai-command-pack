# Today

Today is the first page, at `/` and `/today`: the same
`/api/now` rows the classic Now drew, as an annunciator and a ranked ledger. Its
capture is the shell's, as on every page: a task or followup through `POST /api/items`,
a note on the selected item through `POST /api/items/<id>/notes`.
It reads `/api/now` through the shell's reader (`read.js`): of two refreshes
only the newer one draws, and a failed read clears every row and its commands.
Status mail, backups, HOA water and Wants you wait for collectors.
Snooze hides a row until the next 08:00, for 1 hour or for 1 week, chosen in its
dialog (sd:3450); it posts
`/api/snooze`, and the row waits under Snoozed with an Unsnooze (sd:1896).
A row whose problem reads otherwise shows again before its time.
Your work lists the items `sd today` lists, from the same `/api/now` document; each row has the same Snooze,
keyed `today:item:<id>`, and the item shows again early when its status or due date changes (sd:3271).
`sd today` still lists a snoozed item.
Retry on a failed or interrupted job posts `/api/jobs/<job>/retry` with the job's revision from the same read, as
Management does (sd:3386); a job that changed since is refused and Now is read again.
After exit 127, command not found, Retry asks first and names the exit (sd:3392).
A job row also has Show log, which opens the job on Management > Schedules, and Print, the `launchctl print` line to
copy; Print is the row's act after exit 127. Both are the declarations Management and Activity use (sd:3449).

## Queue view

The Queue view (`#view=queue`, key q, pack sd:7234) holds what Queue's Overview, Today's Queues and In motion
showed. `/queue` answers 301 to it; `/queue?show=all` opens it with Ended builds on. An old `#view=queues` or
`#view=motion` link opens it too.

It has one row per repo, all closed. A click opens a repo's rows under it and closes the one that was open; a click
on the open repo closes it. The rows, in order:

- working: the live items of `/api/now` (a worktree, a lane entry, a running `sd-*` command, a herdr agent or a Fix
  note, pack sd:3466), the open build runs of `GET /api/queue/builds?show=all` (`builds.panel`: working, waiting,
  stalled or lost), a builder's gate in the lane, and the runner's queued and running assignments no run holds
  (`GET /api/queue/runner`, pack sd:7115 and sd:7217);
- merging, next and blocked: the lane entries of `GET /api/queue` (`queue_screen.document`);
- suggested: each repo's ready items from the `/api/now` queues rows, at most three (pack sd:7222);
- ended: ended build runs, and the cancelled and landed lane entries.

Each row's marker is its state glyph and its type in words; a repo's glyph is its worst row's.
A repo row's detail holds three boxes, merging, next and blocked, as Queue's lane ledger drew them (pack sd:7272).
They count all the repo's rows of those types, so a filter hides no count. A box is lit only when its count is not
zero; blocked lights the warning lamp; the cell's label says all three in words. A repo whose lane was not read says
"lane not read" in place of the boxes, not 0.
Suggested and Ended builds are off by default. On, a repo that has only those rows shows too, and `?show=` keeps them.
The view reads its three documents when it first shows, on each Today read after, and every 30 s while it shows.
A source that was not read is named under the table.

A live row's click shows its Details with Open item, Show assignment and Fix (sd:6714).
Up, down, top, hold, release and cancel, a blocked row's Retry and Approve, a cancelled row's Re-queue and a running
row's Release post `/api/queue/move`, which runs `sd-ship lane move|hold|release|cancel|retry` and nothing else.
Each write carries the revision, head or claim the view showed, and the verb checks it again under the queue's lock,
so a stale write is refused (409). A failure that is not a refusal answers 502 with an unknown outcome, and the view
reads the lane again. The full rules are in `queue_screen`'s docstring.
A build run's Cancel asks first and posts `/api/assignments/<id>/cancel`; an ended blocked or cancelled bundle's Retry
and Send to builder post `/api/queue/builds/retry` (pack sd:6020).
Queue's Last 7 days moved to Metrics' Lane times view (pack sd:7233).
