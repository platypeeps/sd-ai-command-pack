# Design — agent kind and subagent capability gate

## Scope boundary

Plumbing only: one registry field, one manifest kind, one renderer, and the
manifest rows that follow. **No agent bodies.** The first named agents
(sd-audit-reviewer, sd-audit-refuter, sd-ci-triager) belong to
`07-25-worker-agents`, which this task blocks. Shipping this task with zero
agent sources and zero rows is a valid end state — the capability gate is
testable without an agent existing.

Cross-program: the SE pack's shipped `skill_review.py` AST-parses
`installer/registry.py` structures of **both** checkouts. Reshaping
`PlatformInfo` changes what installed copies parse. se-ai-command-pack
`07-25-audit-registry-snapshot-contract` lands first or in the same window.

## Confirmed measurements

Everything below was re-derived from source on 2026-07-28. Several PRD claims
did not survive.

### 1. The support matrix disagrees across all three available sources

R1 asks for a capability field "with values covering: MD-dialect native file,
TOML (codex), JSON (kiro), none (devin, trae, qoder, zcode, pi, reasonix,
shared)". Three sources purport to answer which platform supports agent files,
and they contradict each other on 11 of 17 platforms:

| source | supporters |
|---|---|
| parent `design.md` §1.2 (binding) | claude, gemini, github, opencode, cursor, kiro, droid, codebuddy, antigravity, **codex** (TOML) |
| registry `trellis_local_only` agent globs | claude, codebuddy, codex, cursor, gemini, kiro, pi, qoder, trae, zcode |
| files actually on disk in this checkout | claude, codex, gemini, opencode, github |

Concretely:

- `trae`, `qoder`, `zcode`, `pi` are declared `none` by R1 and by the parent
  design, yet the registry reserves agent paths for all four
  (`registry.py:405`, `:357`, `:431`, `:331`).
- `github`, `opencode`, `droid`, `antigravity` are declared supporters by the
  parent design, yet none has an `agents/` glob in `trellis_local_only` — while
  `.github/agents/` and `.opencode/agents/` each hold three real files.

Only **claude, codex, gemini** appear in all three. The parent design's own
phrase — "Trellis's `.trellis/agents/` -> five-platform fan-out in this
checkout is the working reference" — matches the disk column exactly:

```
.claude/agents:   3    .codex/agents:  3    .gemini/agents:  3
.opencode/agents: 3    .github/agents: 3    (all others: 0)
```

**Disposition:** the disk column is the source of truth, because it is the only
one that has been executed. The registry column is a Trellis-side *reservation*
(paths ignored if present), not a capability claim, and R1 should stop treating
it as one. The parent design's list is a research summary; where it disagrees
with a directory that demonstrably works, the directory wins. The design records
this and does not silently pick.

### 2. Manifest kinds are descriptive, not dispatching

`grep` for kind branching across `installer/*.py` returns exactly two sites:

- `installer/manifest.py:113` — the validation gate
- `installer/provenance.py:101` — a special case for `MANAGED_BLOCK_KIND` only

Nothing in install, status, remove, audit, or check dispatches on `skill` vs
`command` vs `script`. So R2's "manifest schema gains kind `agent`" is a
one-member addition to a frozenset, and rows then flow through install →
status → check → audit → remove with no per-kind code. That is the good news in
this task and it should be stated rather than rediscovered.

### 3. Three hardcoded kind lists, one of them a shipped byte-identical mirror

`KNOWN_MANIFEST_KINDS` is not the only list:

```
installer/manifest.py:31                              frozenset (8 members)
scripts/sd-ai-command-pack-surface-check.py:253       tuple, hardcoded
templates/scripts/sd-ai-command-pack-surface-check.py:253   byte-identical mirror
```

`diff -q` on the pair reports identical. Missing the mirror means `make
generate` output validates locally and fails for an installed consumer. This
also intersects `07-28-stop-committing-generated-mirrors`, which is changing
how that mirror class is maintained.

### 4. The registry already encodes agent paths and dialects — and its globs are
name-scoped, which is what makes the `sd-` prefix load-bearing

`registry.py` already carries per-platform agent targets with their dialects:
`.claude/agents/trellis-*.md`, `.codex/agents/trellis-*.toml`,
`.kiro/agents/trellis*.json`, `.gemini/agents/trellis-*.md`, and so on. Every
one is scoped to `trellis-*`.

That is the mechanical reason R4's "collision-safe `sd-` prefix" is not
cosmetic: pack-owned `sd-*.md` files land in the same directories and are
*outside* every Trellis-local glob, so they remain pack-managed and removable.
Name a pack agent `trellis-anything` and it disappears into the Trellis-local
carve-out.

There is a hard invariant behind those tuples.
`tests/test_install_core.py:2111` asserts every `trellis_local_only` entry
appears verbatim in `scripts/sd-ai-command-pack-review-scope.sh`. Do not add
pack agent paths to `trellis_local_only`.

**zcode carries two agent directories** — `.zcode/agents/` and
`.zcode/cli/agents/` (`registry.py:431-432`). A single
`agent_target_pattern` string cannot express that. R4's wrinkle list does not
mention it. zcode is out of wave 1, so the field shape only has to not
*preclude* a later dual target.

### 5. `SKILL_FANOUT_PLATFORMS` is not a capability list — do not reuse it

`registry.py:456` is antigravity, codebuddy, devin, droid, kilo, kiro, pi,
qoder, reasonix, trae. It contains none of claude/codex/gemini. It means
"platforms whose command surface is skills-only, having no bespoke adapter" —
the complement of the bespoke-adapter set, not a statement about support.

### 6. R1 names the wrong model

`structured_question_tool` is `str | None` naming a *runtime tool*, set on 2 of
18 rows (`registry.py:80`, `:125`), read at `registry.py:1062` and
`generate-command-surfaces.py:490`. It gives a None-gate and nothing else.

The right model is one row up: `command_kind` + `command_target_pattern`
(`registry.py:25-26`). That pair already expresses *dialect* and *where the file
goes*, and already gates on None in both consumers:

```python
registry.py:448                    if info.command_kind and info.command_target_pattern
generate-command-surfaces.py:713   if not info.command_kind or not info.command_target_pattern:
```

Modeling on `structured_question_tool` yields a capability flag that still needs
a second field for the path. Modeling on `command_kind` yields one shape already
proven across 11 platforms, with the None-gate R2 requires.

### 7. R5 rests on a name collision

`sd-check`'s `kind` is a different vocabulary: `builtin`, `prerequisite`,
`check` (`scripts/sd-ai-command-pack-check.py:880`, `:1004`, `:1022`). It is the
check-*result* kind, not the artifact kind, and has no relationship to
`KNOWN_MANIFEST_KINDS`. R5 as written asks to extend a contract that does not
contain artifact kinds. What R5 actually needs is confirmation that
`--audit`/`--status` inspection enumerate manifest rows generically — which,
per measurement 2, they do.

### 8. The gitignore-tuple invariant is a non-event as scoped

`tests/test_install_core.py:2016-2027` requires any platform carrying
`local_gitignore_patterns` or `trellis_local_only` to hold a slot in
`install._LOCAL_GITIGNORE_GROUP_ORDER` / `_LOCAL_ONLY_GROUP_ORDER`. Adding a
capability field touches neither tuple. R2's "gitignore-tuple invariants
extended" only becomes real work if agent rows introduce new local-only or
ignore data — and per measurement 4 they must not.

## The central tension

R6 defers the wave-1 platform set to this design, and the evidence in
measurement 1 forces the answer rather than leaving it to taste.

**Wave 1 = claude + codex.** Both are in all three source columns, and codex is
the TOML dialect, so wave 1 exercises the two-dialect renderer immediately
instead of shipping an MD-only path that pretends to be general.

**gemini is the free third** and should be included: also triple-confirmed, MD
dialect, no new renderer code. Its wrinkle (subagents run without per-tool
confirmation) is a content constraint on the agent body — tools scoped tightly
— which is enforceable in the renderer's frontmatter emission and testable
without a real agent.

**github and opencode wait.** Both have working directories on disk, so they are
the obvious wave 2 — but `.github/agents/*.agent.md` carries the 30,000-char cap
(R4) and a `.agent.md` double extension that no other platform uses, and neither
appears in the registry column. Adding them later is an additive registry row,
which is exactly what R6 requires of the design.

**Everything else is `none` for now**, including kiro. R1 lists JSON (kiro) as a
dialect to cover; measurement 1 shows kiro has a reserved path and zero files.
Building a third renderer dialect for a platform with no working reference is
speculative work. Record kiro's JSON dialect in the field's docstring as the
known shape; implement it when a kiro agent exists.

This narrows R1's stated scope. That narrowing is the design decision R6 asked
for, and it is stated rather than absorbed.

## Contract

**Registry field** — modeled on `command_kind`/`command_target_pattern`, not on
`structured_question_tool`:

```python
agent_kind: str | None = None            # "markdown" | "toml" | "json"; None = unsupported
agent_target_pattern: str | None = None  # e.g. ".claude/agents/{filename}"
```

Both None on every platform outside wave 1. The pair-gate
(`if not info.agent_kind or not info.agent_target_pattern`) is the capability
gate R2 wants and produces zero rows by construction, not by filtering.

**Manifest row** — shaped like `_platform_skill_entry`
(`generate-command-surfaces.py:727-734`), with the shared/per-platform
distinction that function's neighbours already draw: the `shared` row carries
`install: "always"` and no `anchor`; per-platform rows carry `anchor` and no
`install`.

```python
{
    "platform": platform,
    "kind": "agent",
    "source": f"templates/.agents/agents/{name}.md",   # canonical neutral MD
    "target": info.agent_target_pattern.format(filename=...),
    "anchor": info.directory,
}
```

**Naming** — every pack agent is `sd-<role>`. Enforced, not conventional: the
`trellis-*` globs in measurement 4 are what a non-`sd-` name would collide with.

**Kind registration** — all three lists in measurement 3, in one commit.

## Compatibility

Zero agent sources means zero agent rows, so a consumer that installs this
version sees an unchanged file set. The manifest gains a kind it does not yet
use. That is the intended shipping state for this task and it makes the
installer round-trip in AC1 testable with a fixture agent rather than a real one.

`trellis_local_only` is untouched, so `review-scope.sh` classification and the
`_LOCAL_ONLY_GROUP_ORDER` byte-stability tuple are untouched.

The two consumers that must move together:

- se-ai-command-pack `skill_review.py` AST-parses `PlatformInfo` — coordinate
  with `07-25-audit-registry-snapshot-contract`.
- `templates/scripts/sd-ai-command-pack-surface-check.py` is a byte-identical
  mirror; `07-28-stop-committing-generated-mirrors` is changing that class.

## Rollout and rollback

Three commits, each independently revertible:

1. **Kind registration.** All three lists plus a validation test. No rows, no
   renderer. Reverting is a frozenset member.
2. **Registry field.** `agent_kind` + `agent_target_pattern`, both None on all
   18 rows, plus the pair-gate test asserting zero rows everywhere. Reverting is
   two dataclass fields with defaults — no call site changes because every
   consumer gates on None.
3. **Renderer + wave-1 rows.** Populate claude/codex/gemini, add the MD and TOML
   emitters, regenerate. This is the only commit that changes generated output.

Commits 1 and 2 are inert by construction — they add a vocabulary and a field
that nothing populates. Commit 3 is the one that can produce a bad diff, and it
is bounded by three platforms.

Rollback of commit 3 removes agent files from installed checkouts on the next
`sd-check`/remove pass, which is correct: they are pack-managed rows with normal
removal semantics, which is what R2 asks for.

## Risk

1. **Shipping R1's matrix verbatim.** It marks trae/qoder/zcode/pi as `none`
   while the registry reserves agent paths for them, and marks github/opencode
   as supporters while they have no registry entry. Encoding either list without
   reconciling produces a capability field that contradicts the file tree on day
   one. Measurement 1 is the whole reason this design exists.
2. **A pack agent named `trellis-*`.** It silently enters the Trellis-local
   carve-out, stops being pack-managed, and survives removal. The `sd-` prefix
   must be enforced by the generator, not assumed.
3. **Missing the shipped `surface-check.py` mirror.** Local validation passes,
   installed consumers reject the new kind. One `diff -q` catches it.
4. **The SE pack's registry parser.** Out of this repo's test reach entirely;
   only cross-program sequencing protects it.
5. **Building the kiro JSON dialect on spec.** Zero working references. Deferring
   it is cheap; building it is a renderer branch nothing exercises.
6. **zcode's dual agent directories** breaking a single-pattern field later.
   Out of wave 1, but the field shape should not preclude a tuple-valued target.
