---
name: sd-handoff
description: Write the local session-handoff packet for this directory so a killed session can be restarted with its context.
disable-model-invocation: true
---

# sd-handoff

The problem is narrow and local: this session is context-compromised and has to
be killed and restarted against the same repository on the same machine.
`bin/sd-handoff` writes one packet and stops. **Nothing here touches git,
GitHub, or CI** — no commit, no push, no PR, no stash. The working tree is left
exactly as it stands.

## The gesture is two steps, and cannot be one

```
sd-handoff --summary "..." --next "..." --dont "..."
/clear
```

Then the `sd-handoff-restore` SessionStart hook injects the packet into the
fresh session in the same directory. Writing cannot be automated away: a hook
is a subprocess with no access to the conversation, so it can snapshot branch,
head and changed files but can never produce `summary`, `next` or `dont`.
Those need the model, which means an explicit call. That constraint is what
keeps this from becoming an automatic journal.

## Where the packet lives

`~/.local/state/sd-ai-command-pack/handoff/<digest>.json`, where `<digest>` is
the sha256 of the **normalized worktree root**, resolved as:

```
explicit --cwd  ->  $PWD  ->  CLAUDE_PROJECT_DIR  ->  git rev-parse --show-toplevel
```

`CLAUDE_PROJECT_DIR` comes last on purpose: it is the session's *launch*
directory, so a writer inside a linked worktree and a restorer preferring the
env var would compute different digests and never meet. Normalizing to the root
is what lets a session started in `src/foo` find the packet a session started at
the root wrote. Two worktrees of one repo get distinct packets, which is right —
they hold different work. Outside a git repo the raw directory path is the
identity, so packets work in plain directories too.

**Hash on path, verify on content.** The packet records `repo.root` (plain
text, so a mismatch is diagnosable rather than an opaque hash), `cwd_raw`,
`remote` and `head_sha`, and never hashes them. Restore refuses when the
recorded root is not a prefix of the resolved cwd, or when the recorded
`head_sha` is not an object in the current repo (that is the reused-path,
different-project case). A changed `remote` injects with a warning, never a
refusal on its own.

## What it holds — and the cap is the point

`schema`, `created`, `expires` (+14d), `consumed`; `repo` {root, cwd_raw,
remote, label, branch, head_sha}; `item` (work-item dir, or **null** — packets
work with no work item at all); `summary` (≤600 chars); `next[]` (≤5);
`dont[]` (≤5 — dead ends already tried, the field that saves the most rework);
`questions[]` (≤3); `files[]`, derived mechanically from `git status
--porcelain` plus `git diff --name-only`, never typed by hand; optional
`stash_ref` under `refs/sd-handoff/` (local-only, never pushed).

Hard **8 KB** cap. Over it, the tool trims the mechanical file list to a floor
of 5 and then refuses, saying what to cut. The refusal is the anti-journal
mechanism, not a formality.

## Flags

`--summary` · `--next` (repeatable) · `--dont` (repeatable) · `--question`
(repeatable) · `--item` · `--stash-ref` · `--cwd` (resolve the packet for that
directory) · `--show` (print the pending packet **and consume it** — the load
path for Codex/OpenCode sessions, which have no SessionStart hook) · `--json`.

Exit codes: `0` wrote or showed · `1` refused, with the reason on one line ·
`2` usage error. Never a traceback.

## The restore side

`sd-handoff-restore` runs on SessionStart matchers `startup|clear` **only** —
never `compact` (a compact matcher would eat the packet into the dying session,
so the following `/clear` finds nothing) and never `resume` (old context, no
use for it). It exits silently when `SD_HANDOFF_RESTORE=0` is set — which
`cron-jobs.sh` exports for every `claude -p` job, so a packet is not eaten at
3 a.m. — or when no unconsumed, unexpired packet exists. Otherwise it emits the
packet as `additionalContext` stamped with its age, and marks it consumed by
atomic rename, so two sessions racing in one directory cannot both claim it.

## Never

- **Never write a packet automatically.** No SessionEnd hook, no PreCompact
  hook, no "I'll snapshot this just in case". Writing stays an explicit act,
  because auto-writing every session is exactly how the journals started.
- **Never treat the packet as a log or a journal.** One per directory, last
  writer wins, consumed once, expired at 14 days, capped at 8 KB. A superseded
  packet is stale by definition.
- **Never commit, push, stash, or open a PR from the default lane.**
- **Never consume a packet you are only inspecting** — `sd-status`'s handoff
  section reads without consuming; `--show` consumes.
- **Never pad `summary`, `next` or `dont` to fill the cap.** `dont[]` in
  particular is worth more than everything else in the file; five real dead
  ends beat a paragraph of narrative.

## Lane B (`--push`, `--park`) is not implemented

The design's Lane A / Lane B split (R10-D3) gives `--push` the carrier-branch
behaviour: append `handoff:` to `## Log`, commit and push WIP, print a restart
one-liner; on finding an open PR for the carrier branch, convert it to draft
before pushing and **suppress the Copilot re-request** (R10-D2), because the
once-per-head rule would otherwise fire on the moved head. The design's
guards — settled-green refusal and the branch-scoped stash check — belong to
that lane.

**`bin/sd-handoff` today implements Lane A only.** It has no `--push` and no
`--park`, and none of those guards exist in the code yet. Do not simulate Lane
B by hand: if a carrier branch is what you need, say so and do the commit and
push deliberately under `sd-ship`'s constraints.
