# Design — derive the fleet-publish allowlist from manifest.json

## Scale of the drift, measured

Comparing the literal `DEFAULT_ALLOWED_PREFIXES`
(`scripts/sd-ai-command-pack-fleet-publish.py:76-92`) against this checkout's
`.sd-ai-command-pack/manifest.json`:

- **456 of 725** payload targets are not covered by the tuple.
- 13 target roots are missing entirely: `.agent`, `.codebuddy`, `.devin`,
  `.factory`, `.gito`, `.kilocode`, `.pi`, `.prism`, `.reasonix`, `.trae`,
  `.zcode`, `docs`, `scripts`.
- Five tuple entries match no manifest target at all: `.trellis/`, `.codex/`,
  `.sd-ai-command-pack/`, `docs/repomix-map.md`, `.gitignore`.

The last line is the important one: four of those five are *correct* residue
(not installer-owned), and one — `.codex/` — is stale. So the tuple has drifted
in both directions at once. `scripts/`, the symptom that opened this task, is
one of thirteen.

## D1 — Source of truth: the consumer's manifest, not its installed-targets receipt

Both live in the consumer. `installed-targets.txt` records what the installer
actually wrote; `manifest.json` `files[].target` records every target the
installed payload declares.

**Decision: `manifest.json`.** A thin receipt deliberately omits
machine-provided surfaces, and the repo already treats the receipt as an
unsafe basis for exactly this kind of inference:

> A thin receipt no longer lists the machine-provided surfaces, so inferring
> platforms from it would shrink the set to whatever happens to be
> repo-native — and every fleet reader comparing installed platforms against
> the registry would then reject the consumer.
> (`installer/inspection.py:244-250`)

Deriving the gate from the receipt would reproduce that bug as a false
refusal on every thin consumer: the installer rewrites a machine-provided
surface, the path shows dirty, the receipt never listed it, the gate refuses.
`manifest.json` does not shrink under thin mode.

Secondary reason: the receipt cannot describe a *deleted* target. A payload
that drops a file leaves a `D` entry in `git status` whose path is absent
from the freshly written receipt. The manifest of the version being installed
still declares it only while it exists, so neither source solves deletion
perfectly — see D4.

## D2 — Pack-side registry is not the source either

`fleet-publish` runs from the pack checkout against `--repo <consumer>`, so
`installer/registry.py` is importable. It is still the wrong input: it
describes what *this* pack version could install for *any* platform
selection, not what this consumer has. Using it would widen the gate on every
consumer to the union of all platforms, which is the opposite of failing
closed. The consumer's own manifest is both narrower and per-consumer
correct.

## D3 — Shape: directory prefixes for dotted platform roots, exact paths otherwise

The gate is prefix-based (`is_allowed`, `:168-170`). Converting 725 exact
targets into 725 prefixes is correct but wasteful and brittle against
byproducts: an installer that writes `.claude/skills/x/SKILL.md` may leave
`.claude/skills/x/` containing a file the manifest does not name, and an
exact-path set refuses it.

**Decision:** for a target whose first segment begins with `.`, contribute
that segment plus `/` (`.claude/`, `.prism/`). For any other target,
contribute the exact target path (`scripts/sd-ai-command-pack-check.py`,
`docs/SD_AI_COMMAND_PACK.md`). Dotted roots are pack-owned directories where
directory-level trust is already the established posture; `scripts/` and
`docs/` are shared with the consumer's own work and must stay file-exact. The
old tuple's `docs/repomix-map.md` entry is evidence that this distinction was
already understood informally.

### D3a — "exact" needs a separate matcher, because the gate only knows prefixes

`is_allowed` (`:168-169`) is
`path == prefix or path.startswith(prefix)`. Feeding it an exact file path
does **not** produce exact matching: a derived `scripts/a.py` would also
sanction `scripts/a.py.orig`, `scripts/a.pyc`, and anything else sharing that
string prefix. An editor backup beside a managed script would pass the gate
and land in the publication commit — the precise leakage this gate exists to
stop. A test asserting that `scripts/b.py` is refused passes while the hole
stays open, so the obvious test does not catch it.

Widening `is_allowed` to treat every non-`/`-terminated entry as exact is
rejected: `--allow-path-prefix` is documented as a *prefix* and the PRD
requires its semantics unchanged, so an operator passing `docs/rep` must keep
working.

**Decision:** carry two sets. `is_allowed(path, prefixes, exact)` returns true
when `path` is in `exact`, or matches `prefixes` under the current rule.
Derived dotted roots, the residue, and every `--allow-path-prefix` value go
into `prefixes` with unchanged behavior; derived non-dotted targets go into
`exact`. This is the only signature change in the module.

## D4 — Residue, and why each entry stays

Kept explicit, each with an ownership comment, because none is installer-owned.
The residue splits the same way derived targets do (D3a): `.trellis/` and
`.sd-ai-command-pack/` are directories and stay in `DEFAULT_ALLOWED_PREFIXES`;
`docs/repomix-map.md` and `.gitignore` are files and belong in
`DEFAULT_ALLOWED_EXACT`. Leaving a residue file in the prefix tuple reopens the
D3a hole one layer up — `startswith` would sanction `.gitignore.bak` and
`docs/repomix-map.md.orig`. Pinned by
`test_residue_file_entries_are_exact_not_string_prefixes`.

| Entry | Owner |
| --- | --- |
| `.trellis/` | Trellis; the active task and journal are dirty by design here |
| `.sd-ai-command-pack/` | the installer's own receipts, not a payload target |
| `docs/repomix-map.md` | the map generator, regenerated post-archive |
| `.gitignore` | housekeeping's managed KB block |

`.codex/` is **dropped**. It matches no manifest target in this checkout, and
on a consumer that does install codex surfaces the manifest supplies it
automatically. This is the intended behavior change: a stale platform
directory left by an older install is no longer silently sanctioned. Risk and
mitigation in D6.

Deletion (D1's open edge) is handled by residue too: a `D` entry under a
dotted platform root still matches that root's prefix. A deleted `scripts/`
or `docs/` file whose exact path left the manifest refuses, and names itself.

## D5 — Failure is refusal with a reason code, never a default

`derive_allowed_paths(repo)` raises `PublishError(code=3)` when
`.sd-ai-command-pack/manifest.json` is absent, unreadable, not a JSON object,
lacks a list `files`, or yields zero usable targets. Reason codes, stable and
named in the message:

- `manifest_missing`
- `manifest_unreadable`
- `manifest_malformed`
- `manifest_targets_empty`

An entry that is not a mapping, or whose `target` is not a non-empty string,
is skipped rather than fatal — one malformed row must not strand a publish —
but if skipping empties the set, `manifest_targets_empty` fires. Absolute
paths and any target containing a `..` segment are skipped and counted; the
count appears in the refusal message when the set ends up empty, so a
pathological manifest cannot masquerade as a missing one.

No fallback to the old literal. A silent fallback is precisely the failure
mode this task exists to remove.

## D6 — Risk: a consumer that legitimately has a stale platform directory

Dropping `.codex/` and narrowing `docs/` to exact manifest targets means a
consumer carrying an older install's leftovers now refuses where it
previously passed. That is the correct direction — the helper is asking "did
the installer write this?" and the answer is no — but it can stall a fleet
lane.

Mitigations, in order: the refusal message names the derived source and entry
count so the operator can see *why* a path is unrecognized; `--allow-path-prefix`
keeps its current semantics as the deliberate override; and the fleet lane
already treats a publish refusal as a per-consumer skip with a reason, not a
campaign abort.

Not mitigated by widening the derived set. If leftovers are common, the fix
is an installer cleanup pass, which is out of scope here.

## D7 — Compatibility with the existing call shape

`check_preconditions` gains the `exact` set alongside `prefixes` (D3a); the
resolver returns both and runs in `publish()` before it, where
`repo` is already bound (`:421`) and `--allow-path-prefix` values are
appended to `prefixes` exactly as today (`:422`).
`DEFAULT_ALLOWED_PREFIXES` survives as the residue-only constant with its
ownership comments, so the name still means "what the helper trusts without
asking the manifest".

Six existing call sites pass `publish.DEFAULT_ALLOWED_PREFIXES` directly
(`tests/test_fleet_publish.py:69,92,120,130,406,409`); five feed
`check_preconditions` and one asserts membership. Their meaning changes
under this design: `.agents/` is no longer in that constant. They must be
updated to resolve through the new function, which is implementation work,
not a compatibility break in the shipped contract — `fleet-publish` is a
repo-owned controller script with no consumer-facing API.

## Rollout and rollback

Repo-owned script (`scripts/` has no `templates/` twin for the `fleet-*`
family, confirmed by enumerating the directory), so no `make sync` round
trip and no payload version bump. Rollback is reverting the commit; nothing
persists in consumer state.
