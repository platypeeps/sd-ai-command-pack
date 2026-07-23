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

## Update-Spec References

Direct references are split by optional concern:

- architecture/source map;
- generated repository map; and
- Obsidian/knowledge-base refresh.

The canonical skill contains selection criteria and shared safety. It reads one
reference only when the repository evidence or explicit invocation matches.

## Compatibility

JSON schemas are versioned. Human output may evolve, but tests and consumers use
stable fields/reason codes. Unknown schema majors fail visibly.

## Rollback

Rollback reinstalls the prior pack version. Do not keep duplicate prose and JSON
paths live after the typed contract is proven.
