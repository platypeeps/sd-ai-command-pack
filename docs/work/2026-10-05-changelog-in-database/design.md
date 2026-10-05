# Design — changelog entries in the database

The problem, the measurement and the requirements are in [prd.md](prd.md).
The steps are in [implement.md](implement.md).

## The shape

```text
PR body "## Changelog"  --prepare-->  ship row (body, parsed entry)
        |                                   |
   reviewer reads it               merge confirmed on GitHub
                                            |
                                   state row sd-changelog:v1:<slug>:<pr>
                                            |
                 sd changelog render  -->  CHANGELOG.md region  -->  render PR
```

One new module, `bin/sd_changelog.py`, owns the section parser, the row key,
the row writer, the reader and the renderer. `sd-ship` and `bin/sd` call it.
The system repository does not change.

## Status

Design accepted. The operator ruled Q1 to Q7 on 2026-10-05 at about
17:25 MDT, through the team lead. Each ruling took the recommendation.
The ruling is recorded on sd:2783. Implementation has not started.

## Decision log

| Question | Ruling (Operator 2026-10-05 ~17:25 MDT) |
| --- | --- |
| Q1, a no-entry answer | Accept `none` as the explicit no-entry answer. |
| Q2, the store | The database holds the entries; git is the cross-check. |
| Q3, render cadence | On demand, plus a daily lane render when unrendered rows wait. |
| Q4, releases | Fix the `CONTRIBUTING.md` terminal-release line; leave `--release` unused until a release is cut. |
| Q5, the hand-written Unreleased lines | Keep them below the rendered region; no release heading now. |
| Q6, a merged PR with no row | Render refuses and names the pull request; `sd changelog import` repairs it. |
| Q7, no privacy-pattern file | Refuse at render; warn at prepare. |

## Decisions

Each numbered point below answers one of the six questions in the brief.
Each **Decided** paragraph closes one operator question; the log above
lists them.

### 1. Entry text source, and who sees it

**Decision: a `## Changelog` section in the pull request body.**

```markdown
## Changelog

### Fixed

- **A catch-up keeps both changelog entries (sd:2174).** The lane ...
```

Or, for a change with no user-facing effect:

```markdown
## Changelog

none
```

Reasons:

- The body is already the reviewed, public description. A reviewer reads the
  entry beside the summary, before merge.
- `prepare` already reads the live body (`body_input` in `bin/sd-ship`) and
  stores it in the ship row. A later edit on GitHub wins, as it does today.
- `squash_body` copies the body into the squash message. The entry text
  therefore also lands in git, which render uses as a cross-check (point 5).
- An `sd-ship` flag hides the text from the reviewer until merge. The item
  title is one line, and many items ship several pull requests.

The subsection names are the six that Keep a Changelog defines. The current
file uses four of them: Added, Fixed, Changed and Deprecated.

`.github/PULL_REQUEST_TEMPLATE.md` gains the section with a comment that
names `none`.

**Decided, Q1 (Operator 2026-10-05 ~17:25 MDT):** accept `none` as an explicit no-entry answer? Ruling, as recommended:
yes. Without it, a test-only change must invent prose, and an absent section
cannot tell "forgot" from "nothing to say".

### 2. Storage

**Decision: one checkpoint row per pull request in the existing `state`
table.** No schema change.

`sd_db.ship.read` and `sd_db.ship.save` already store revisioned JSON rows
under a free key: the ship receipt (`ship:<sha256>`) and the offload receipt
(`sd-gate-offload:v1:<sha256>`) use them. The pack already queries `state`
by key prefix in `sd_ship_squash` and `sd_ship_no_item`. Index
`state_by_kind_key` (migration 013) serves a prefix range scan.

Key: `sd-changelog:v1:<slug>:<pr>`, for example
`sd-changelog:v1:platypeeps/sd-ai-command-pack:1377`.

- Per pull request, not per item: one item often ships several pull
  requests, and one squash is the unit that lands.
- Readable, not hashed: the renderer lists one repository's rows with a range
  scan, `key >= prefix AND key < prefix || char(0x10FFFF)`. A `LIKE` would
  read `_` in a slug as a wildcard.

Row (`protocol: 1` is added by `ship.save`):

| Field | Value |
| --- | --- |
| `repository` | `owner/name`, lower case |
| `pull_request` | number |
| `item` | `sd:<n>`, or null for a no-item ship |
| `merge_commit` | the squash sha GitHub confirmed |
| `merged_at` | the reconcile time, UTC |
| `entries` | list of `{section, text}`, in body order; empty for `none` |
| `body_digest` | sha256 of the `## Changelog` section as merged |

A correction after merge is a new revision of the same key. `ship.save`
appends, so the history stays.

**Decided, Q2 (Operator 2026-10-05 ~17:25 MDT):** keep the database as the store, or render straight from the
squash messages in git? The squash message already carries the section, so
git alone could render. Ruling, as recommended: the database, as the item says.
Reasons: a correction is a new row revision, not a rewrite of `main`. sd
surfaces such as the dashboard can list unreleased entries without a
checkout. Git stays the cross-check (point 5).

### 3. Render verb, timing, determinism

**Decision: `sd changelog render [--check] [--release VERSION]`, run in a
render pull request.**

- Input: the rows for this repository, the first-parent history of the base,
  and the newest `v*` tag on that history.
- Selection: rows whose `merge_commit` is on the base's first-parent history
  after the newest tag. A row whose commit is not on the base is skipped and
  named on stderr; it never renders.
- Order: by section in the six-name order above, then newest merge first, by
  first-parent position. Write order and clock times never decide the order.
- Output: each entry's text verbatim, with `(#<pr>)` appended to its first
  line, continuation lines indented two spaces as the file does today.
- Region: between `<!-- sd-changelog:begin -->` and
  `<!-- sd-changelog:end -->` under `## Unreleased`. Text outside the region
  is never read or written.
- `--check` renders to memory and exits 1 when the file differs. Prepare
  runs it for a render branch (R6).
- `--release VERSION` writes the region under `## VERSION - <date>` instead,
  and leaves an empty region under `## Unreleased`. The date is the base
  commit's committer date in UTC, not the clock, so the output stays
  deterministic.

`sd changelog show` prints the same region to stdout and writes nothing.

Between render pull requests, `main`'s `CHANGELOG.md` lags the merged
entries. The squash messages and `sd changelog show` hold them.

**Decided, Q3 (Operator 2026-10-05 ~17:25 MDT):** when does a render pull request run? Ruling, as recommended: on
demand, plus once a day from the integrator's lane when at least one
unrendered row exists. Only the render branch edits the file, so its catch-up
never conflicts with a feature branch.

**Decided, Q4 (Operator 2026-10-05 ~17:25 MDT):** do releases resume? `CONTRIBUTING.md` says `v0.72.0` is the
terminal release and forbids tags and headings, yet `v1.0.0` exists and its
heading is in the file. Ruling, as recommended: fix that line to name `v1.0.0`, and
keep `--release` unused until the operator cuts a release. The design does
not need a release to remove the conflicts.

### 4. Migration and what drops the per-PR entry

**Decision: keep the current file text; add the empty marked region at the
top of `## Unreleased`.**

The 2,193 hand-written Unreleased lines stay below the region. Parsing them
into rows would need a parser for free prose with nested lists, and nothing
reads them as rows.

**Decided, Q5 (Operator 2026-10-05 ~17:25 MDT):** cut those lines into a release heading now, for example
`## 1.1.0 - 2026-10-05`? Ruling, as recommended: no. They stay until a release is cut (Q4).

The opt-in is a tracked file, `.github/sd-changelog.json`:

```json
{"mode": "database"}
```

It follows `.github/sd-gate-reuse.json` and `.github/sd-review.json`. A
reviewer sees the switch in a diff. A `repo` column would need a
`SCHEMA_VERSION` bump and a live migrate.

What changes for a feature branch in the opted-in pack:

| Surface | Today | After |
| --- | --- | --- |
| Builder briefs, `CONTRIBUTING.md`, `WORKFLOW.md` | "add an Unreleased entry" habit | "write the `## Changelog` section" |
| `.github/PULL_REQUEST_TEMPLATE.md` | no section | `## Changelog` section |
| `sd-ship prepare` | no check | refuses a missing section, a privacy match, or a `CHANGELOG.md` edit |
| `bin/sd_changelog_merge.py` (sd:2174) | resolves keep-both catch-ups | deleted once no open branch edits the file |

No gate or test requires an entry today, so no gate drops a requirement.
`sd-docs-lint`, `tests/governed.py` and `tests/test_workflow_policy.py`
skip `CHANGELOG.md` as history; that stays.

Deleting the resolver touches every place that names it:
`bin/sd_changelog_merge.py`, `tests/test_sd_changelog_merge.py`, the imports
and calls in `bin/sd-ship` and `bin/sd_lane.py`, the module list in
`bin/sd_ship_bindings.py`, its entry in `tests/test_git_policy.py`, the
`sd_lane.Speculation` changelog cases in `tests/test_sd_lane.py`, the
catch-up resolver cases in `tests/test_sd_ship.py`, and the
paragraph in `skills/sd-ship/references/recovery.md`. A repository that did
not opt in still edits `CHANGELOG.md` per branch, so step 7 asks first
whether any such repository uses `sd-ship`.

### 5. Satellite and failure behaviour

**Decision: the row is written only by the hub's merge; nothing is lost
silently.**

- **Prepare on a satellite.** It parses and checks the section locally and
  saves the parsed entry into the ship row over the wire, as sd:2679 already
  saves the row. A hub that cannot be reached fails the prepare, as today.
- **Merge.** `sd-ship merge` runs on the hub only: it holds
  `repository_lock`, a file beside the database, and a satellite meets
  `HubOnly` there. So "the hub is unreachable at merge" cannot happen; the
  satellite cannot merge at all.
- **Write point.** `reconcile` writes the row after GitHub confirms the merge
  and before it saves `phase=merged`. Merge reaches `reconcile` on every
  path. The text comes from the stored `body`, which is the squash message's
  source, so the row and git agree.
- **Write fault.** The fault raises like any database fault, and the phase
  stays `merge_dispatch`. A rerun of `sd-ship reconcile` (or `merge`, which
  calls it) writes the row. The write is idempotent: an existing row with the
  same `merge_commit` and `body_digest` is left alone.
- **A merge made outside `sd-ship`.** No row is written. Render's
  cross-check catches it. It reads the squash messages on the base since the
  newest tag. Each one with a `## Changelog` section other than `none`
  needs a row. A missing row refuses the render and names the pull request.
  `sd changelog import <pr>` writes the row from that squash message.

**Decided, Q6 (Operator 2026-10-05 ~17:25 MDT):** should a missing row refuse the render, or render from the
squash message and warn? Ruling, as recommended: refuse. The refusal names the fix,
and a render pull request is never urgent.

### 6. Privacy

The repository is public. The `## Changelog` text is public as soon as
`prepare` publishes the body, so the check must run before publication.

- Prepare checks the section against the operator's privacy patterns before
  it creates or edits the pull request. A match refuses and names the line
  number, not the matched text.
- Render checks every row again, because a correction or an import can
  bring new text.
- Pattern file: config key `sd.privacy_patterns`, default
  `${SYSTEM_TOOLS_CONFIG:-~/.config/system}/privacy-patterns`. It holds one
  extended regular expression per line, the format `local-leak-guard` in the
  system repository reads. The pack does not import that tool.
- Tests use a synthetic pattern file in a temporary home.

**Decided, Q7 (Operator 2026-10-05 ~17:25 MDT):** with no pattern file, warn or refuse? Ruling, as recommended: refuse
at render, warn at prepare. Render is the last step before the file changes;
prepare on a fresh satellite should not block on missing local config. The
pre-push leak guard does not cover the pack clone today.

## Failure modes

| Fault | Effect | Who sees it |
| --- | --- | --- |
| Body lacks the section | prepare refuses, `code=changelog_missing` | the builder |
| Section has an unknown subsection or no bullets | prepare refuses, `changelog_invalid` | the builder |
| Privacy pattern match | prepare refuses, `changelog_private`, line number only | the builder |
| Feature branch edits `CHANGELOG.md` | prepare refuses, `changelog_edited` | the builder |
| Row write fails after the squash | reconcile raises; phase stays `merge_dispatch` | the lane log and the integrator |
| Merge outside `sd-ship` | render refuses, names the pull request | whoever renders |
| Render branch is stale | `render --check` fails at prepare | whoever renders |

## Rollout and rollback

Steps 1 to 4 change nothing for any repository until step 5 adds
`.github/sd-changelog.json`. Rollback deletes that file. The rows stay in
`state` and harm nothing. The last render stays in `CHANGELOG.md`, and
branches may edit the file again.

## Alternatives rejected

- **`merge=union` in `.gitattributes`** (sd:2686): it drops the blank line
  between entries, and the lane log records it as unsafe.
- **One file per entry, for example `changelog.d/<pr>.md`:** no conflict.
  But the entry needs the pull request number before it exists. A file per
  merge also grows the tree. The database already holds per-merge rows.
- **A new `changelog` table:** a `SCHEMA_VERSION` bump forces a live migrate
  on the hub and a matching library on every satellite. `state` already
  holds this row shape.
- **Entry text from an `sd-ship merge` flag:** no reviewer reads it before
  the merge.
