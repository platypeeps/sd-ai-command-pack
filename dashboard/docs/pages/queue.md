# Queue

Queue is at `/queue` (sd:2585): each managed repository's `sd-ship lane`,
one row per item as merging, next, building, blocked, cancelled or landed.
`GET /api/queue` (`queue_screen.document`) runs `sd-ship -C <repo> lane list`
per repository, reads the builder gate logs in the lane folder, the gate slots
from `sd gate status --json` and the machine's load. A lane hosted on another
machine still gets its section, from the hub's queue. An item that is done
in the database, cancelled included, is never a blocked row, even when its
newest lane entry failed (sd:5847). Up, down, top, hold,
release and cancel, a blocked row's Retry and Approve, a cancelled row's
Re-queue and a running row's Release post `/api/queue/move`, which runs
`sd-ship lane move|hold|release|cancel|retry` and nothing else. Each write
carries the revision, head or claim the page showed, and the verb checks it
again under the queue's lock, so a stale write is refused (409). A failure
that is not a refusal answers 502 with an unknown outcome, and the page reads
the lane again. The full rules are in `queue_screen`'s docstring.
Overview lists the runner's queued and running assignments under Builds,
from `GET /api/queue/runner` (`queue_screen.runner`, pack sd:7115). Pack
sd:7217 retired their own Assignments view: its Waiting on you list repeated
Writing's pieces at `ready_to_send`. An old `#view=assignments` link opens
Overview.
Last 7 days moved to Metrics' Lane times view (pack sd:7233).
