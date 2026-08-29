# Design — consumer-config layout shim

## D1 — The shim is a vendored copy of the resolver, not a launcher for it

The obvious shape is a small shell stub that finds the real resolver and execs
it. It is the wrong one, for a reason that is measurable rather than
aesthetic: **a stub that can find the resolver already contains the only hard
part of the resolver.** Locating the machine payload is the
`resolve_state_root` ladder; once a file carries that ladder it is no longer a
stub, and shipping both means two implementations of one question, one of them
vendored and therefore refreshed on a different cadence than the other.

So the shim is the existing `sd-ai-command-pack-review-layout.py`, installed a
second time at a path conversion keeps. One source, one implementation, two
install targets. That is already the dominant manifest pattern rather than a
novelty: 53 of the manifest's sources map to more than one target today
(`templates/.agents/skills/sd-help/SKILL.md` maps to 12).

Consequence worth stating plainly: thin conversion stops being "the consumer
keeps no pack code" and becomes "the consumer keeps one file." That is the
price of a fixed entrypoint and there is no version of this that avoids it —
a consumer that holds zero pack bytes has no way to name the pack that
conversion does not delete. Measured against
`docs/fleet/surface-partition.json` at manifest `0.71.10`, conversion removes
the two machine categories: `machine-claude` 80 plus `machine-other` 89, so
**169 rows**. One file against 169 is the trade this task proposes; the
alternative is not zero files, it is 68 bootstrap probes.

## D2 — Target: `.sd-ai-command-pack/bin/`, not `.claude/**`

| candidate | verdict |
|---|---|
| `.claude/sd-ai-command-pack/` | Already `consumer-config` (`partition-surfaces.py:115`), so it needs no partition change — and it fails R2. Both existing rows there carry `platform: "claude"`; a consumer that does not declare `claude` never installs them. Making the row `shared` instead would create a `.claude/` directory in a Gemini-only repository to hold a file Claude does not read. |
| `.sd-ai-command-pack/bin/` | Platform-neutral, and the directory is already present and **tracked** in every measured consumer (verified: `git ls-files .sd-ai-command-pack/` returns the receipts in all eight). Needs one new `TARGET_OVERRIDES` entry. |
| a new top-level directory | Same partition cost, plus a new directory in eight repositories, for no property the receipt directory lacks. |

`bin/` rather than the directory root: the override should be as narrow as the
thing it classifies. `.sd-ai-command-pack/**` would silently classify any
future row targeted at the receipt directory as `consumer-config`;
`.sd-ai-command-pack/bin/**` classifies exactly the code.

**The vendored copy keeps the basename it has**, giving the full target
`.sd-ai-command-pack/bin/sd-ai-command-pack-review-layout.py`. A shorter name
reads better and is worse. The resweep's rule 5
(`sd-ai-command-pack-thin-resweep.py:1239-1250`) counts a bare basename as a
blocker when it "belongs to exactly one removed path and to no surviving
file". Keeping the basename means the surviving vendored copy satisfies the
second clause, so a consumer line naming the script by basename alone — a
`Windows`-separator path, an `os.path.join("scripts", ...)` — stops being a
blocker, because it now names something that is in fact still there. A renamed
copy leaves that clause unsatisfied and the bare-basename references stay
blockers for no reason. Full-path references to `scripts/…` remain blockers
either way, correctly.

Bare-*suffix* matching is deliberately absent from the resweep (same
docstring, "What is deliberately absent is bare-suffix guessing"), so the two
copies sharing a tail creates no false blocker in the other direction.

`.sd-ai-command-pack/` is already the first entry in the resolver's own
`COPIED_PREFIXES`, so the vendored copy classifies as `pack-payload` under
`--path` with no change — the shim is consistent with the classifier it
carries rather than an exception to it.

The three install receipts live in the same directory and are **not** manifest
rows (`installer/conversion.py` `BOOKKEEPING_TARGETS` handles them separately),
so the override cannot collide with them. `installer/removal.py` and
`installer/inspection.py` contain no glob over that directory — verified by
grep, zero matches — so nothing treats a fourth file there as a stray.

Override placement matters: `TARGET_OVERRIDES` is first-match-wins and already
ends with `("scripts/**", MACHINE_CLAUDE, True)`. The new entry goes in the
consumer-config block above it, where the existing four sit.

## D3 — The one unavoidable code change: the shim cannot import the library

`scripts/sd-ai-command-pack-review-layout.py:42` reads:

```python
from sd_ai_command_pack_lib import CommandError, resolve_state_root
```

That is a bare sibling import, and it works today in both layouts *because both
copies travel together* — under thin, the resolver and the library are both in
`~/.agents/bin/`. A vendored copy at `.sd-ai-command-pack/bin/` has no sibling
library, and `sd_ai_command_pack_lib.py` is `machine-claude`, so under thin the
import raises and the shim fails exactly where it is needed.

`resolve_state_root` and `CommandError` therefore move into the resolver's own
bytes. This is the duplication D3a of the guard task already sanctioned —
"redefined in the shipped script with a comment naming the repo-side original,
and a pack test asserts the two agree" — applied to the one function that
cannot be imported. The test (AC4) exercises all five rungs of the ladder
against both copies, so drift fails a gate rather than a consumer.

Nothing else in the file needs to change. `argparse`, `json`, `os`, `sys`,
`pathlib`, `typing` are stdlib.

### D3c — This collides with A-046, and the collision is real

Found during implementation, not planning. `tests/test_state_root_boundary.py`
is a gate from task A-046, which consolidated four forked `resolve_state_root`
ladders into the shared library and then asserted, by AST over every
`scripts/*.py`, that exactly one definition exists. D3 re-forks it. The gate
fired, correctly.

The alternative that satisfies the gate outright is to ship the library to
`.sd-ai-command-pack/bin/` as well, so the resolver can import a sibling in
both layouts. Measured: `scripts/sd_ai_command_pack_lib.py` is 1230 lines and
42 top-level definitions of git, subprocess, hashing and private-cache
machinery, essentially none of which the resolver calls. That trades ~45 lines
of duplicated path arithmetic for ~1230 lines of vendored pack code in every
consumer, inside a conversion whose entire purpose is to stop vendoring pack
code. Rejected.

Renaming the carried function so the AST check does not see the name would
evade the gate rather than answer it, and would leave the fork unchecked.
Rejected.

So the gate takes a narrow exemption, written into the gate file with this
reasoning. What A-046 actually bought was *no drift*, not literally one
definition, and the exemption preserves that property by a stricter mechanism
than the AST check: `test_carried_state_root_ladder_matches_library` runs both
implementations over every rung and every refusal and requires equal answers.
Two further checks keep the exemption honest — the exempt file must still
carry a definition (an exemption for a file that stopped needing it is one
nobody is checking), it may carry only `resolve_state_root` and never
`ensure_private_directory` (which creates directories and enforces
permissions, and has no import-availability excuse), and the agreement test
must still exist under its name.

Deliberately **not** done: deleting the `scripts/` row. The pack's own tooling
invokes `scripts/sd-ai-command-pack-review-layout.py`, and the three inventory
gates wired for it last session (coverage floor 95, `post_rename_scripts`,
shipped-script docs) are all keyed to that path. Moving the row would break
three gates to save one manifest line.

## D4 — Call convention

Callers invoke the vendored copy directly:

```
python3 .sd-ai-command-pack/bin/sd-ai-command-pack-review-layout.py \
  --resolve <NAME>
```

No probe, no fallback chain, no fat-versus-thin branch — the path is present
under both layouts by construction, which is the entire point. `mode` remains
output, never input (the guard task's D4), so a caller reads what was resolved
rather than asking which layout it is in.

Python 3 is not a new dependency: the shipped shell and Node bindings already
spawn `python3`, and every measured consumer's CI runs it.

The bindings (`review-scope.sh --json`, the `.mjs` export) change their one
literal from the `scripts/` path to the vendored path. They are payload, so
they change once here and reach consumers through the ordinary refresh.

The row is `install: always`. `if-not-exists` is correct for `.gito/config.toml`
and `.prism/rules.json`, which a consumer edits; it would be a defect here,
where the file is code that must track the pack version.

## D5 — The resweep needs no change, and that is a design property

`installer/conversion.py` computes what conversion removes from partition
categories, and `KEEP_CATEGORIES = frozenset({"repo-native", "consumer-config"})`.
The resweep's blocker rule is "a consumer reference to a path conversion
removes." A `consumer-config` path is not removed, so a reference to it is not
a blocker — with no rule written anywhere about this task.

AC7 tests both directions on a fixture rather than a live consumer, because a
rule that only ever answers "not a blocker" would pass a one-directional test
while classifying everything as safe.

## D5a — `platform: "shared"` installs without being declared

No consumer declares `shared`: all eight `docs/fleet/consumers.json` entries
read `['claude', 'gemini', 'github', 'opencode']`. The row would install
nowhere if `shared` were gated on that array. It is not — `.gito/` and
`.prism/`, both `platform: "shared"` rows, are present in `hoa-manager`, which
declares neither. R2 is therefore satisfied by `shared` rather than in spite of
it, and no consumer registry edit is needed.

## D5b — `--path` degrades under thin, and this task makes that reachable

`classify()` tests `normalized in layout.targets` before falling back to
`COPIED_PREFIXES`, and `layout.targets` is the receipt. Conversion rewrites the
receipt to the residual slice, so in a converted consumer a
`scripts/sd-ai-command-pack-*.py` path matches neither test and classifies as
`authored` — the wrong answer for a path that is pack payload.

This is pre-existing behavior from the guard task, not introduced here, and it
is unreachable in ordinary use: in a converted consumer that path does not
exist, so no changed-file set contains it. This task makes it *reachable*,
because it puts a working resolver in exactly the consumers where the receipt
has been narrowed — a cohort reviewing a pre-conversion diff, or a
mid-conversion tree, can ask about a path the receipt no longer lists.

Not fixed here, and not silently inherited either: it is `C-4` in this task's
ledger, parked with a named trigger. The disposition is to document the bound
(`--path` answers about the *current* install, not about history) and to add a
test that pins the documented behavior, so a later change that alters it fails
a gate instead of surprising a cohort.

## D6 — What the fleet count actually becomes

Measured across the eight saved resweeps:

- 288 blockers name a `scripts/sd-ai-command-pack-*` path, spread over **68
  files** and naming **17 distinct** pack scripts.
- Rewriting those 68 files to call the vendored entrypoint retires all 288 and
  introduces **zero** new blockers, versus up to 68 under a bootstrap probe.
- 31 further blockers sit in the five bespoke guards, which the cohorts delete
  rather than port.
- **101 remain and this task does not reach them**: glob patterns in
  instructions prose and CI-classifier fixture lists. No runtime resolver
  rewrites a glob. They need per-consumer rewriting or explicit acceptance.

So the honest claim is: this task makes zero *achievable* and retires the
largest bucket by construction; it does not by itself put any consumer at zero.

## D7 — Rollout and rollback

Ordering the conversion cohorts depend on, and the reason each step precedes
the next:

1. Ship the row (this task). The entrypoint exists in the pack.
2. Fleet-refresh every consumer to that version. The entrypoint now exists **in
   the consumer**, committed, at a path conversion keeps.
3. Cohorts rewrite call sites to the vendored path. Safe only after step 2; a
   rewrite that lands first names a file that is not there yet.
4. Resweep. The 288 are gone; whatever remains is the glob residue.
5. Convert.

Rollback is one revert: drop the manifest row and the override entry, regenerate.
A consumer that already received the file keeps a stale copy until its next
refresh removes it — harmless, since nothing references it before step 3, and
after step 3 the rollback is blocked by the same ordering that made step 3 safe.

## D8 — Open questions, to be closed by execution rather than assertion

These are the places this design could be wrong. Each names the check.

- **O1 — two rows, one source, install audit.** 53 sources are already
  multi-target, but none of them is `kind: script`. Check:
  `sd-ai-command-pack-install-audit.py` on a fresh self-install, plus
  `installed-targets.txt` holding both paths.
- **O2 — `kind: script` outside `scripts/`.** `generate-plugin.py:172-177`
  maps kinds to allowed prefixes, but only walks the `machine-claude` slice, so
  a `consumer-config` row should never reach it. Check: `make generate` succeeds
  and `plugins/sd/bin/` gains no second copy.
- **O3 — machine payload.** `installer/machinepayload.py` consumes the
  `machine-other` slice plus `sharedRuntime` rows. A `consumer-config` row is
  in neither. Check: `partition-surfaces.py --check` plus the payload count
  before and after.
- **O4 — executable bit.** The file is invoked as `python3 <path>`, so no exec
  bit is required; confirm the installer does not chmod by `kind` in a way that
  makes the two copies differ. Check: compare modes of both installed copies.
- **O5 — file mode and the machine receipt.** The machine receipt records
  `executable` per entry. Confirm the consumer-config copy does not enter it at
  all.
