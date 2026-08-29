# Design: typed housekeeping output and progressive spec guidance

## Housekeeping Result

Use one shared eligibility object from the PR-gate task plus housekeeping-owned
action results. The envelope includes:

- repository/branch/PR/head identity;
- finish-work and task-lifecycle state;
- eligibility object and reason codes;
- attempted/completed merge and cleanup actions;
- branch deletion/switch/prune outcomes;
- remaining local/remote state; and
- final `clean|blocked|indeterminate|failed` classification.

The helper remains executable truth. The skill explains policy, handles
judgment where needed, and renders the final conclusion.

Expose the envelope through `sd-ai-command-pack-housekeeping.sh --json` while
preserving the current human output as the default. JSON mode reserves stdout
for one schema-version-1 document and sends progress and diagnostics to stderr.
The Bash orchestrator records stable action and anomaly codes beside the
existing human messages, captures the delegated `sd-status --json` report, and
passes both to a small stdlib result builder. The result builder validates and
assembles data; it does not collect Git/GitHub evidence or gain mutation
authority.

The PR evaluator gains a combined machine adapter format that emits its compact
JSON result and the existing shell receipt from one evidence collection. This
prevents housekeeping from querying a moving PR twice merely to obtain both
representations. The envelope embeds that evaluator JSON unchanged and keeps
the evaluator's schema and reason codes authoritative for exact-head checks,
reviews, threads, and finish-work evidence.

The envelope is intentionally compositional rather than a second status or
eligibility model:

- `invocation` records remote, merge strategy, dry-run, branch-retention,
  dependency-PR, and finish-work inputs;
- `actions` and `anomalies` contain stable codes plus bounded human messages;
- `eligibility` is the existing evaluator result or `null` when no open-PR
  evaluation was applicable;
- `status` is the complete existing `sd-status` schema-version-1 report;
- `outcome.status` is `clean|blocked|indeterminate|failed` with stable reason
  codes derived from the embedded evidence; and
- identity fields bind the result to repository, start/default/current branch,
  PR, and full observed heads.

Unknown input schema majors, malformed delegated reports, unsafe codes, or
unbounded messages fail visibly. The JSON builder is read-only. Housekeeping
remains the only owner of fetch, merge, switching, pull, branch deletion, and
prune actions, and every existing exact-head mutation-boundary recheck remains
in the Bash executable.

## Update-Spec References

Direct references are split by optional concern:

- architectural overview maintenance;
- generated repository-map/repospec refresh; and
- Obsidian/knowledge-base refresh.

The canonical skill retains Trellis delegation, extension ordering, selection
criteria, shared safety, the normal one-line KB helper invocation, and final
report fields. It loads no optional reference during a routine spec-only run.
When deterministic repository evidence or an explicit request activates an
extension, it loads that extension's direct reference before acting. Multiple
independent extensions may apply in one run, but references never point to one
another and each concern is loaded at most once.

Reference routing fails closed: a selected reference that is missing,
unreadable, empty, outside the installed skill directory, or contradictory to
the canonical safety rules stops that extension and is reported rather than
silently skipped. The registry owns reference fanout to every installed skill
root; templates remain the authored source.

## Compatibility

JSON schemas are versioned. Human output may evolve, but tests and consumers use
stable fields/reason codes. Unknown schema majors fail visibly.

## Rollback

Rollback reinstalls the prior pack version. Do not keep duplicate prose and JSON
paths live after the typed contract is proven.
