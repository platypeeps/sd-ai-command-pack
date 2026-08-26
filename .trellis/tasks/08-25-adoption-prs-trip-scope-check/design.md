# Design — adoption diffs do not require a hand-written scope section

Settles requirement 1 of `prd.md` as recorded there on 2026-08-26: exempt a diff
whose every changed path is pack-owned, reading ownership from the **base** copy
of `.sd-ai-command-pack/installed-targets.txt`.

## Where the change goes

`scripts/sd-ai-command-pack-review-scope.sh`, in the classification loop at
`:415-483`. Nothing else in the pack changes behaviourally; requirement 3 is a
wording change to two templates.

The loop today classifies each changed file into one of three scope categories,
accumulates `scoped_changes`, and then branches:

```
collect_changed_files → classify → scoped_changes[]
  ├─ empty            → return 0
  ├─ advisory mode    → warn + sd-ai-command-pack-scope-advisory: marker
  └─ enforcing mode   → check_pr_body_scope "${#scoped_changes[@]}"
```

`check_pr_body_scope` (`:301`) fails on any non-zero count. That count is the
defect: it cannot distinguish *only* pack files from authored work carried
alongside pack files. The fix adds one predicate and one early return, placed
**before both** the advisory and enforcing branches.

## The predicate

```
is_adoption_only_diff:
    changed = collect_changed_files()        # untracked included; see below
    if changed is empty:            not adoption      # nothing to exempt
    if base receipt unusable:       not adoption      # fail closed
    for path in changed:
        if not pack_owned_at_base(path): not adoption
    adoption
```

`pack_owned_at_base` is `is_pack_target_path` with `$TARGETS_FILE` bound to the
base copy rather than the working tree.

### Untracked files are counted, deliberately

`collect_changed_files` ends with `git ls-files --others --exclude-standard`
(`:112`), so untracked files count as changed.

An earlier revision of this design excluded them, reasoning that one stray
scratch note in the operator's tree should not cost the exemption. That is
wrong, and the existing suite proved it:
`test_review_scope_script_reports_manifest_driven_pack_changes` builds its
authored files with `write_text` and never stages them, so excluding untracked
paths made the predicate blind to them and granted the exemption to a diff that
plainly was not an adoption.

Generalised, excluding untracked files fails **open**: create an authored file,
leave it unstaged, and an otherwise-pack-only diff is exempt. Requirement 2 is
the entire safety case for this exemption, so the predicate uses
`collect_changed_files` unchanged. The cost — an operator with an untracked
scratch file does not get the exemption — is exactly today's behaviour, so it
fails **safe**. Consistency with classification is a secondary benefit: one
notion of "changed", not two.

### Interaction with `SD_AI_COMMAND_PACK_TARGETS_FILE`

`$TARGETS_FILE` is overridable (`:36`), and the override is load-bearing: nine
call sites across `tests/test_review_layout.py` and `tests/test_review_scope.py`
set it to point at a receipt elsewhere, at a missing file, or to unset it.
Unconditionally rebinding it to a git-materialized base copy would break that
contract and several existing tests.

So the base-copy substitution applies **only when the override is unset**. When
`SD_AI_COMMAND_PACK_TARGETS_FILE` is explicitly set, that file is the receipt
for both classification and exemption, and the caller owns the consequences —
which is what an explicit override means. The security argument is unaffected:
the hazard is a receipt an untrusted *diff* can rewrite, not one an operator
deliberately points elsewhere.

### Why ownership is read from the base

`TARGETS_FILE` resolves to `$REPO_ROOT/.sd-ai-command-pack/installed-targets.txt`
(`:36`) — the working-tree copy. Today that is safe in the strict direction:
appending a path to the receipt makes that path *count as scoped*, which
demands a section rather than skipping one. The exemption flips the sign. An
author could append `src/payments.py` to `installed-targets.txt` and the diff
carrying both would read as all-pack-owned.

The script already resolves a base ref for `collect_changed_files` via
`scope_base_ref` (`:85`), so the base copy is one command away:

```sh
git show "${base_ref}:.sd-ai-command-pack/installed-targets.txt"
```

That output is materialized once into a temp file and `$TARGETS_FILE` is pointed
at it for the ownership sweep only. The existing classification loop keeps using
the working-tree copy, so scope *categorisation* is unchanged and only the
*exemption* consults the base. Two different questions, two different sources,
each defensible: categorisation should describe the branch as it stands;
authorisation to skip a gate must not be writable by the diff being gated.

### Fail-closed cases

All three produce "not adoption", i.e. today's behaviour:

| Condition | Why it fails closed |
|---|---|
| `git show` of the base receipt non-zero | Receipt absent at base (new install) |
| Base receipt empty after comment-stripping | Indistinguishable from truncation |
| Any changed path absent from it | Requirement 2 — authored file present |

There is deliberately no "unresolvable base ref" row. `configured_review_base_ref`
warns and returns non-zero for a ref that does not resolve, and `scope_base_ref`
then falls back to the discovered default branch — so there is no state in which
no base ref exists to decide against. That is a better outcome than the
fail-closed rule an earlier revision assumed: the exemption is not silently
disabled in checkouts with an unusual base. The receipt read is the real guard.

The last row is requirement 2 in full. No separate mechanism is needed: an
authored file is by construction absent from a receipt `install.py` wrote.

### Accepted cost

When a pack version *adds* a new installed target, that path is absent from the
base receipt, so the adoption PR still asks for a section. This is a
false-negative in the strict direction, identical to today's behaviour, and it
occurs only on versions that change the target set. Accepted rather than
engineered around; engineering around it means trusting the head receipt, which
is the hazard above.

## Observability

Silence would make an exemption indistinguishable from a check that did not run.
The full scope report — categories and changed files — still prints; only the
body requirement is waived. An earlier revision returned before that report and
broke `test_scope_guard_accepts_a_relative_explicit_root`, which exists to prove
the receipt lookup survives a relative root and reads the categories back to do
it. Suppressing the report to implement an exemption destroyed the evidence that
the classifier ran at all. After the report, the script prints one line and
returns 0:

```
info: All changed files are pack-owned at <base_ref>; adoption diff, no scope section required.
```

The advisory marker `sd-ai-command-pack-scope-advisory:` is **not** emitted on
this path. `rwbp-website`'s lane is the one surface where a fleet operator sees
this defect today (`prd.md`, "What survives"); after the fix there is nothing to
warn about, and continuing to warn would re-create the noise the task exists to
remove.

## Rollout and rollback

Behaviour-only change to one shipped script, so it needs a manifest version bump
and the four-copy mirror sync (`make sync` → `make generate` →
`sd-ai-command-pack-fleet-candidate-check.py` → `make check`).

Rollback is reverting the commit: the predicate is additive and nothing else
reads it, so removing it restores the prior gate exactly. No receipt format
changes, no state is written, and consumers need no re-adoption beyond the
normal version bump.

## Requirement 3

`templates/.github/PULL_REQUEST_TEMPLATE.md:6` and
`templates/.github/copilot-instructions.sd-ai-command-pack.md:61` state the
section is required. After this change that is true for mixed diffs and false
for adoption diffs. Both get a clause naming the exemption, so a consumer
reading them can predict the gate's behaviour rather than discovering it.

## Rejected alternatives

- **Widen `is_pack_target_path`.** Wrong direction: that predicate marks files
  as in-scope, so widening it demands *more* sections, not fewer.
- **Exempt a hard-coded path list.** Duplicates coverage the receipt lookup
  already provides and drifts from it.
- **Compare `${#scoped_changes[@]}` against a total-changed count.**
  Nearly right, and wrong on a real case: `scoped_changes` also collects
  repository-map and Trellis-journal files. A diff of exactly
  `docs/repomix-map.md` would count as all-scoped and be exempted, though it is
  not pack-owned and not an adoption diff. Ownership must be tested directly.
