# Work

Each directory here is one work item: `<YYYY-MM-DD>-<slug>/design.md`.
Write it only when the shape needs agreement before the code.
The item's sd row holds status, progress and decisions.
Older items keep their `prd.md` and `implement.md`; write no new ones.

Progress lives in the database; active PRDs carry no `status:` field.
An item that is `ready` or `in_progress` states acceptance criteria and
carries no open `BLOCKING` line; an `in_progress` item records the `branch:`
it lives on.
Finishing work leaves its directory in place.
