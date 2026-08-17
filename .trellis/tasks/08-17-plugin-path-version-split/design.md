# Design: one way for a skill to reach a pack helper

## What the investigation changed

The PRD was written from the symptom — a `PATH` entry naming `sd/0.71.22/bin`
under an installed 0.71.29 — and inferred that shipped skills call helpers by
bare name and let `PATH` decide. Enumerating every
`sd-ai-command-pack-*.{mjs,py,sh}` reference under `.agents/skills/` says
otherwise. `prd.md` carries the dated amendment; the two facts that drive this
design are:

**The resolver already exists and is already correct.**
`scripts/sd-ai-command-pack-toolchain.sh:42-61`
(`resolve_pack_script_operand`) takes a helper operand, strips a `scripts/`
prefix, and resolves the name **next to the toolchain script itself**
(`$SCRIPT_DIR`). Its own comment states the guarantee: "Own location wins
outright and the working directory is never probed, so a repository cannot
shadow a pack helper with a same-named file of its own." A helper reached
through the toolchain is therefore always from the same install as the
toolchain. There is no version split along that path, and there never was.

**The bug is one level up: how a skill finds the toolchain.** Every skill
writes `bash scripts/sd-ai-command-pack-toolchain.sh …`. That leading path is
working-directory-relative and is not resolved by anything. A thin consumer has
no `scripts/sd-ai-command-pack-*` at all — verified across the fleet — so the
bootstrap fails before the resolver is ever reached.

So the task is not "make every call site version-safe." It is "make the one
bootstrap correct, and route the handful of calls that bypass the resolver back
through it."

## The two call classes

Enumerated from `.agents/skills/`, not from the PRD:

| Class | Shape | Sites | Resolution today |
|---|---|---|---|
| A | `bash <scripts-prefixed toolchain> run[-python] -- <helper>` | 50 | operand already correct; **bootstrap** is CWD-relative |
| B | `node`/`bash` invoking a scripts-prefixed helper directly | 9 | none — bypasses the resolver entirely |

Class B, exhaustively — `sd-fleet-refresh:180`, `sd-review-pr:234`,
`sd-review-pr:776`, `sd-finish-work:85`, `sd-finish-work:150`,
`sd-housekeeping:22`, `sd-housekeeping:30`, `sd-update-deps:84`,
`sd-create-pr:218`.

The eleven bare-name occurrences `prd.md` counts are a **different set** from
class B, not a subset of it — disjoint lines, overlapping only in which skills
they fall in. They are also mostly not call sites: ten are the helper named
rather than run — nine in prose, one inside an error message
(`sd-create-pr:215`) — and two of the prose ones (`sd-review-pr:262-263`)
instruct the reader *not* to use the scripts they name. Only `sd-create-pr:213`
is executable, and it is a `command -v` guard rather than an invocation. Naming
a helper is a documentation concern, not a resolution one, and this design does
not touch it.

## The rule

> A shipped skill reaches a pack helper only through the toolchain, and locates
> the toolchain with the documented bootstrap. Nothing else.

Two parts, because the bootstrap is the one thing that cannot itself go through
the toolchain.

### Part 1: the bootstrap

One snippet, stated once in a reference file and cited by every skill rather
than re-derived:

```bash
SD_PACK_TOOLCHAIN=""
for candidate in \
  "${SD_AI_COMMAND_PACK_TOOLCHAIN:-}" \
  "scripts/sd-ai-command-pack-toolchain.sh" \
  "$HOME/.agents/bin/sd-ai-command-pack-toolchain.sh"
do
  [ -n "$candidate" ] && [ -f "$candidate" ] && { SD_PACK_TOOLCHAIN="$candidate"; break; }
done
[ -n "$SD_PACK_TOOLCHAIN" ] || {
  printf '%s\n' "error: sd-ai-command-pack toolchain not found (checked SD_AI_COMMAND_PACK_TOOLCHAIN, scripts/, and \$HOME/.agents/bin); reinstall the command pack" >&2
  exit 1
}
```

Order is the design decision:

1. `SD_AI_COMMAND_PACK_TOOLCHAIN` — explicit override, for testing a
   deliberately constructed split (an acceptance criterion needs this) and for
   a developer pointing a consumer at a work-in-progress checkout.
2. `scripts/` — when it exists, the working directory *is* a pack source
   checkout, and a pack developer editing helpers must run the edited ones. A
   consumer never has this directory, so it costs consumers nothing.
3. `$HOME/.agents/bin` — the machine install. This is not a new convention:
   `docs/fleet/consumers.json` already invokes two helpers as
   `node "$HOME/.agents/bin/sd-ai-command-pack-review-preflight.mjs"` and
   `bash "$HOME/.agents/bin/sd-ai-command-pack-housekeeping.sh"`. The skills are
   adopting a rule the fleet manifest already uses.

Notably absent: `PATH`. `PATH` is where the reported defect comes from —
Claude Code prepends a cached plugin root, first match wins, and the oldest
surviving entry answers. Resolving the bootstrap through `PATH` would
reintroduce exactly the split this task exists to close. `$HOME/.agents/bin` is
**not** on `PATH` on the reporting machine, so preferring it is also the change
that makes the two disagree visibly rather than silently.

`CLAUDE_PLUGIN_ROOT` is rejected for a different reason: the pack ships to
`claude`, `gemini`, `github`, and `opencode`, and a Claude-only variable cannot
be the one rule requirement 2 asks for.

### Part 2: class B routes through the toolchain

`toolchain.sh run -- <operand>` applies `resolve_pack_script_operand` to the
operand and `exec`s it. Both class-B helpers are directly executable with
shebangs (`#!/usr/bin/env node`, `#!/usr/bin/env bash`), verified in the machine
install, so each site becomes:

```bash
bash "$SD_PACK_TOOLCHAIN" run -- sd-ai-command-pack-review-preflight.mjs …
bash "$SD_PACK_TOOLCHAIN" run -- sd-ai-command-pack-housekeeping.sh …
```

One trap to avoid: `run` resolves only its **first** operand. Writing
`run -- node sd-ai-command-pack-review-preflight.mjs` resolves `node` (not a
pack name, returned unchanged) and leaves the `.mjs` argument unresolved, which
fails. The interpreter must not be named; the helper's shebang supplies it.

## The `sd-create-pr` defect

`sd-create-pr/SKILL.md:213-218` is a live bug that this design closes as a side
effect, and it is worth stating separately because it is **version-independent**
— it fails identically when every install agrees:

```bash
if ! command -v sd-ai-command-pack-review-preflight.mjs >/dev/null 2>&1 \
  && [ ! -f scripts/sd-ai-command-pack-review-preflight.mjs ]; then
  printf '%s\n' "error: … not resolvable on PATH or under scripts/…" >&2
  exit 1
fi
node scripts/sd-ai-command-pack-review-preflight.mjs
```

The guard accepts `PATH` **or** `scripts/`; the invocation unconditionally uses
`scripts/`. On a thin consumer the helper is on `PATH` and absent from
`scripts/`, so the guard passes and the next line throws. Reproduced read-only
in `~/repos/platypeeps/loadsmith`:

```
guard: PASSES (helper is on PATH)
scripts/ copy: ABSENT
node:internal/modules/cjs/loader:1573
  throw err;
```

The failure disables the pre-publication preflight that `sd-create-pr` runs
before staging, committing, or pushing — the gate the skill's own text calls
non-substitutable. Under the new rule the guard disappears entirely: the
bootstrap's failure branch is the diagnosis, and the invocation and the check
can no longer disagree because there is only one of them.

## Requirement 1: what "names both versions" can actually mean

Requirement 1 asks that a skill's helper invocations resolve to the same install
the skill text came from, or stop with both versions named. Half of that is not
observable from a shell: **nothing in the process can see which `SKILL.md` text
the agent loaded.** A design that claims to check it would be lying.

What is observable, and what this design commits to:

- **Coherence is structural, not checked.** Every helper comes from
  `$SCRIPT_DIR` of the resolved toolchain, so a run cannot mix two installs. The
  guarantee is by construction; there is no runtime comparison to get wrong.
- **Disagreement is reported, not resolved.** When the resolved toolchain's
  install differs from the machine install, or a `PATH` entry names a third,
  that is a real observable and belongs in `sd-status` (requirement 3) — not in
  a per-invocation check that would add a version probe to all 50 sites.

So requirement 1 is met by making a split *impossible along the executed path*,
and requirement 3 by making a split *visible* when the environment still has
one. The residue — a skill loaded from a root nobody can name — is recorded as a
limit here rather than papered over.

## Requirement 3: what `sd-status` adds

One machine-scope row, beside the existing install-versus-target line, and
explicitly not overloading it:

- the toolchain the bootstrap would resolve, and its install root;
- every `PATH` entry naming a pack `bin/`, in `PATH` order;
- a comparison verdict: `bound` when the bootstrap's answer is the only pack
  install reachable, `shadowed` when a `PATH` entry names a different one.

`shadowed` is the reporting machine's current state and must render as such
rather than as an error, because the new rule makes it harmless — the skills no
longer read `PATH`. It is reported so an operator can see the stale cache
without reproducing it by hand, which is exactly what requirement 3 asks and
what the existing `comparison: current` line does not say.

## Gate

A repository-wide check in `make check` that fails on the forbidden forms:

- any `scripts/sd-ai-command-pack-` in a shipped skill's executable block;
- any `node`/`bash`/`python3` directly invoking a `sd-ai-command-pack-*` helper;
- any pack helper named as the second operand of `run --`.

The gate enumerates from the filesystem — every `SKILL.md` under
`.agents/skills/` — rather than from a list of known sites, so a skill added
later is covered without editing the gate.

## Tradeoffs and what this costs

**The `scripts/`-before-machine-install order is the contentious choice.** It
means a pack source checkout keeps using its own helpers, which is the behavior
that lets a developer test an edit at all, but it also means a stale checkout
shadows a newer machine install. That is acceptable here and not elsewhere: a
pack checkout is a place someone is deliberately editing helpers, and
`sd-status` reports the resulting disagreement. The alternative — machine
install always — makes pack development require an install round-trip per edit.

**50 mechanical edits across 22 files in 16 skills.** Large diff, low risk
each, and the
gate prevents regression. The alternative of leaving class A alone and fixing
only class B was considered and rejected: class A is the majority of the
breakage on thin consumers, which is requirement 4.

**This does not prune the plugin cache or touch `PATH`,** per requirement 5.
The 12 retained versions and 63 MB stay. What changes is that they stop being
consulted.

## Out of scope

- Pruning the plugin cache, or asking Claude Code to change how it builds
  `PATH`. Upstream-fixable accumulation is `08-08-upstream-handoff-register`.
- The machine install's missing `installer/` package (`#496`).
- Prose in skills that names a helper without invoking it. Nine such
  occurrences exist; none is a resolution defect.
- The machine-scope install-versus-target skew and the duplicate-registration
  reconciliation — both closed in `#497`, released in v0.71.29.
- Consumer pack pins, which are `08-08-fleet-one-path`'s rollout ledger.
