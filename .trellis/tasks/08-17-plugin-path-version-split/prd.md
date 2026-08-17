# Pack binaries resolve from a stale plugin-cache PATH entry, not the loaded skill's root

## Goal

Make a pack skill and the pack binaries it invokes come from the same install,
or fail loudly when they cannot. Today the two are resolved by different
mechanisms that are free to disagree, and nothing reports the disagreement.

## Problem

Claude Code prepends each enabled plugin's `bin/` directory to `PATH`. The
entry names a specific cached version, and it is written at session start. The
skill text the session actually loads is resolved separately, from the plugin
root in effect for that session. Nothing binds the two.

Measured on this machine, 2026-08-17, immediately after updating the plugin
from 0.71.22 to 0.71.29:

```
$ echo "$PATH" | tr ':' '\n' | grep sd-ai-command-pack
/Users/sven/.claude/plugins/cache/sd-ai-command-pack/sd/0.71.22/bin

$ python3 -c '...installed_plugins.json...'
user 0.71.29 -
```

The running session resolves every bare `sd-ai-command-pack-*` name to 0.71.22
while the installed plugin is 0.71.29. The operator report of this defect
described the same split at a different pair of versions: binaries at 0.71.13
under a skill loaded from 0.71.14.

Two properties make this more than a restart-shaped inconvenience.

**Stale entries accumulate and are never pruned.** The same `PATH` in this
session carries duplicate and divergent plugin roots for four plugins:

```
 1  .../thedotmack/claude-mem/13.13.1/bin
 5  .../thedotmack/claude-mem/13.15.0/bin
 2  .../openai-codex/codex/1.0.6/bin
 6  .../openai-codex/codex/1.0.6/bin
 3  .../caveman/caveman/0d95a81d35a9/bin
 7  .../caveman/caveman/ec83e5bace4c/bin
 4  .../claude-hud/claude-hud/0.6.0/bin
 8  .../claude-hud/claude-hud/0.6.0/bin
```

First match wins, so the *oldest* surviving entry is the one that answers. The
pack's own cache retains 12 versions from 0.71.1 to 0.71.29, 63 MB, with no
mechanism that removes one.

**The pack invokes its binaries by bare name.** Shipped skills call
`sd-ai-command-pack-review-preflight.mjs`, `sd-ai-command-pack-pr-eligibility.py`,
`sd-ai-command-pack-full-check.sh`, and six more without a path, and zero
shipped skills reference `$HOME/.agents/bin` or `CLAUDE_PLUGIN_ROOT`. Every one
of those calls is resolved by whatever `PATH` happens to name. A skill from one
release therefore drives helpers from another, silently, and the failure mode is
a validator or gate behaving to a contract the skill does not describe.

This is distinct from the machine-scope skew `sd-status` already reports. That
line compares the *installed* pack against the target and is now `current`;
it says nothing about which copy a given process will actually execute.

## Requirements

1. A pack skill's helper invocations resolve to the same install the skill text
   came from, or the run stops with a diagnosis naming both versions. Silent
   cross-version execution is the defect; picking a winner without saying so is
   not a fix.
2. The resolution rule is one rule, stated once, and every shipped skill uses
   it. Nine bare-name call sites across the skills are the current surface;
   the fix is not nine local edits that can drift apart again.
3. `sd-status` reports the split when it exists — the resolved binary version
   beside the loaded skill version — so an operator sees it without reproducing
   it by hand. The existing machine-scope line does not cover this and must not
   be overloaded to imply it does.
4. The reporting path works from a consumer checkout, where the pack is thin and
   the skill root is the machine install rather than a vendored tree.
5. Nothing in this task prunes another tool's plugin cache, edits `PATH` for the
   user, or writes into a consumer checkout. Cache retention is Claude Code's,
   not the pack's; this task may recommend, never reach in.

## Acceptance criteria

- [ ] A skill invoking a pack helper while `PATH` names a different pack version
      either executes the matching helper or fails with both versions named.
      Demonstrated against a deliberately constructed split, not only against a
      clean machine.
- [ ] Zero shipped skills invoke a `sd-ai-command-pack-*` helper by bare name,
      verified by a repository-wide grep that is part of `make check`.
- [ ] `sd-status` prints the resolved-binary-versus-loaded-skill comparison, and
      a test covers the disagreeing case.
- [ ] The comparison is correct from a thin consumer checkout, verified against
      at least one real consumer.
- [ ] `make check` passes.
- [ ] No consumer checkout and no plugin cache directory is modified.

## Out of scope

- Pruning the plugin cache, or asking Claude Code to change how it builds
  `PATH`. If the accumulation is upstream-fixable, that is a handoff for
  `08-08-upstream-handoff-register`, not work here.
- The machine-scope install-versus-target skew and the plugin-registration
  duplicate reconciliation. Both are closed: `#497`, released in v0.71.29.
- The machine install's missing `installer/` package, which makes a directly
  invoked `~/.agents/bin/sd-ai-command-pack-status.py` report machine scope
  unavailable. That is issue `#496` and it is a layout defect, not a version
  split.
- Consumer pack pins, which are `08-08-fleet-one-path`'s rollout ledger.

## Evidence

2026-08-17, this checkout, after `scripts/sd-ai-command-pack-pack-update.sh`
reported `machine: installed 0.71.29 / status: current`:

- `PATH` entry `.../sd/0.71.22/bin` against installed plugin 0.71.29.
- `which -a sd-ai-command-pack-housekeeping.sh` resolves into the plugin cache,
  not the machine install at `~/.agents/bin`.
- 12 retained cache versions, 63 MB, none pruned.
- Operator report of the same split at 0.71.13 binaries under a 0.71.14 skill.
