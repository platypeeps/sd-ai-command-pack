# Design — `AGENTS.md` canonical-entry-point routing managed block

Issue #486. Complex task: the contract crosses the manifest, the installer's
managed-block path, removal, thin conversion, the surface partition, and the
install audit. Everything below was measured in this checkout at `b17764ed`
(pack 0.71.54) on 2026-08-25; line numbers are from that head.

---

## 1. The open question, settled: documentation-only

**Decision: the routing block ships as documentation. The pack does not ship a
checker that derives the routing list from a consumer's `.agents/skills/`.**

This is not "no verification". The block gets exactly the verification every
managed block already has — install-time drift detection — and R6's required
written statement says which surface that covers and which it does not.

### 1.1 A managed block already carries a verification story

Measured, not inferred. A consumer fixture with `github` active, pack 0.71.54
installed clean:

```
state: current
planned changes: 0
result counts: unchanged=88
```

One line inserted *inside* `SD-AI-COMMAND-PACK:COPILOT-GUIDANCE:START/END`,
then the same command:

```
state: refresh-required
planned changes: 1
result counts: unchanged=108, updated=1
```

`install.py <target> --check` plans the payload in dry-run through the same
`_install_payload` the apply uses (`install.py:1405-1414`), so
`install_managed_block(dry_run=True)` returns `UPDATED` whenever the bytes
between the markers differ from the shipped template
(`installer/fileops.py:790-800`). `UPDATED` is in `_CHANGE_INSTALL_STATUSES`
(`installer/inspection.py:32-41`), so it moves the reported state. Consumers
already run this; it needs no new script, and it is the check that actually
matters — "did my routing block drift from the one the pack ships".

> Note for whoever re-runs this: a fixture without the platform's activation
> markers reports `planned changes: 0` even with the block tampered, because
> `selected_files` skips the row with `active Trellis github install not
> detected` (`installer/fileops.py:243-250`). That is the fixture, not the
> pack. `.github/skills/trellis-before-dev/SKILL.md` is one of `github`'s
> three markers.

### 1.2 A derivation checker cannot be shipped correctly

The filing repository's test derives the wrapped-workflow set from
`.agents/skills/` and fails when the section drifts. That works *there* because
that repository's `.agents/skills/` and its `AGENTS.md` are both repo-owned and
always in step.

Here there is nothing to derive from. §1.4 makes the block route by *intent*
and carry no skill inventory, so a checker comparing "the routing list" against
`.agents/skills/` has no list to read. That is the whole answer, and it is a
content decision this design controls rather than a claim about tooling.

> **Do not substitute the build gate for this.** `make generate`'s
> shipped-surface closure does **not** cover managed blocks: `surface-check`
> skips them outright —
> `if entry["kind"] == "managed-block" or not target_path.exists(): continue`
> (`scripts/sd-ai-command-pack-surface-check.py:772-773`). An earlier draft of
> this section argued the build gate already caught any inconsistency, which is
> false. If the block ever did enumerate skills, nothing in this repository
> would check it — which is a second reason not to let it enumerate them.

> **Corrected 2026-08-25.** An earlier draft argued that `--platform` filtering
> makes a consumer's `.agents/skills/` set vary, so the check would fire on
> correct configuration. That is **false**: 82 of the 84 `shared` rows declare
> `install: "always"`, and `selected_files` selects `always` rows *before* the
> platform filter (`installer/fileops.py:227-236`), so `--platform claude`
> still installs `.agents/skills/`. The argument above does not depend on it.

Thin conversion does move the set — `.agents/**` is a machine surface for
partition purposes and `PLATFORM_RETAIN_VENDORED_FOR`
(`.github/scripts/partition-surfaces.py:198-200`) exists for exactly that — so a
consumer-side checker would additionally need machine-scope awareness to avoid
failing every converted consumer. That is a second cost on top of a check that
was already redundant.

### 1.3 The pack's receipt layer already declines to vouch this content

`never_vouched_targets()` derives its exclusion set from the manifest kind:

```python
*(file.target.as_posix() for file in files if file.kind == MANAGED_BLOCK_KIND)
```

— `installer/provenance.py:135-141`, under the docstring "managed blocks are
shared ownership". Every managed-block target is dropped from provenance by
construction, and `sd-ai-command-pack-install-audit.py:128` skips the same
targets in the audit. Shipping a pack-owned content checker for a managed block
would re-assert an authority the pack's own receipt layer gives up on purpose.

### 1.4 What this makes the block's content have to be

Documentation-only is safe **only if the text cannot go stale**. So the block
routes by *intent* — "for X, use the canonical entry point" — and enumerates no
installed-skill inventory at all. Two concrete rules:

- **No skill list, no command list, no count.** Anything that names a specific
  installed surface can be made false by a later release or a thin conversion,
  and §1.2 establishes that nothing would catch it.
- **No `scripts/` or pack-doc reference**, per §3.1: those are rewritten for a
  thin consumer and would read differently there.

This is a content constraint on `templates/AGENTS.sd-ai-command-pack.md`, and
§8 test 7 is where it is checked.

### 1.5 R6 satisfied

The block itself, and the tooling spec section, carry this sentence:

> The pack verifies that this block matches the version it shipped — `install.py
> <repo> --check` reports `refresh-required` if the text between the markers
> drifts. It does **not** verify the routing against this repository's installed
> skills, and deliberately names none: the block routes by intent so that there
> is nothing in it that a later release or a thin conversion could make false.

---

## 2. Absent `AGENTS.md`: skip, do not create

**Decision: when `AGENTS.md` does not exist, the row is skipped at selection
time — the pack writes nothing, and the target is not recorded as installed.**
§2.1 is where that must happen and why the obvious placement is wrong.

The existing precedent creates (`installer/fileops.py:802-805`), so this
departs from it deliberately:

- `.github/copilot-instructions.md` has one writer. `AGENTS.md` has two: the
  pack, and `trellis update`, which owns `TRELLIS:START`/`TRELLIS:END`
  (`AGENTS.md:1-21` in this checkout).
- R1 requires the routing block **below** the Trellis block. If the pack
  creates the file, there is no Trellis block to be below, and the invariant is
  vacuous at creation and then decided later by `trellis update`'s own
  insertion point — which the pack does not control. Creating the file is the
  one way to make R1 unverifiable.
- It is the same reasoning the PRD already used to reject shadowing the
  `trellis:*` command surface: compose with the other installer, do not fight
  it.

### 2.1 Where the skip is enforced — in selection, not in the writer

The obvious lever is the manifest `anchor`: `install: "if-anchor-exists"` with
`anchor: "AGENTS.md"`, since `(target / file.anchor).exists()` accepts a file.
**That lever does not exist for this row.** §4 pins the row to `install:
"always"` — it has to, or a marker-less `shared` row is never selected in a
normal install — and the `ALWAYS_INSTALL` branch short-circuits at
`installer/fileops.py:227-229`, before the anchor is ever consulted. The anchor
would be an inert field, so §4's row omits it.

Even if the row could use the anchor, the gate is bypassed under an explicit
platform filter or `--all`:

```python
if install_all or platform_filter:
    selected.append(file)
    continue
if file.anchor and not (target / file.anchor).exists():
```

— `installer/fileops.py:237-242`. So the anchor is the wrong mechanism twice
over.

**The skip must therefore happen in `selected_files`, at the top of the loop —
not in `install_managed_block`.** Returning `PRESERVED` from the writer is
not enough, and the reason is a hard failure, not a cosmetic one:

`installed_targets_content(selected, ...)` builds
`.sd-ai-command-pack/installed-targets.txt` from the **selected** rows
(`installer/provenance.py:71-77`), not from the results. A row that was
selected and then preserved is still written into the receipt. The audit then
reaches `audit_structural_state`, finds the listed target absent, and — because
`AGENTS.md` is a tracked repository document and not gitignored — takes the
failure branch, not the warning branch:

```python
failures.append(f"installed target is missing: {target}")
```

— `sd-ai-command-pack-install-audit.py:693`. `install.py <target> --check` runs
that audit and reports `audit: failed`. So a writer-side skip turns a clean
consumer with no `AGENTS.md` into a failing one, which is R5 inverted.

Concretely, at the **top of `selected_files`'s per-file loop**
(`installer/fileops.py:226`), before every install-mode branch. For an
`always` row this is the *only* reachable placement — every branch below line
229 is dead for it:

```python
spec = MANAGED_BLOCK_SPECS.get(file.target.as_posix())
if spec is not None and not spec.create_if_absent:
    if not path_is_occupied(target / file.target):
        skipped.append((file, f"{file.target} not present; block not created"))
        continue
```

**`path_is_occupied`, not `.exists()`.** `Path.exists()` follows symlinks, so it
is `False` for a *dangling* `AGENTS.md` symlink, and a `.exists()` gate would
silently skip that instead of reporting it. The pack's contract is the
opposite: a final-path symlink is reported and left untouched, never followed
and never replaced. `path_is_occupied(path) = path.exists() or
path.is_symlink()` (`installer/fileops.py:256-257`) is the primitive the
removal path already uses for exactly this reason. With it, a dangling symlink
falls through to the writer and gets the symlink conflict the rest of the
installer would give it.

The `PRESERVED` branch in `install_managed_block` stays as defence in depth —
an explicit refusal beats a silent create if a future caller reaches the writer
another way — but it is no longer the contract's enforcement point.


---

## 3. Structure: one shared per-target table, not a second hardcoded target

Today three surfaces each hardcode the one target:

| surface | shape today |
| --- | --- |
| `installer/fileops.py:780-781` | `if file.target != COPILOT_INSTRUCTIONS_TARGET: raise SystemExit` |
| `installer/fileops.py:647-654` | `merge_managed_block` closes over `COPILOT_GUIDANCE_START/_END` |
| `installer/thin.py:817-832` | `BLOCK_MARKERS` — already a per-target table, already holding two entries |

`thin.py`'s table is the existing right shape and it already covers a second
target (`.gitignore`). The design promotes that shape into
`installer/registry.py` as the single source, and has `fileops`, `thin`, and
`removal` read it:

```python
AGENTS_ROUTING_TARGET = Path("AGENTS.md")
AGENTS_ROUTING_START = "<!-- SD-AI-COMMAND-PACK:ROUTING:START -->"
AGENTS_ROUTING_END = "<!-- SD-AI-COMMAND-PACK:ROUTING:END -->"

# target -> spec(start, end, label, preserve_invalid_utf8, adopt_on_thin,
#                create_if_absent, strip_on_thin)
MANAGED_BLOCK_SPECS = {...}
```

`strip_on_thin` is the field the two thin-side consumers need and the reason
they can stop hardcoding targets. It is `True` for `.gitignore` and
`.github/copilot-instructions.md` and `False` for `AGENTS.md`, matching §4's
`repo-native` classification. Both `installer/thin.py`'s `BLOCK_MARKERS` and
`sd-ai-command-pack-thin-resweep.py`'s `STRIPPED_BLOCK_LABEL` become derived
views filtered on it, so §5's "unreachable entry" property holds by
construction rather than by an implementer remembering to omit one.

`strip_on_thin` and the partition category must agree — a `repo-native` target
must not be strip-eligible. §8 test 8 asserts that, so the two cannot drift.

`merge_managed_block(current, block, *, start, end, label)` takes its markers
as arguments instead of closing over the Copilot pair. Everything else about
the merge is untouched — R3 says do not invent a second merge semantics, and
the existing function already implements the exact contract R3 wants: replace
between markers when present, append with normalized blank-line separation when
not (`installer/fileops.py:647-666`).

Appending is what puts the routing block **below** the Trellis block, with no
ordering logic of its own: the Trellis block occupies the head of the file
(`AGENTS.md:1-21` here) and the pack appends at EOF. Note *at EOF*, not
immediately after `TRELLIS:END` — this checkout's own `AGENTS.md` carries
`## Maintainer Rules` and `## Contributor Entry Points` after the Trellis
block, and the routing block lands below those too. That satisfies R1, which
asks for below-Trellis and not adjacent-to-Trellis; the test in §8 asserts
ordering relative to `TRELLIS:END`, not adjacency.

R1's "never inside it" holds for every state the pack can reach on its own — a
fresh append lands at EOF, and a later install replaces the routing block where
it already is. It is **not** an enforced invariant, and this design
deliberately does not add one. Neither `selected_files` nor
`merge_managed_block` inspects `TRELLIS:START`/`TRELLIS:END`
(`installer/fileops.py:647-666`), so two states the *consumer* can create
survive install unchanged:

- a routing block hand-placed **inside** the Trellis block stays inside,
  because the merge replaces it at its existing position;
- an **unterminated** Trellis block (`TRELLIS:START` with no `TRELLIS:END`)
  swallows the appended routing block.

Both are recorded rather than guarded. A guard would mean the pack parsing and
enforcing another installer's marker semantics — the coupling the PRD's
rejected alternative already refused — and `trellis update` rewrites its own
block regardless. §8 test 14 asserts the unterminated case behaves as written
here rather than as something unexamined.

**R1 was amended to match.** As originally written ("never inside it",
unqualified) R1 and this section contradicted each other outright, and test 14
asserted the violation. The PRD now scopes R1 to a *well-formed* Trellis block;
see its Amendments section.

### 3.1 UTF-8 and adoption disposition

`preserve_invalid_utf8: True`, matching `.github/copilot-instructions.md`:
`AGENTS.md` is equally consumer-owned prose and a removal must not transcode a
consumer's bytes. `adopt_on_thin: False` — adoption is `.gitignore`-only,
because only its rules outlive the payload (`installer/thin.py:812-816`).

`normalize_managed_block_template` runs the template through
`rewrite_text(..., profile=THIN_PROFILE, key=<target>)` for a thin consumer
(`installer/fileops.py:631-639`), and that rewrite is generic: it repoints
`scripts/<name>` and pack-doc references at their machine locations
(`installer/references.py:635-657`). This is correct behaviour, but it is a
**constraint on the template**: any `scripts/` or pack-doc reference the
routing block carries will read differently in a converted consumer. Design
§1.4's "route by intent" already keeps such references out; §8's test 7
fixture is the place to notice if one creeps in.


### 3.2 Inherited behaviour: removal can delete the file

`remove_text_block_file` deletes the target outright when stripping the block
leaves nothing behind:

```python
status = RemoveStatus.REMOVED if not stripped.strip() else RemoveStatus.UPDATED
...
if status is RemoveStatus.REMOVED:
    unlink_target_file(target, destination)
```

— `installer/fileops.py:1030-1048`. So an `AGENTS.md` whose *entire* content is
the pack's routing block is deleted by `--remove`, not emptied.

This is inherited from the existing managed-block path, not introduced here,
and §2's skip-when-absent means the pack never produces such a file itself: a
routing-block-only `AGENTS.md` can only exist if a consumer hand-made one.
It is recorded and tested (§8 test 13) rather than guarded, because the
alternative — leaving a zero-byte `AGENTS.md` behind — is worse, and diverging
from the shared removal path for one target reintroduces the per-target
special-casing this design is removing.

---

## 4. Manifest row and partition category

```json
{
  "platform": "shared",
  "kind": "managed-block",
  "source": "templates/AGENTS.sd-ai-command-pack.md",
  "target": "AGENTS.md",
  "install": "always"
}
```

**`install: "always"`, and no `anchor`.** This is not cosmetic; the obvious
alternative is dead on arrival. Omitting `install` defaults it to
`if-anchor-exists` (`installer/manifest.py:91`), and an `if-anchor-exists` row
must clear `has_active_trellis_platform(target, file.platform)`
(`installer/fileops.py:243`), which is

```python
markers = ACTIVE_TRELLIS_PLATFORM_MARKERS.get(platform, ())
return any((target / marker).is_file() for marker in markers)
```

— `installer/fileops.py:208-210`. `shared`'s `PlatformInfo` declares **no
markers** (`installer/registry.py:403-406`), so it is absent from
`ACTIVE_TRELLIS_PLATFORM_MARKERS` (`installer/registry.py:2227-2231`), the
`any(())` is `False`, and a normal install — no `--platform`, no `--all` —
skips the row *even when `AGENTS.md` exists*. Only an explicit `--platform
shared` would install it, which is not the contract R1 asks for.

`install: "always"` is also what the other 82 `shared` rows use, so this is the
platform's established mode rather than a special case. The consequence is that
the anchor gate is unreachable for this row (the `ALWAYS_INSTALL` branch
short-circuits at `installer/fileops.py:227-229`), which is precisely why the
absent-target skip in §2.1 lives at the top of the loop and not in the anchor.

`platform: "shared"` because `AGENTS.md` is the cross-platform entry-point
document; it is the platform whose directory is `.agents`
(`installer/registry.py:403-406`), which is what the routing describes.

**That platform choice needs an override, and this is the trap.** `shared` is a
*machine* platform for partition purposes — it is absent from
`PLATFORM_DISPOSITIONS`' repo-native list and appears instead in
`PLATFORM_RETAIN_VENDORED_FOR`. A `shared`-platform row therefore classifies as
`machine-other`, and `conversion.py:171-185` routes a managed-block target with
a non-`KEEP` partition category to `blocked`. So the row needs a target-path
override:

```python
# AGENTS.md is the repository's own entry-point document; the pack owns one
# block inside it and Trellis owns another. It is repo-native regardless of
# the `shared` platform's machine disposition.
("AGENTS.md", REPO_NATIVE, False),
```

in `TARGET_OVERRIDES` (`.github/scripts/partition-surfaces.py:111`). The
override table is checked first (`override_category`, line 282-287) and an
override matching zero rows is a hard error, so it cannot be added speculatively
ahead of the manifest row, nor left behind if the row is dropped.

This is also the correct thin-conversion answer, and it mirrors
`.github/copilot-instructions.md` (`repo-native`, `surface-partition.json:2255`)
for the same reason the code gives: the surface is read from the repository and
cannot see the machine install.

---

## 5. Correction to acceptance criterion 8

> "Thin conversion handles the new target — the `installer/thin.py` per-target
> table has an entry, exercised by a test, not merely present."

`BLOCK_MARKERS` is reached from exactly two places, both keyed on
`plan.block_strip`: `thin.py:871` (preflight) and `thin.py:1013` (apply). A
`repo-native` target classifies `keep` (`conversion.py:180-181`) and never
enters `block_strip`. **An entry for `AGENTS.md` in that table would be
unreachable, and no test could exercise it without first misclassifying the
target.**

The criterion's intent — thin conversion handles the new target, proven by a
test — is met by asserting the classification instead: a test that runs the
conversion planner over a consumer carrying the routing block and asserts
`AGENTS.md` lands in `keep`, not `block_strip` and not `blocked`. That is a
stronger assertion than a table entry, because it is the one that fails if the
partition override is forgotten.

Recorded here rather than silently substituted; `implement.md` carries the
criterion in its corrected form and the PRD gets an amendment note.

---

## 6. R2 sweep — every site, with its disposition

The PRD says to derive this by sweeping for the existing marker constant.
Done — and the sweep **misses one site**, recorded below.

| site | disposition |
| --- | --- |
| `registry.py:2326-2331` | add `AGENTS_ROUTING_*` constants + `MANAGED_BLOCK_SPECS`; export in `__all__` |
| `registry.py:2356` `__all__` | add the new names |
| `manifest.py:12,37` | no change — `MANAGED_BLOCK_KIND` is already a known kind |
| `fileops.py:647-666` `merge_managed_block` | parameterize markers |
| `fileops.py:773-805` `install_managed_block` | table lookup replaces the target assert; absent+`skip` → `PRESERVED` as defence in depth |
| `fileops.py:226-250` `selected_files` | **skip a `create_if_absent: False` row whose target is absent, at the top of the per-file loop** — §2.1; this is the enforcement point |
| `fileops.py:624-644` `normalize_managed_block_template` | marker validation reads the target's pair, not the Copilot pair |
| `removal.py:32-33` imports | add the routing constants |
| `removal.py:55-60` `MANAGED_BLOCK_REMOVAL_TARGETS` | add `AGENTS.md` — this is what R4 needs, and what routes conversion to the partition check |
| `removal.py:345-356` | second `remove_text_block_file` call, or a loop over the table |
| `removal.py:109,154` | derive from the set; no edit needed once the set has the entry |
| `conversion.py:171-185` | no code change — behaviour follows from the partition override (§4) |
| `conversion.py:385` | no change — derives from `MANAGED_BLOCK_REMOVAL_TARGETS` |
| `thin.py:817-832` `BLOCK_MARKERS` | **no entry** — see §5; if the table is unified into `registry.py`, `thin.py` filters it to strip-eligible targets |
| `provenance.py:135-141` | no change — derives from `file.kind`; the new row is never-vouched automatically |
| `install.py:645` dispatch | no change |
| `partition-surfaces.py:111` `TARGET_OVERRIDES` | add the `AGENTS.md` → `repo-native` row (§4) |
| `sd-ai-command-pack-thin-resweep.py:83-86` `STRIPPED_BLOCK_LABEL` | **no entry** — same reason as `BLOCK_MARKERS` (§5): it maps strip-eligible targets and `AGENTS.md` is kept. Recorded because its own comment claims the mapping "is derived from the same constants removal uses, so the two cannot drift apart" — the shared table in §3 is what should make that true instead of asserted |
| `sd-ai-command-pack-review-learnings.py:153-157` `GENERATED_SIGNAL_PATHS` | **add `AGENTS.md`** — the set drives comment classification (`:1117`) and planning-signal classification (`:1288`); without it, review feedback on the new pack-managed surface falls through to `SIGNAL_OTHER` |
| `README.md:41,647,667` and `templates/docs/SD_AI_COMMAND_PACK.md:563,2351` | **shipped user-facing inventories** naming only the Copilot block. Each recites what the pack installs, merges, or strips; leaving them ships false install/removal documentation |
| `sd-ai-command-pack-review-preflight.mjs:4997` `isSdCommandPackCopiedPath` | **exempt `AGENTS.md`, ahead of the receipt lookup** — reversed from an earlier draft of this table; see §6.1b |
| **`sd-ai-command-pack-install-audit.py:128`** | **add `"AGENTS.md"` to `PROVENANCE_NEVER_VOUCHED_TARGETS`** |
| **`sd-ai-command-pack-install-audit.py:425-441`** `expected_targets_from_manifest` | **add `OPTIONAL_INSTALL_TARGETS` and make `AGENTS.md` expected only when the receipt lists it** — §6.3 |

### 6.1 The site a marker sweep does not find

`PROVENANCE_NEVER_VOUCHED_TARGETS` is a **hardcoded set of target-path
strings** (`templates/scripts/sd-ai-command-pack-install-audit.py:128-137`),
listing `.github/copilot-instructions.md` literally. It contains no marker
constant and no reference to `MANAGED_BLOCK_KIND`, so sweeping for
`COPILOT_GUIDANCE_START` or the kind constant does not reach it — only sweeping
for the *target path string* does. Miss it and the audit tries to vouch a
consumer-owned file, turning legitimate local text into a drift failure — the
exact failure the docstring at `provenance.py:127-133` warns about.

**Because it is a shipped script under `templates/`, this edit is canonical and
must be mirrored by `install.py . --force` + `make generate`, not hand-edited in
`scripts/`.**

### 6.1a The second site a marker sweep does not find — found by measurement

`expected_targets_from_manifest` builds the completeness set from the manifest
and treats **every `shared` row as unconditionally expected**
(`templates/scripts/sd-ai-command-pack-install-audit.py:425-431`). §2.1 keeps a
skipped row out of the receipt; this check then fails the consumer *for the
skip*, from the opposite direction. Measured on a fixture with no `AGENTS.md`,
after §2.1 was implemented and before this was:

```
state: invalid
audit: failed
  error: expected installed target is missing from receipt: AGENTS.md
  error: expected installed target is missing: AGENTS.md
```

This is the same failure R5 forbids, so §2.1 alone does not deliver R5.

The script already carries the correct shape one branch below: `.gitignore` is
expected **only when the receipt lists it** (`:439-440`). The fix mirrors it —
an `OPTIONAL_INSTALL_TARGETS` set excluded from the unconditional comprehension
and unioned back in from `targets`. Present in the receipt still means the file
must still be there, so deleting an installed `AGENTS.md` remains a failure;
absent from the receipt means the row was legitimately skipped.

Spelled as a literal target-path set for the same reason as
`PROVENANCE_NEVER_VOUCHED_TARGETS`: the script ships standalone and cannot
import the registry. Both sets are therefore invisible to a marker sweep and
to a `MANAGED_BLOCK_KIND` sweep — only a *target-path* sweep reaches them, and
even that would not have reached this one, because the failure is about a row
the audit expects rather than a target it names. **What found it was running
`install.py --check` against a real fixture with no `AGENTS.md`** — §8 test 2's
`audit: passed` assertion is what keeps it found.

### 6.1b Review classification: reversed by fleet evidence

An earlier draft of §6 said to **add** `AGENTS.md` beside the
`.github/copilot-instructions.md` literal in `isSdCommandPackCopiedPath`,
reasoning that a new managed-block target needs the same missing-receipt
fallback. That was wrong in two ways, and the fleet candidate check found it:

```
failed      P20 platypeeps/loadsmith
error: review preflight fixture mismatch for AGENTS.md: copied=true, expected false
```

1. **The literal was not what fired.** `AGENTS.md` is an installed target, so
   `packInstalledTargets().has(path)` classifies it as copied on the first
   line of the function, receipt or no literal. Removing the literal alone
   changes nothing; the classification had to be *reversed*, not left alone.
2. **The classification is wrong for this file.** `copied` means "do not
   line-comment this file's wording." `AGENTS.md` is mostly the consumer's own
   agent instructions plus another installer's block; the pack owns thirty
   lines of it. Telling a reviewer to skip a repository's own agent
   instructions is a much larger loss than a missed comment on pack prose.

`loadsmith` had already reached that conclusion for the exactly-parallel file
and recorded it in `scripts/check_review_readiness.sh:251-255`:

> The command pack manages a block inside this repo-owned adapter, but review
> still treats the whole file as local integration, so it is not copied scope.

So the pack now carries the same exemption for `AGENTS.md`, placed **before**
the receipt lookup. `.github/copilot-instructions.md` keeps its existing
classification: changing it would move every consumer's review scope, and this
task does not own that decision.

### 6.2 Local-only mode

`AGENTS.md` is already named twice in the registry — `LOCAL_ONLY_TRELLIS_EXCLUDES`
(`registry.py:2247`) and `LOCAL_ONLY_TRACKED_CHECK_PATHS` (`registry.py:2257`) —
both predating this task. Under `--local-only`, `local_only_exclude_patterns`
unions the static excludes with `local_only_pack_excludes(selected)`
(`localonly.py:216-224`), so a new `AGENTS.md` pack row adds a duplicate the
`dict.fromkeys` de-dupes. No behavioural change and no edit; verified by test,
not by assertion (§8).

---

## 7. Rollout / rollback

- Additive: one manifest row, one template, one override row, one audit-set
  entry, parameterized markers. Nothing existing changes shape.
- Rollback is deleting the manifest row plus the override row (the override
  would otherwise match zero rows and hard-error, which is the desired coupling).
  A consumer that already installed the block clears it with `install.py
  <repo> --remove`, or by hand — the markers are self-describing.
- Fleet rollout via normal `sd-fleet-refresh`; no wave-specific handling.
- Version + changelog per the pack's usual bump. **Coordinate the version with
  any concurrent session** — a peer session is holding 0.71.55.

---

## 8. Tests required

In `tests/test_install_core.py` unless noted. Every one names its assertion
point; a test that only asserts "no exception" proves nothing here.

1. `AGENTS.md` with only a Trellis block → both blocks present, routing after
   `TRELLIS:END`, and the Trellis block **byte-identical** (assert the slice,
   not just presence).
2. No `AGENTS.md` → file still absent; the row is **skipped, not preserved**;
   `AGENTS.md` absent from `.sd-ai-command-pack/installed-targets.txt`;
   `--check` reports `state: current` **and** `audit: passed`. The receipt
   assertion is the load-bearing one — see §2.1. (R5.)
3. Same, **under an explicit `--platform` filter** (any platform — an `always`
   row is selected regardless of the filter, `installer/fileops.py:227-229`).
   This covers the `install_all`/`platform_filter` short-circuit path, which
   the anchor gate never reaches. Assert the installed-targets receipt, not
   only the absent file.
   Also run the mirror case with `--all`, for the same short-circuit.
4. Re-install idempotent: sha256 of `AGENTS.md` equal across two installs.
5. Consumer prose above, between, and below the two blocks survives; text
   inside the routing markers is replaced.
6. Removal deletes the routing block and leaves the Trellis block and consumer
   text intact (`tests/test_remove.py`).
7. Two separate assertions, both needed:
   a. Conversion planner classifies `AGENTS.md` as `keep`
      (`tests/test_conversion_plan.py`) — §5's substitute for the criterion-8
      table entry, and what fails if §4's override is forgotten.
   b. **Template content constraint** (§1.4, §3.1): assert
      `normalize_managed_block_template` output for the routing row is
      byte-identical with `is_thin=True` and `is_thin=False`. That is the
      executable form of "no `scripts/` or pack-doc reference" — those are
      exactly what `rewrite_text` changes (`installer/references.py:635-657`),
      so equality proves the template carries none.
8. `tests/test_partition_surfaces.py` — the override row matches exactly the
   one manifest row, **and** every `MANAGED_BLOCK_SPECS` entry's
   `strip_on_thin` agrees with its partition category: strip-eligible iff not
   `repo-native`. This is what keeps §3's derived views and §4's override from
   drifting apart.
9. `tests/test_install_audit.py` — a **stale or hand-authored** provenance
   entry for `AGENTS.md` does not produce a drift failure. Model it on
   `test_install_audit_ignores_stale_never_vouched_entries`
   (`tests/test_install_audit.py:1076-1098`): install, then write a bogus
   `files["AGENTS.md"]` hash into `.sd-ai-command-pack/provenance.json`, then
   run the audit and assert exit 0.

   > A test that merely edits `AGENTS.md` outside the markers **cannot** fail
   > without the audit-set entry, and an earlier draft of this section asked
   > for exactly that. `never_vouched_targets()` already drops every
   > managed-block row by kind (`installer/provenance.py:135-141`), so an
   > ordinary install writes no `AGENTS.md` provenance entry and the audit's
   > `PROVENANCE_NEVER_VOUCHED_TARGETS` skip
   > (`sd-ai-command-pack-install-audit.py:759-760`) is never reached. The
   > entry exists for provenance that predates or bypasses that rule, so the
   > test has to produce that state deliberately.
10. `tests/test_generated_parity.py` / `make generate` — surface closure clean
    with the new row, all mirrors byte-identical.
11. Local-only install lists `AGENTS.md` exactly once in the exclude patterns
    (§6.2). The fixture **must have an `AGENTS.md`**, so the manifest row is
    actually selected and contributes the duplicate that `dict.fromkeys` has to
    collapse. Without that, the test passes on the static
    `LOCAL_ONLY_TRELLIS_EXCLUDES` entry (`installer/registry.py:2247`) alone and
    proves nothing about the new row.
12. **`--remove` against a repo that never installed the pack** leaves an
    existing `AGENTS.md` byte-identical (`tests/test_remove.py`). This is
    criterion 7, and no other test covers it: `remove_text_block_file` returns
    `UNCHANGED` without writing when the markers are absent
    (`installer/fileops.py:1023-1027`), and the test is what keeps that true.
13. **Degenerate removal** — an `AGENTS.md` whose entire content is the routing
    block. See §3.2; assert the documented outcome rather than discovering it.
14. **Unterminated Trellis block** — `TRELLIS:START` with no `TRELLIS:END`.
    Assert the §3 outcome as written (the routing block appends at EOF, inside
    the unterminated block), so the un-guarded case is a recorded decision
    rather than an untested one.
15. **Dangling `AGENTS.md` symlink** — the install reports a symlink conflict
    and does not follow or replace the link, matching the existing
    managed-block symlink behaviour at `tests/test_install_core.py:694-702`.
    Must fail against a `.exists()`-based gate (§2.1).

---

## 9. Wrong vs correct

##### Wrong

```python
if file.target not in (COPILOT_INSTRUCTIONS_TARGET, AGENTS_ROUTING_TARGET):
    raise SystemExit(...)
merged = merge_managed_block(current, block)   # still the Copilot markers
```

Two targets, one marker pair: installing the routing block into `AGENTS.md`
would search for `COPILOT-GUIDANCE:START`, not find it, and append — then the
*next* install appends again, because it still cannot find its own markers.
Idempotence fails on the second run, which is exactly what criterion 4 hashes
for.

##### Correct

```python
spec = MANAGED_BLOCK_SPECS.get(file.target.as_posix())
if spec is None:
    raise SystemExit(f"error: unsupported managed block target: {file.target}")
merged = merge_managed_block(
    current, block, start=spec.start, end=spec.end, label=spec.label
)
```

##### Wrong

```python
# manifest row added; partition override skipped
```

`shared` is a machine platform, so the row classifies `machine-other`, and
`conversion.py:182-185` returns `blocked` with "managed-block file has an
unexpected partition category". Every thin conversion in the fleet refuses.
Test 7a is what catches this.

##### Wrong

```python
if not destination.exists():
    ...  # create, matching the Copilot precedent
```

Creates an `AGENTS.md` containing only the pack's block, in a repository that
never had one. R1's "below the Trellis block" then has no referent, and
`trellis update` later merges into a file the pack invented. It is also the
wrong *place* — see §2.1: by the time the writer runs, the row is already in
the installed-targets receipt, so a writer-side skip fails the audit instead.

##### Wrong

```json
{"platform": "shared", "kind": "managed-block", "target": "AGENTS.md",
 "anchor": "AGENTS.md"}
```

No `install` key, so it defaults to `if-anchor-exists` — and `shared` declares
no activation markers, so `has_active_trellis_platform` returns `any(())` and
the row is **never selected in a normal install**. Every unit test that passes
`--platform shared` still passes; only a fixture install with no `--platform`
flag fails. §4 pins `install: "always"` and drops the inert anchor.

##### Wrong

```python
if not (target / file.target).exists():   # skips a dangling symlink
```

`.exists()` follows symlinks. A dangling `AGENTS.md` symlink is silently
skipped instead of reported as a symlink conflict. Use `path_is_occupied`
(§2.1).
