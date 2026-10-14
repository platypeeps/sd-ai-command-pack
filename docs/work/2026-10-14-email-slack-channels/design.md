---
title: Email and Slack channels - a repo names the mail aliases it owns, and Today shows their threads waiting on the operator
created: 2026-10-14
item: sd:4191
---

# Design: email and Slack channels (sd:4191)

Write this page only when the shape needs agreement before the code.
The item's row holds status, progress and decisions; this page holds the shape.

## Status

Design only; nothing is built. Q1 and Q2 below decide the scope; slices E1 and E2 do not wait on them.

Adversarial review: one read-only round on 2026-10-14 found three findings. Dispositions:

- F1 the pack pin does not guard an older writer, since the dashboard loads the home clone: fixed; the claim is
  corrected, and the rollback step clears `email` first (Older state).
- F2 a fetch Gmail throttled in part looks fresh: accepted with a reason; a throttled thread keeps its old row and
  arrives on the next fetch (`write_threads`), a one-day delay the digest has today (Risks).
- F3 filtering before taking each thread's newest arrival shows a thread already answered: fixed; Today takes the
  newest arrival first, and a test covers a reply.

## Terms

- **Channel setting**: the `channels` JSON column on a repo's row (sd:3471 design, `docs/work/2026-10-13-channels/`).
  Publish channels (`obsidian`, `notion`, `drive`) are one replacement; inbound sources (`feed`, `jira`, `github`)
  are each their own key (`channels.kept`).
- **Email channel**: the two system tools that already carry mail. `local-notify` is the one sender
  (`send_gmail_message` appears nowhere else in either repository); it mails only the recipient pinned per machine.
  `local-mail-intake` is the one reader: its Gmail client also serves the dashboard's Notes mail and Draft email.
- **Alias label**: the `<label>` of an `alias|<label>|<address>` line in `<config>/mail-intake/mail-intake.conf`.
  The address stays in that file; the database holds the label only.
- **Arrival**: a row of mail-intake's `mail-arrivals.csv`: a thread whose newest message changed, with its `alias`
  label, `subject`, `who`, `waiting_on` and `detected_at`.

## Rulings this design follows

- Channels are choosable per repo: Notion, email, Obsidian, Drive, GitHub issues, Jira, Slack (sd:3462, 2026-10-12).
- Each repo's channels live in the workflow database, set by `sd-db repo channels` and the dashboard form
  (sd:3471, 2026-10-13).
- Jobs report findings into Reports and Today, not by mail; the dashboard is the primary surface (sd:3454, sd:3537).
- The mail and drive intake files stay hand-edited; they do not move into the database (sd:3988, 2026-10-13).
- Today and Tasks show each repo's issues assigned to or filed by the operator (sd:3461, sd:4636; system half sd:4628).

## Problem

Email reaches the workflow only around it. `local-notify` mails whatever a caller asks, per call. `local-mail-intake`
watches two aliases and feeds a private repository's morning digest by mail. Neither knows which repo a message is
about, so Today cannot show "mail waiting on you" beside the repo it belongs to, as it will for Jira and GitHub issues.

Slack has no transport in either repository. A scheduled agent routine reads Slack through an MCP connector and mails
a digest; nothing in the pack or the system repo reads or posts Slack.

## Approach

### No new transport

`local-notify` and `local-mail-intake` are the email channel. Nothing moves into the pack and nothing is renamed:
the pack holds the vocabulary, the system tools carry the mail. Each tool's README names itself as the channel's
outbound or inbound half.

### Inbound email: one key on the repo row (E1, pack)

`email` joins `channels.INBOUND`, beside `feed`, `jira` and `github`:

```json
{"email": {"aliases": ["board", "committee"]}}
```

- **Set**: `bin/sd-db repo channels PATH email=board,committee`. One to eight labels, each `[a-z0-9][a-z0-9_-]*`,
  no repeats, sorted on write. The labels are names only: an `@`, a space or a URL refuses, so no address enters the
  database.
- **Its own key**, as `feed` is: `kept` keeps it when a set leaves it out, and `outbound` drops it. A setting naming
  only `email` publishes as no setting does. Joining `CHANNELS` instead would have turned the vault copy off, since a
  publish channel left out is off.
- **Reader**: `repos.mail_aliases(connection, path)` returns the labels, or `[]`. It reads through `repo_channels`,
  so a stored value the validator refuses, a restore that is open, or a database not yet migrated raises, as
  `issue_sources` does. No migration: the column is JSON.

### Today shows the threads (E2, system)

Today's per-repo section that sd:4628 adds for issues gets mail rows too. For each repo with aliases, the dashboard
reads mail-intake's arrivals through `mail_intake.read_arrivals(path, unreported_only=False)`, loaded by path as
`notes_screen._mail_intake` already does.

- **Rows**: first the newest arrival of each thread, since the file keeps every change; then keep it when its
  `alias` is one of the repo's labels, its `waiting_on` is `you` and its `detected_at` falls in the last 48 hours.
  Filtering first would show a thread the operator already answered. At most ten, then "N more". Each shows subject,
  sender name and time, linked to the thread in Gmail with the `authuser` the Draft email action uses.
- **Read only**: no fetch, no stamp, no Jev. The private digest's `stamp` is untouched, and so is its mail.
- **Unknown is not none.** A missing state folder, an unreadable file, a label the conf does not define, or a last
  fetch older than 36 hours (from `threads.csv` `seen_at`) shows "mail not read: <reason>" under the repo, never an
  empty list. A machine with no mail-intake state (a satellite) shows the same line.
- **Form**: the repo channels form (sd:3465) gets an email aliases field, posted through `set_repo` and
  `repos.set_channels` like the other inbound keys.

Rejected:

- **A `mail` shadow tracker.** It moves mail-intake's Gmail client into the pack, needs a hub collector run, and needs
  a closed state that a mail thread lacks. Today reads the state file that already exists.
- **Alias addresses in the database.** sd:3988 keeps the intake file hand-edited; a label in the row is enough.
- **An outbound `email` publish channel for documents.** No document wants mailing to its own author; Notion is the
  work channel (sd:3471). Q1 asks about outbound notices instead.

### What it replaces and deletes

- E1 and E2 replace nothing and delete nothing: the digest keeps mailing until Q3 decides otherwise.
- After Q3's first option, the digest's mail section and mail-intake's `report`, `stamp` and `reported_at` column have
  no caller left and go, in the private repository's PR and a system PR.

### Slack

Recommended: no `slack` key until a reader exists in the tree (Q2). A key with no reader is config nobody reads, and
the only Slack reader today is an agent prompt outside both repositories. Q2 names the two ways to give Slack a reader.

## Non-goals

- Sending mail anywhere new. The recipient stays pinned per machine in `<config>/notify/.env`.
- Moving `mail-intake.conf` into the database (sd:3988).
- Jev in Today's mail rows: they show `waiting_on` only, so Today runs the same without Jev.
- Marking a thread done from the dashboard: the rows age out after 48 hours.

## Older state

E1 and E2 move no state in steps: E1 adds a key to a JSON column, and E2 reads files. The rows below cover what an
older or newer build meets.

| Step | State moved | Failure | Recovery | Test |
| --- | --- | --- | --- | --- |
| pack rollback after a repo stores `email` | none; the row keeps the key | the older validator refuses the whole value, so that repo's renders hold its vault copy and queue | before a rollback, clear and re-set the repo without `email`: `repo channels PATH none`, then set the rest; or roll forward | none new: `test_each_key_outside_the_vocabulary_refuses_by_name` is the older validator's behaviour; the E1 body names this recovery |
| older pack writes the row | the row loses `email` | the dashboard and the verb load the pack's home clone (`SD_PACK_ROOT`), not the gate's pin; an older `kept` treats a stored value it refuses as `{}`, so a set from either drops `email` | the same rollback step as the row above: clear `email` from each repo that names it before the home clone moves back; `sd-db repo list` names the paths, `repo channels PATH` shows each | none: older code cannot be tested here; the E1 body carries the step |
| conf edited after a fetch | arrivals keep the old label | a label renamed in the conf leaves earlier arrivals under the old one | Today shows the old rows for 48 hours, then they age out | `test_today_mail`: a label absent from the conf shows the reason line, fail-first |
| mail-intake state from before E2 | none | an arrivals file written before E2 | E2 reads the columns the file already has; no rewrite | `test_today_mail` runs on a fixture copied from today's column order |

## Slices

1. **E1 pack, inbound `email` key** (about 2 hours). `channels.INBOUND`, `_email` validation, `kept` and `outbound`
   unchanged in shape; `repos.mail_aliases`; the verb's `email=` spelling; `docs/sd-db.md` Channels lines.
   Tests: `tests/sd_db/test_channels.py` (each refusal by name: an `@`, a space, a repeat, nine labels, an empty
   list; `outbound` of an email-only setting is `None`; `kept` keeps `email` across a channels set), and
   `tests/sd_db/test_repos.py` (`mail_aliases` reads, and raises on a refused stored value). Leaves working: every row
   without `email` reads and publishes as before.
2. **E2 system, Today mail rows and the form field** (about 4 hours, after sd:4628 merges). The pin bump; Today's mail
   rows; the form field; `local-notify/README.md` and `local-mail-intake/README.md` name the channel halves. Tests:
   `tests/test_today_mail.py` (rows filtered by label, `waiting_on` and the window; a reply after an inbound
   arrival hides the thread; each unknown cause shows its reason), the management test for the field, each fail-first. Leaves working: repos without aliases show no mail
   line.
3. **S1 Slack** only if Q2 picks a reader; sized then.

## Open questions

Q1. Should a repo's notices route by its channel setting?
- Option: No. Notices stay per call through `local-notify`; Reports and Today carry findings (Recommended). Keeps
  sd:3454's direction and adds no reader to notify.
- Option: Yes. An outbound `notify` key per repo (email, ntfy) that `notify.sh --repo PATH` reads; about 3 hours, and
  notify then depends on the database with a fallback to its `-c` list.

Q2. How should Slack get a reader?
- Option: Defer Slack: no key until a reader exists; keep it on this item as a follow-up (Recommended).
- Option: A `slack` key of channel names that the Slack digest routine reads through `sd-db repo channels`; no new
  credential, but the reader is an agent prompt outside the tree, so no test covers it.
- Option: A Slack bot token and a shell reader like mail-intake, feeding Today; a new credential on the machine.

Q3. Once Today shows mail rows, should the private digest keep its mail section? (Does not block E1 or E2.)
- Option: Keep it for a week of Today use, then decide (Recommended).
- Option: Drop it after E2: the digest stops mailing threads, mail-intake gets its own daily `fetch` job, and
  `report`, `stamp` and `reported_at` go.

## Acceptance criteria

- [ ] `python3 -m unittest tests.sd_db.test_channels tests.sd_db.test_repos` passes with 0 failures.
- [ ] `sd-db repo channels <path> email=board` prints `none -> {"email":{"aliases":["board"]}}`;
      `email=a@example.test` refuses naming `email` and changes nothing.
- [ ] A repo whose setting is `{"email": {"aliases": ["board"]}}` renders and queues exactly as a repo with no setting.
- [ ] Today, for a repo with `email=board`, lists a fixture arrival on `board` waiting on you from the last 48 hours,
      and leaves out one waiting on them, one on another label, one older than 48 hours, and a thread whose newer
      arrival is the operator's reply.
- [ ] Today shows "mail not read" with the reason for a missing state folder and for a fetch older than 36 hours.

## Risks

- Today's rows are as fresh as the last fetch, which the private digest runs once a day. Accepted: the stale line
  names a fetch older than 36 hours.
- A fetch Gmail throttled in part writes a fresh `seen_at` while a few threads were not read. Accepted: those threads
  keep their old row (`write_threads` carries them) and arrive on the next fetch, a day late, as they do in the
  digest today. The fetch prints the throttled count; Today does not see it.
- Two repos may name one label; both show its threads. Accepted: a refusal across rows costs a check in the write for
  a case one operator controls.
- `waiting_on` is coarse: most threads read `you` (mail-intake README). The 48-hour window keeps Today to the daily
  delta, where the label is honest.
- Subjects and sender names show on the local dashboard, as the digest and Notes mail already show them; nothing new
  leaves the machine.
- What ties a row to its repo is the `alias` label mail-intake wrote at fetch time from the conf; a label renamed
  since points nowhere until the rows age out.
