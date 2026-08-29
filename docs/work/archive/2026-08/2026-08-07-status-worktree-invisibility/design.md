# Design: sd-status worktree inventory

## Decision summary

Add a `collect_worktrees(repo)` collector to the status collector whose
enumerating source is `git worktree list --porcelain -z`, surface it as
an additive `git.worktrees` JSON block plus a `==> Worktrees` human
section, and mark held branches in the existing local-branch listing.
Read-only throughout; the recovery-artifacts classifier is not touched.

Edit direction (AGENTS.md source-of-truth rule):
`templates/scripts/sd-ai-command-pack-status.py` is the canonical file
and is edited **first**; the root `scripts/` twin is synchronized to it
byte-identically. Line references in this document cite the root twin
only because greps ran there; the files are identical.

Rejected alternatives:

- **Extending the recovery classifier** to report foreign worktrees —
  rejected by the PRD itself: ownership is receipt-based and
  `active`/`safe-cleanable`/`needs-review`/`missing-artifact`/
  `unowned-artifact` mean specific things about receipts. The new
  inventory is a separate section.
- **Marking held branches by rewriting `localBranches` entries** (e.g.
  `"name [worktree]"` strings in JSON) — rejected: consumers parse
  `git.localBranches` as bare branch names (housekeeping's
  `strict_anomalies` compares against `default`), so the JSON list keeps
  its shape and a separate `git.branchesHeldElsewhere` list carries the
  marking. Human output may decorate, JSON may not.
- **Per-worktree cleanliness via `--porcelain` only** — `git worktree
  list --porcelain` does not report dirtiness, so each existing,
  non-prunable, non-bare worktree row costs one extra
  `git -C <path> status --porcelain` call. Bounded by the number of
  worktrees; acceptable for a local diagnostic command.

## Data collection

New top-level function, called from `collect_git` after the branch
inventory (so its result rides in the same `git` state dict):

```python
def collect_worktrees(repo: Path) -> dict[str, Any]:
    # -> {"status": "ok", "rows": [...]} | {"status": "unavailable"}
```

(The reporting-checkout path is resolved inside the function via
`rev-parse`; no separate parameter.)

- Enumerate with `git_output(repo, "worktree", "list", "--porcelain",
  "-z")`. **`-z` is required, not cosmetic**: worktree paths are
  externally controlled and may contain newlines; without `-z` a
  newline-bearing path shears the line-oriented parse, and lock/prune
  reasons arrive C-quoted instead of raw. With `-z` every attribute
  record is NUL-terminated and entries are separated by an empty record
  (two consecutive NULs). `None` (nonzero exit — including a git too old
  for `worktree list -z`, which then reports honestly instead of
  mis-parsing) -> `{"status": "unavailable"}`. Requirement 7: never
  silently convert failure into an empty healthy result.
- Parsing lives in a dedicated pure function
  `parse_worktree_porcelain(text) -> list[dict]` so tests can drive it
  with fabricated bytes directly. **The parser returns raw values.**
  Sanitization is a serialization concern, not a parsing one: every
  filesystem or git operation (current-row resolution, the identity
  check, the cleanliness probe) uses the raw path, and `safe_text`
  bounding is applied only when `collect_worktrees` composes the
  outgoing JSON row. Sanitizing first would make any path longer than
  the display bound silently non-current and unprobeable. Recognized attributes per entry:
  `worktree <path>` (required), `HEAD <oid>`,
  `branch refs/heads/<name>`, `detached`, `bare`, `locked[ <reason>]`,
  `prunable[ <reason>]`. Unrecognized attribute records are ignored
  (forward compatibility with newer git).
- Row shape:

```json
{
  "path": "<safe_text, limit 300>",
  "branch": "<short name or null>",
  "detached": false,
  "head": "<12-char oid or null>",
  "bare": false,
  "locked": false,
  "prunable": false,
  "reason": "<safe_text lock/prune reason or null>",
  "clean": true | false | null,
  "current": true | false
}
```

- `current`: the reporting checkout. Determined by comparing the block's
  path against `Path(git_output(repo, "rev-parse", "--path-format=absolute",
  "--show-toplevel"))` after `Path.resolve()` on both sides (macOS
  `/private/tmp` vs `/tmp` symlinks make raw string comparison wrong).
  If resolution of a row path raises `OSError`, fall back to the raw
  comparison for that row; at most one row is marked current, and if no
  row matches, no row is (reported as-is per requirement 2 — the
  collector does not chase paths beyond what Git reports).
- `clean`: per-row probe
  `git_output(Path(raw_path), "--no-optional-locks", "status", "--porcelain")`
  **only** when the block is not `bare`, not `prunable`,
  `Path(raw_path).is_dir()`, **and the identity check below passes**.
  Empty output -> `true`, non-empty -> `false`, command failure or
  skipped -> `null`. `null` renders as `unknown` in human output.
  - `--no-optional-locks` (a git global option, so it precedes the
    subcommand in the argv `git_output` builds) is mandatory: plain
    `git status` opportunistically refreshes and **writes** the probed
    worktree's index, which would break the read-only guarantee from
    inside a probe. The reporting tree's own pre-existing
    `status --porcelain=v2` call in `collect_git` predates this task and
    keeps its current form (parked below).
  - Identity check (stale-path-reuse guard): before trusting a probe
    target, run `git_output(Path(raw_path), "rev-parse",
    "--path-format=absolute", "--git-common-dir")` and require it to
    resolve (`Path.resolve()`) to the reporting repository's own common
    dir (obtained once the same way from `repo`). A worktree path
    deleted and re-occupied by an *unrelated* repository would otherwise
    report that stranger's cleanliness. Mismatch or failure ->
    `clean: null`, no `status` probe run.
- Paths and reasons are externally controlled: `safe_text` with the
  limits above (requirement 9). Branch names pass through `safe_text`
  with the default limit.
- Row count is not truncated in JSON. Human output prints at most
  `HUMAN_ITEM_LIMIT * 2` rows with a `; +N more` suffix, consistent with
  the bounded-row convention elsewhere in the collector. (Local `T-*`
  completeness applies to tasks, not to this section; `--json` carries
  the complete inventory.)

## Derived branch marking

After `collect_worktrees`, `collect_git` computes:

```python
state["worktrees"] = worktrees
state["branchesHeldElsewhere"] = sorted({
    row["branch"] for row in rows
    if row["branch"] and not row["current"]
}) if worktrees["status"] == "ok" else None
```

- (Set comprehension, not a generator: forced duplicate checkouts —
  `git worktree add -f` of an already-held branch — must not produce
  duplicate names.)
- The marked set is exactly the branches whose holding worktree is not
  the reporting one. Refusal-set equivalence is claimed for **checkout
  from the reporting worktree, under git's normal exclusive-checkout
  invariant** (no `worktree add -f` forced duplicates): `git checkout
  <name>` from the reporting tree fails precisely for these (checking
  out the branch you are already on is a no-op success, not a refusal).
  Two documented non-equivalences: `git worktree add` additionally
  refuses the reporting tree's own branch; and a *forced duplicate* of
  the reporting branch in another worktree is still marked (the
  visibility is correct — it is held elsewhere) even though checking it
  out from here would no-op succeed. The marked set's definition is
  "held in a worktree other than the reporting one", full stop; the
  checkout-refusal equivalence is a property of the unforced case, and
  AC 2 is scoped accordingly. Detached rows contribute nothing. `None`
  (vs `[]`) distinguishes "inventory unavailable" from "nothing held"
  (requirement 7).
- `strict_anomalies` and every existing consumer of `localBranches` are
  untouched. Classifying held branches (anomaly or not) is
  `08-07-status-housekeeping-anomaly-disagreement`'s scope; this task
  only makes the axis visible.

## JSON contract

`SCHEMA_VERSION` stays 2: the new keys (`git.worktrees`,
`git.branchesHeldElsewhere`) are additive, and the existing schema
version rule in this collector is that additive keys do not bump the
version — verified precedent: the top-level `recoveryArtifacts` key was
added in `7ba4d0c9` (2026-07-28) with `SCHEMA_VERSION = 2` unchanged on
both sides of that commit. No existing key changes shape.

## Human output

In `render_local` (the human formatter, `sd-ai-command-pack-status.py:2171`):

1. The `- local branches (N): ...` line marks each held branch by
   suffixing ` [worktree]` to its name — human output only, JSON
   unchanged.
2. New section after the `==> Expected clean state` block:

```text
==> Worktrees
- /path/to/repo: branch main, clean (reporting)
- /path/to/wt-a: branch codex/x, dirty
- /path/to/wt-b: detached at ab12cd34ef56, clean
- /path/to/wt-c: branch gone/branch, prunable (gitdir file points to non-existent location)
[- ; +N more]
```

- Row order preserves `git worktree list --porcelain` order in **both**
  JSON and human output — git lists the main worktree first, and when
  status runs from a linked worktree the reporting row is deliberately
  *not* first. AC 1's "row for row" is ordered equality against
  porcelain, which reordering would break; the `current` flag (JSON) and
  a `(reporting)` marker (human) identify the reporting row wherever it
  falls.
- Empty state prints explicitly: `- linked worktrees: none` (AC 3 — the
  section is present, not omitted).
- Unavailable prints `- worktrees: unavailable` and appends nothing to
  `anomalies` (same treatment as GitHub inventory unavailability, which
  reports in place; the skill text already forbids treating unavailable
  optional sources as healthy-empty).
- `locked` / `prunable` rows carry their reason when git reported one.

## Read-only guarantees

- Only `git worktree list --porcelain`, `git rev-parse`, and per-row
  `git status --porcelain` are run — all read-only. No `worktree add`,
  `prune`, `repair`, `remove`, `lock`, or receipt write anywhere in the
  new code (requirement 5, AC 4).
- `collect_recovery` and the recovery-artifacts helper are not modified
  at all (requirement 6, AC 5): the diff to
  `sd-ai-command-pack-recovery-artifacts.py` is empty.

## Surfaces beyond the collector

- `scripts/sd-ai-command-pack-status.py` — byte-identical mirror of the
  canonical `templates/scripts/` collector (existing Makefile `cmp`
  gate); synchronized after the template edit per the direction above.
- Skill docs: the sd-status skill's step-4 report list
  (`templates/.agents/skills/sd-status/SKILL.md` as the hand-authored
  source) gains the worktree inventory and the held-branch marking;
  installed mirrors and command surfaces follow via `make generate` /
  `make sync`. Shipped-payload change means the release gates fire:
  manifest bump to 0.64.32, changelog entry, candidate-ledger refresh,
  regenerated surfaces — the same sequence 0.64.31 required, run through
  `make release-prep` (the canonical wrapper, per CONTRIBUTING.md).
- Spec: `.trellis/spec/backend/manifest-and-filesystem.md`'s
  "Read-Only Status And Housekeeping Delegation" section is the status
  collector's contract of record; it gains the worktree-inventory
  sentence and its stale "schema version 1" claim is corrected to 2
  (the code moved to `SCHEMA_VERSION = 2` without the spec following).
- Fleet mode is untouched (PRD out of scope).

## Parked

- Adding `--no-optional-locks` to the reporting tree's own pre-existing
  `status --porcelain=v2` call in `collect_git`. It predates this task,
  its optional index refresh touches only the reporting checkout the
  user invoked status from, and changing it belongs to a deliberate
  repo-wide no-lock decision, not to this additive inventory. Trigger:
  any future task hardening sd-status's read-only contract repo-wide.

## Tests (tests/test_status.py, fixture = make_status_repo; eleven total)

1. **Inventory row parity.** Create two linked worktrees (`git worktree
   add <path> -b wt-branch` and one `--detach`); JSON `git.worktrees.rows`
   has 3 rows (reporting + 2), exactly one `current: true`, and the
   (path, branch/detached) pairs equal those parsed from
   `git worktree list --porcelain` run independently by the test (AC 1).
2. **Held-branch marking, external oracle.** The expected set is derived
   by *attempting the operation*, not by re-running the implementation's
   own rule: for every local branch the test runs
   `git -c core.hooksPath=<empty temp dir> checkout <name>` in the
   fixture root (hooks neutralized so an inherited `post-checkout` hook
   cannot masquerade as a refusal), records refusal vs success —
   a refusal is a nonzero exit whose stderr contains
   `already used by worktree`, so arbitrary failures do not count — and
   restores the initial branch in a `finally` block regardless of
   outcome. `git.branchesHeldElsewhere` must equal the refusal set
   exactly (AC 2, unforced case), and the human `local branches` line
   carries the ` [worktree]` suffix on exactly those names.
3. **Empty state.** No linked worktrees: `rows` has exactly the
   reporting row, `branchesHeldElsewhere == []`, human output contains
   the explicit `linked worktrees: none` line (AC 3).
4. **Read-only** (regression invariant — see baseline note). Seed a
   sentinel receipt in the state root first (an unmodified pre-existing
   receipt is the half of AC 4 an empty state root cannot test). Then
   capture, before and after a full status run with linked worktrees
   present: `git worktree list --porcelain` bytes, the complete
   state-root receipt tree (paths + bytes), and each linked worktree's
   `.git`-dir index file bytes. Assert all three identical — the index
   comparison is what catches an accidental index-refreshing probe that
   the worktree-list comparison cannot see (AC 4).
5. **Recovery independence.** With a foreign (receipt-less) worktree
   present, the recovery section still reports no tracked artifacts and
   the classifier output is unchanged from the no-worktree fixture
   (AC 5).
6. **Prunable.** Create a worktree, `shutil.rmtree` its directory, run
   status: the row reports `prunable: true` and `clean: null`; a
   subsequent `git worktree list --porcelain` still lists it (nothing
   pruned) (AC 6).
7. **Dirty worktree.** Touch a file inside a linked worktree; its row
   reports `clean: false`; the reporting row stays `clean: true`.
8. **Unavailable inventory.** PATH-prefixed git stub failing only the
   `worktree` subcommand (exit 1): JSON `git.worktrees.status ==
   "unavailable"`, `branchesHeldElsewhere is None`, human output prints
   `worktrees: unavailable`, and the run still exits 0 (advisory mode).
9. **Adversarial parser input + long-path integration.** Unit half:
   drive `parse_worktree_porcelain` directly (the tests already load the
   module via `load_module_from_path`) with fabricated `-z` bytes: a
   path containing a newline, a path longer than the 300-char display
   bound, a locked entry with a reason, and an unknown future attribute
   record. Rows parse without shearing, the parser returns the **raw**
   values (the long path unbounded — sanitization happens at
   serialization, per the contract above), and the unknown attribute is
   ignored. Integration half: create a real linked worktree whose
   absolute path exceeds 300 characters (nested directories; each
   component under the 255-byte filesystem limit), run status, and
   assert its row is genuinely probed — `clean` is `true`/`false`, not
   `null` — while the serialized `path` field is `safe_text`-bounded.
   This is the case a sanitize-first implementation fails (requirement
   9, concern R2-3).
10. **Linked-worktree invocation.** Run status with `--repo` pointing at
    a *linked* worktree: exactly the linked row is `current: true` (not
    git's first-listed main-worktree row), JSON row order still equals
    porcelain order, and `branchesHeldElsewhere` now contains the main
    checkout's branch. This is what separates real `rev-parse` matching
    from "mark the first row current".
11. **Stale path reused by a stranger.** Create a linked worktree,
    delete its directory, and `git init` an unrelated repository at the
    same path with a dirty file: the row reports `clean: null` (identity
    check refuses the probe), never the stranger's dirtiness.

Baseline classification (two kinds, checked differently against the
pre-change collector materialized via
`git show HEAD:templates/scripts/sd-ai-command-pack-status.py` into a
temp copy — never stash/revert the working tree):

- **Behavioral tests 1, 2, 3, 6, 7, 8, 9, 10, 11 are fail-before**: the
  keys, section, and parser do not exist pre-change, so each must fail
  against the baseline and pass after — proving they pin the new
  behavior.
- **Tests 4 and 5 are regression invariants**: read-only behavior and
  recovery-classifier output are properties the pre-change collector
  already has, so they must **pass before and pass after**. Demanding
  fail-before of them would be incoherent; their value is guarding that
  the new probes and inventory do not break what already holds.

## Rollback

Collector + twin + tests are one revertable commit; the release-bump
commit follows separately (same shape as PR #392). Reverting both
restores the current report exactly: all new surface area is additive.
