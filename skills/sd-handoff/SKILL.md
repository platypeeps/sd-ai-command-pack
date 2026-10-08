---
name: sd-handoff
description: Write the local session-handoff packet for this directory so a killed session can be restarted with its context.
disable-model-invocation: true
---

# sd-handoff

Use this when a context-compromised session must be killed and restarted
against the same repository on the same machine. `bin/sd-handoff` writes one
packet and stops. **Nothing here touches git, GitHub, or CI** — no commit, no
push, no PR, no stash.

## The gesture is two steps, and cannot be one

```
sd-handoff --summary "..." --next "..." --dont "..."
/clear
```

A hook has no access to the conversation, so only the model can write
`summary`, `next` and `dont`. Writing is therefore an explicit call, never
automatic.

## Where the packet lives

`~/.local/state/sd-ai-command-pack/handoff/<digest>.json`, where `<digest>` is
the sha256 of the **normalized worktree root**: `--cwd`, then `$PWD`, then
`CLAUDE_PROJECT_DIR`, then `git rev-parse --show-toplevel`. Restore refuses a
packet whose recorded root is not a prefix of the cwd, or whose `head_sha` is
not an object in the current repo.

## What it holds

`repo` (root, branch, head), an optional `item`, `summary`, `next[]`, `dont[]`,
`questions[]`, and `files[]` from `git status`. A packet expires after 14 days.
The cap is 8 KB; over it, the tool refuses and says what to cut.

## Flags

See `sd-handoff --help`. `--show` prints the pending packet and consumes it.
It is the load path for a session whose host has no SessionStart hook.

## The restore side

`sd-handoff-restore` runs on the SessionStart matchers `startup|clear` only
(R10-D3): never `compact` and never `resume`. A compact matcher would consume
the packet in the dying session, so the `/clear` after it would find nothing.
The hook exits silently when `SD_HANDOFF_RESTORE=0` is set. Nothing sets it for
you, so an unattended `-p` job must set it in its own environment, or a packet
is eaten. Otherwise the hook injects the packet with its age and marks it
consumed.

The same hook also injects this checkout's open `followup` and `question`
notes, as `sd_db.note_brief` renders them, with or without a packet. The
restored session's setup step, before it resumes writing any file the packet's
`files[]` lists, is `sd-rules --for <path>`, run from the repository root.
Notes are not claimed; `sd note resolve <id>` closes one.

## Never

- **Never write a packet automatically.** No SessionEnd or PreCompact hook.
- **Never commit, push, stash, or open a PR from the default lane.**
- **Never consume a packet you are only inspecting.** The handoff section of
  `sd-status` reads without consuming; `--show` consumes.

## Lane B is not implemented

The design gave Lane B the carrier-branch push, with draft conversion and the
Copilot re-request suppressed (R10-D2). `bin/sd-handoff` has no push flag and
no park flag. If you need a carrier branch, commit and push under `sd-ship`.
