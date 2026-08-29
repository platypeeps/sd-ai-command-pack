# Design

## Surfaces

| Surface | Change |
| --- | --- |
| `.agents/skills/sd-fleet-refresh/SKILL.md` | rewrite the `pr-publication` bullet into an ordered sequence |
| `docs/FLEET_ROLLOUT.md` | align the publication steps with the skill |
| `templates/scripts/sd-ai-command-pack-review-preflight.mjs` | payload source: add `checkGeneratedStructuralMapPaths` |
| `scripts/sd-ai-command-pack-review-preflight.mjs` | installed copy, rewritten by `make sync` (`install.py . --force`) |
| `tests/test_review_preflight.py` | new cases |
| `manifest.json`, `CHANGELOG.md` | version bump for the payload change |

## Ordering fix

The current bullet reads as one paragraph whose first sentence ends "push, and
create or reuse one PR", and whose fourth sentence introduces the fold. Rewrite
as an explicit numbered sequence:

1. Stage only the dedicated task artifacts, installer-managed output,
   receipts/provenance, and deterministic preparation output.
2. Run `sd-ai-command-pack-fleet-publish.py`. It makes the work commit with a
   pre-computed post-archive map, archives the task, records the journal, takes
   the completion receipt, asserts the delta, and pushes.
3. Classify the pushed head with `sd-ai-command-pack-fleet-review-classify.py`.
4. Create or reuse one PR and record the published head and PR number.

A consumer the helper refuses (one carrying
`.github/scripts/bookkeeping_ci_scope.py`) self-releases through
`sd-finish-work`; the map is then regenerated *after* `task.py archive` and
before the finish-work push, never after it. State that explicitly so the
fallback does not reinvent the broken order.

Ordering is stated once as a sequence and referenced from `FLEET_ROLLOUT.md`,
so the two documents cannot drift into two different orders.

## Guard

New check `checkGeneratedStructuralMapPaths`, registered in
`runReviewPreflight` after `documentation path references`.

Input: `config.generatedStructuralMaps`, defaulting to
`['docs/repomix-map.md']`. A configured file that does not exist is skipped,
so a repository owning no map passes with a stated reason.

Parsing is confined to the map's own `# Directory Structure` section: start at
a line matching `^# Directory Structure\s*$`, stop at the next `^# ` heading or
end of file. Repomix wraps the listing in a fenced block, so lines that are
only backtick runs are skipped rather than parsed as entries — verified against
the maps in rwbp-coordinator and anomaly-metric-creator, both of which open and
close the section with a four-backtick fence. Inside the fence, every non-blank
line is `indent + name`, indent is a multiple of two spaces, and a trailing `/`
marks a directory. Reconstruct the
full path by keeping a stack of directory names indexed by depth; a line whose
indent skips a level, or whose indent is odd, aborts the parse for that file
with a `warn` rather than a `fail` — an unparseable map is a different defect
and must not be reported as drift.

Only reconstructed paths starting with `.trellis/` are checked for existence.
That bound is deliberate:

- `.trellis/` is the tree the fleet flow moves between generation and commit,
  so it is where this drift actually occurs;
- every path under it is tracked, so a checkout of the same commit sees the
  same tree, which keeps the check reproducible in CI;
- broader trees can legitimately list files that are present when the map is
  generated and absent in a fresh clone, which would make the check fail for a
  reason that is not this defect.

Reported failures name the map file, the 1-indexed line, and the reconstructed
path. Failures are capped at the first 20 with a count of the remainder, so a
map generated against an unrelated tree does not flood the report.

## Failure modes considered

- **Map exists, section missing** — nothing to parse; pass with a reason.
- **Map lists a path that a `.gitignore` change later excluded** — reported,
  correctly: the committed map no longer describes the tree.
- **Symlinked `.trellis` entry** — checked with `pathEntryExists()`, which
  `lstat`s the entry, so a listed symlink counts as present even when its
  target is absent. The map records what the tree contains, not whether every
  link resolves; a dangling link is a different defect and reporting it here
  would name the wrong remedy.
- **Very large map** — parse is a single pass over one section; the existing
  `readText` cache is reused.
- **A repo that owns a differently named map** — `loadConfig` unions array
  keys, so a repo adds its own map path and cannot drop the default. Dropping
  it is unnecessary: a configured file that does not exist is skipped, so a
  repo carrying no repomix map passes on the stated reason.

## Evidence

- `checkDocumentationPathReferences` skips `docs/repomix-map.md` explicitly
  (`scripts/sd-ai-command-pack-review-preflight.mjs`, in the exemption list
  beside `docs/SD_AI_COMMAND_PACK.md`), which is why no local gate saw the
  drift.
- `manifest.json` maps
  `templates/scripts/sd-ai-command-pack-review-preflight.mjs` to
  `scripts/sd-ai-command-pack-review-preflight.mjs` with `install: always`, so
  the payload source is the template and the bump is required.
- Array-valued config keys are merged in `loadConfig` from a fixed key list;
  `generatedStructuralMaps` joins that list and inherits the same
  string-filtering behaviour.

## Rollout

The check ships in the payload, so a consumer receives it at its next refresh
and it becomes part of `sd-check` through the `pack.review-preflight` builtin.
No consumer action is required. A consumer whose committed map is already stale
will see the failure on its next PR; the remedy is regenerating the map, which
is a one-command fix.
