---
name: sd-status
description: Read-only derived status for the repository you are standing in, with branch-protection enforcement gaps named.
disable-model-invocation: true
---

# sd-status

`bin/sd-status` answers "where does this repository actually stand" without
writing anything — not the repo, not the state directory, not a cache. Every
section derives its answer at run time from the filesystem, from git, or from
GitHub, because committed derived state is permanent staleness.

**There is no repo-path argument and no fleet walk (R10-D6).** The repository
is the one enclosing cwd, full stop. The old fleet-walking sd-status is
dropped; the dashboard is the cross-repo view, and it reads, never acts.

## The eight sections, in output order

| Section | What it shows |
|---|---|
| `pack` | the checkout these tools came from |
| `work` | derived item status from `docs/work`, counted |
| `prs` | open pull requests, via the same code path as `sd-pr-state` |
| `setup` | mode (`full`/`minimal`/`guest`) and the detected check entrypoints |
| `protection` | branch-protection **enforcement**, gap by gap, plus the two merge-settings flags |
| `handoff` | the pending local packet for this directory (**read, never consumed**) and Lane B carrier branches on origin |
| `backends` | which review backends are installed — names only |
| `residue` | legacy leftovers, each with the exact command that removes it |

## The protection section is the one that matters

The doctrine is that merge authority is GitHub branch protection *wherever
protection is actually enforcing*. Protection that exempts admins is prose, not
authority: it stops collaborators and leaves the one account that does the
merging entirely ungated. So this section reports enforcement state, and each
missing leg prints as a named gap:

- `enforce_admins` off — every rule below it stops at the admin who merges
- no required status checks — a red PR still merges
- `strict` off — a green check run against a base that moved still merges
- `required_not_produced` — required contexts no workflow here produces; each
  blocks every PR until an external app reports it
- `produced_not_required` — checks this repo runs but does not require; they
  can go red without blocking a merge
- `reviews` — no PR review required, or zero required approvals
- the two r7 merge-settings flags: squash title/message source (a `wip:`
  subject reaching main) and whether rebase-merge is allowed

**A gap is a report, not a failure.** The command exits 0 whether or not it
found any. Exit 2 is reserved for an invocation or configuration fault, printed
as a sentence, never a traceback.

## Accepted states are not silenced states

A repository can record, in tracked `.github/sd-status.json`, a protection
state it has looked at and decided to keep. Those findings print as
`ok  [id] accepted <date>: <reason>` with the ending condition on the line
below, and move from `protection.gaps` to `protection.accepted` in `--json` —
so a consumer counting gaps counts open ones only, and never mistakes an
accepted finding for an absent one.

What makes it an acknowledgement rather than a suppression:

- **Keyed on the observed protection state, never on the gap id.** `reviews`
  is emitted for two opposite states — the review object being absent, so no
  pull request is required at all, and the object existing while asking for
  zero approvals. An entry pins the facts it was accepted under, and stops
  applying the moment any of them changes; the gap then prints as a gap,
  carrying a line saying an acknowledgement exists and no longer matches.
- **`because` and `until` are both required, and both print every run.**
  `until` is the deletion criterion: when it comes true the entry is deleted
  and the gap returns on its own.
- **A malformed file accepts nothing and says so** — each fault prints as its
  own gap. It fails closed and loudly, never silently.

## Flags

`--json` (one machine-readable object) · `--parked` (list only the items the
age sweep parked, read from their own `parked:` frontmatter, not from a ledger)
· `--limit N` (most PRs to list).

## Never

- **Never present the absence of gaps you did not read as safety.** If the
  protection section could not be fetched, say the enforcement state is
  unknown; do not say the repo is protected.
- **Never report an accepted finding as an absent one.** "No open gaps" is a
  different sentence from "protection is fully enforcing", and only the second
  is a claim about the branch. Read `protection.accepted` before saying either.
- **Never claim a guarantee the config does not provide.** In a repo with no
  protection, the honest statement is that nothing enforces merge authority
  there.
- **Never consume the handoff packet from here.** The `handoff` section reads
  it; only `sd-handoff-restore` or `sd-handoff --show` consumes it. Reading
  status must never eat a pending packet.
- **Never write, anywhere.** No cache, no index row, no state file. If you want
  a fact recorded, that is a different command.
- **Never point it at another repository**, and never loop it over checkouts to
  rebuild the fleet view that was deliberately removed.
