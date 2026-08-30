---
name: sd-ship
description: Take committed work from a verified branch to a merged pull request, committing only enumerated paths.
disable-model-invocation: true
---

# sd-ship

`sd-ship` sequences the stages between "the work is done" and "the PR is
merged". Invocation is explicit approval for the in-scope commits, the
PR-branch push, and the configured review request — and for nothing outside
the paths you enumerate.

## The sequence

1. **Verify acceptance.** Every acceptance criterion in the item's `prd.md` is
   checked, with the actual check run and its output seen. A partial pass is
   not a pass.
2. **`sd-spec`** — refresh `docs/spec/**` on the PR branch.
3. **`sd-docs-lint`** — all five rules enforced locally regardless of repo
   mode: shape · ready · decision shape · spec index · PR link.
4. **Commit enumerated paths only.**
5. **Push** the PR branch.
6. **Open the PR** with a `Work:` line resolving to the item (0 unchecked
   boxes), or `Work: none - <reason>` under 800 lines with no sensitive path.
7. **Request Copilot once per head** — once, per head SHA, never again for the
   same head.
8. **Settle loop** — wait for checks and required reviews.
9. **Merge**: `gh pr merge --squash -t "<title> (#N)" -b "<body>"`. The
   explicit `-t`/`-b` is the wip-eraser: `wip:` subjects must never reach main.

## Flags

| Flag | Effect |
|---|---|
| `--pr N` | settle an existing PR rather than opening one |
| `--backlog` | loop over ready items (acceptance criteria present, no open BLOCKING) |
| `--agent claude\|codex` | who does the work in `--backlog` (default `claude`) |
| `--jobs N` | concurrent worktrees, default 1, **hard ceiling 3** |
| `--cap N` | items per invocation, default 3 |
| `--dry-run` | print selected items, worktree paths, resolved budget; exit |
| `--tier` | override the routed review tier |
| `--no-github` | local stages only |

## The autonomous lane (R10-D1)

`--backlog --agent codex` runs each item as a non-interactive
`codex exec --sandbox workspace-write` in its own fresh worktree cut off
`origin/main` at the item's `branch:`. The prompt is built **from the item's
own artifacts** — prd + design + implement + the `## Log` tail, the same
context a reattaching session reads — never a bespoke prompt file. Green
`sd-check` in the worktree opens a **draft** PR carrying the `Work:` line; red,
timeout, or rate-limit appends a `handoff:` entry to `## Log` and leaves the
worktree standing for inspection.

Its bounds are not negotiable:

- **It never merges and never marks a PR ready-for-review.** Not even in a repo
  with no branch protection at all — which is exactly the repo where the
  distinction matters. It produces reviewable drafts and nothing else.
  Settling is a human running `sd-ship --pr N`.
- **One writer per checkout.** Worktree isolation is the mechanism; `--jobs` is
  capped because the merge lane is serial regardless.
- **No silent death.** Every item gets an explicit wall-clock budget; exceeding
  it is a reported failure with a `## Log` entry, never a skipped item.
- **Rate-limited is not unavailable.** A quota stop ends the run cleanly with
  the remaining items untouched and named. No retry-thrash, no falling through
  to another provider.
- Codex runs here are subscription-only: the same `codex_preflight` env scrub
  and `auth_mode == chatgpt` assertion `sd-review` applies (R10-D4).
- The repo's `CLAUDE.local.md` marked block is prepended to the prompt this
  lane builds (R10-D7).

## Never

- **Never `git add -A`, `git add .`, or `git commit -a`.** Commit the exact
  paths you enumerated and can name. This is the single hardest constraint in
  this command.
- **No write after settled-green.** Once the PR is green and settled, sd-ship
  stops writing: no follow-up commit, no amend, no force-push, no "one more
  fix". A new finding is a new branch.
- **Never request Copilot twice for the same head.** Once per head SHA.
- **Never accept a repo path** (R10-D6) — the repository is the one enclosing
  cwd.
- **Never claim merge authority the config does not provide.** Merge authority
  is GitHub branch protection *where it is enforcing*; where it is not, say so
  (`sd-status` prints the gaps) rather than asserting the merge was gated.
- **Never weaken a test, skip a check, or bypass a guard to reach green.**
- **In `mode: guest`, never post reviews or labels** in the upstream repo.

## State of the tooling

There is no `bin/sd-ship` yet. Today the agent runs the stages: `sd-check`,
`sd-review`, `sd-docs-lint`, then `git` and `gh` by hand under the constraints
above. `--backlog`/`--agent codex` is not implemented; do not simulate it with
ad-hoc worktree scripting.
