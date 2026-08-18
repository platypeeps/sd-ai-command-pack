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

## Which tree to edit

`AGENTS.md:36` — "Treat `templates/**` as the source of truth for shipped pack
payloads." The repository's own `.agents/skills/` and `.claude/skills/` are
**installed artifacts**: `make sync` runs `install.py . --force`, which
overwrites them from `templates/`. An earlier revision of this design named
`.agents/skills/` as the edit target, which would have produced a diff that the
next sync silently reverted.

There are three authored sources and two generated layers:

| Layer | Path | class A | class B | Edit? |
|---|---|---|---|---|
| authored | `templates/.agents/skills/**` | 50 | 9 | yes |
| authored | `templates/docs/SD_AI_COMMAND_PACK.md` | 15 | 8 | yes |
| authored | `.github/command-sources/*.md` | 2 | 0 | yes |
| generated | `templates/{.commands,.claude,.gemini,.github}/**` | 2 each | 0 | no — regenerate |
| generated | repo `.agents/skills/`, `.claude/skills/` | 50, 39 | 9, — | no — `make sync` |

**67 authored class-A sites and 17 authored class-B sites.** The generated
layers are refreshed by `make generate` and `make sync`; editing them by hand is
the mistake this section exists to prevent.

`templates/docs/SD_AI_COMMAND_PACK.md` is in scope and is not merely
documentation: it is installed into every consumer as `docs/SD_AI_COMMAND_PACK.md`
and its command examples are what an operator copies. Every one of them is
CWD-relative today, so every one fails in the thin consumer it was installed
into. Leaving the doc correct-looking while the skills are fixed would leave the
defect exactly where a human meets it first.

## The two call classes

| Class | Shape | Authored sites | Resolution today |
|---|---|---|---|
| A | `bash <scripts-prefixed toolchain> run[-python] -- <helper>` | 67 | operand already correct; **bootstrap** is CWD-relative |
| B | `node`/`bash` invoking a scripts-prefixed helper directly | 17 | none — bypasses the resolver entirely |

Class B in the skills, exhaustively — `sd-fleet-refresh:181`,
`sd-review-pr:234`, `sd-review-pr:776`, `sd-finish-work:85`,
`sd-finish-work:150`, `sd-housekeeping:22`, `sd-housekeeping:30`,
`sd-update-deps:84`, `sd-create-pr:218`, all under
`templates/.agents/skills/`. The remaining eight are command examples in
`templates/docs/SD_AI_COMMAND_PACK.md`.

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
for candidate in "${SD_AI_COMMAND_PACK_TOOLCHAIN:-}" \
  "scripts/sd-ai-command-pack-toolchain.sh" \
  "$HOME/.agents/bin/sd-ai-command-pack-toolchain.sh"; do
  if [ -f "$candidate" ]; then SD_PACK_TOOLCHAIN="$candidate"; break; fi
done
[ -n "$SD_PACK_TOOLCHAIN" ] || { printf '%s\n' "error: sd-ai-command-pack toolchain not found; checked SD_AI_COMMAND_PACK_TOOLCHAIN, scripts/, and \$HOME/.agents/bin. Reinstall the command pack." >&2; exit 1; }
```

**Amended 2026-08-17, during implementation.** An earlier revision of this
snippet spent two extra lines on `[ -n "$candidate" ] && [ -f "$candidate" ]`
and a three-line failure branch. `[ -f "" ]` is already false, so the emptiness
test was redundant, and the loop body is now an `if` rather than an `&&` chain
because a trailing failed `&&` is the loop body's exit status and would kill a
caller running under `set -e`. Seven lines instead of ten matters here: the
snippet is repeated in **54 fenced blocks** across the authored trees, so each
line costs 54.

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
  a per-invocation check that would add a version probe to all 67 sites.

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

**Amended 2026-08-17, during implementation.** Three refinements, all from
building it:

- A third verdict, `unresolved`, is required. "No candidate answered" is a
  different state from `bound` with nothing on `PATH`, and collapsing them
  would report a machine with no pack install as healthy.
- A `PATH` entry is recognized by *holding the toolchain file*, not by its name
  matching a pack `bin/` pattern. The filesystem answers the question a name
  pattern only guesses at, and it keeps a differently named install root
  visible.
- "Renders as advisory" is implemented as the row alone, with no anomaly entry.
  That follows this section's own framing — machine scope describes the
  machine, not the reported repository — and matches how the neighbouring
  `skew` comparison already behaves. An anomaly would have put `--expect-clean`
  in every repository under the operator's `PATH`.

## Gate

A repository-wide check in `make check` that fails on the forbidden forms:

- any `scripts/sd-ai-command-pack-` in a shipped skill's executable block —
  **including the toolchain's own operands**, see below;
- any `node`/`bash`/`python3` directly invoking a `sd-ai-command-pack-*` helper;
- any pack helper named as the second operand of `run --`.

The first rule admits no exception, and that costs an extra edit per operand.
`resolve_pack_script_operand` strips a `scripts/` prefix, so
`run-python -- scripts/sd-ai-command-pack-status.py` resolves correctly and a
narrower gate could allow it. It is still forbidden. A gate that permits
`scripts/`-prefixed operands has to distinguish the harmless prefix from the
CWD-relative bootstrap that is the entire defect, and a reader then cannot tell
by looking which `scripts/` token is which. Operands become bare helper names,
the rule stays "no `scripts/` in an executable block", and the gate says exactly
what the rule says.

The gate enumerates from the filesystem — every `*.md` under
`templates/.agents/skills/`, not just `SKILL.md`, plus
`templates/docs/SD_AI_COMMAND_PACK.md` and `.github/command-sources/**` —
rather than from a list of known sites, so a skill, reference document, or
command source added later is covered without editing the gate.

It scans the **authored** trees only. Running it over the generated copies as
well would report every defect twice and would fail a tree whose only repair is
`make generate` or `make sync`, which is a confusing way to say "regenerate". The wider glob is load-bearing: eight `references/` and `charters/`
files carry 13 of the 50 class-A occurrences and are executed exactly like
`SKILL.md` text, so a `SKILL.md`-only gate would pass a tree with thirteen live
defects in it.

## Tradeoffs and what this costs

**The `scripts/`-before-machine-install order is the contentious choice.** It
means a pack source checkout keeps using its own helpers, which is the behavior
that lets a developer test an edit at all, but it also means a stale checkout
shadows a newer machine install. That is acceptable here and not elsewhere: a
pack checkout is a place someone is deliberately editing helpers, and
`sd-status` reports the resulting disagreement. The alternative — machine
install always — makes pack development require an install round-trip per edit.

**84 mechanical edits across the three authored trees.** Large diff, low risk
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
