# Selectable sd-status inventory design

## Boundaries

The shipped template `templates/scripts/sd-ai-command-pack-status.py` remains
the only collector and renderer. The root `scripts/` copy remains a byte-
identical dogfood mirror produced by `make sync`. The canonical shared skill at
`templates/.agents/skills/sd-status/SKILL.md` explains the report and selection
semantics; platform adapters remain thin and unchanged unless generation proves
their summary inaccurate.

No new command, option, persistence file, network request, or mutation path is
introduced. The collector continues to use its existing Git, optional GitHub,
Trellis, version, and work-loop reads.

## Structured contracts

Local JSON retains schema version 1 because the change is additive. It gains a
top-level `followUps` array, and the existing `trellis` object gains `tasks` and
`roadmap` arrays:

```json
{
  "followUps": [
    {
      "selectionId": "F-1",
      "kind": "action",
      "summary": "Review and commit or intentionally discard the current working-tree changes.",
      "source": "git.workingTree"
    }
  ],
  "trellis": {
    "tasks": [
      {
        "selectionId": "T-1",
        "id": "task-id",
        "title": "Task title",
        "status": "planning",
        "priority": "P1",
        "path": "tasks/07-23-task-id",
        "parent": "07-22-program"
      }
    ],
    "roadmap": [
      {
        "selectionId": "R-1",
        "id": "program-id",
        "title": "Program title",
        "status": "planning",
        "priority": "P1",
        "path": "tasks/07-22-program",
        "parent": null
      }
    ]
  }
}
```

Existing `activeTask`, `inProgress`, `planned`,
`completedOutsideArchive`, `anomalies`, and `nextSteps` fields remain available
for housekeeping and current automation. Their task records may gain the
additive `parent` field, but selection IDs live only on the category-specific
views so one durable task is not ambiguously assigned both T and R IDs in the
same object.

## Classification and ordering

The task scanner continues to accept only regular, non-symlinked direct child
task records under `.trellis/tasks/`. It records a bounded string parent only
when `task.json.parent` is a nonblank string.

`tasks` ordering is:

1. the current active task, when it is part of the scanned unarchived set;
2. lifecycle state: `in_progress`, `planning`, `completed`, then other states;
3. priority: P0 through P3, then unprioritized;
4. case-folded title and durable ID.

Duplicate inclusion of the active task is prevented by durable ID and path.
`T-N` is assigned after sorting.

`roadmap` contains tasks with no parent and status `in_progress` or `planning`.
It uses the same lifecycle/priority/title/ID ordering, then receives `R-N`.
This treats a top-level Trellis task as the roadmap work stream and its children
as independently selectable implementation tasks.

Follow-ups are built from normalized evidence before rendering. Each candidate
has `kind`, `summary`, and `source`; identical `(kind, summary)` candidates are
deduplicated while preserving priority order. Ordering is:

1. explicit anomalies and invalid lifecycle state;
2. Git working-tree/upstream/divergence actions;
3. active PR and work-loop actions;
4. completed-task archival and installed-pack drift;
5. open GitHub issues and other evidence-backed recommendations.

Task-resume and task-start suggestions remain in the task/roadmap categories,
not F rows. This prevents `sd-status` from maintaining a parallel backlog.
The existing bounded `nextSteps` compatibility summary may reference the first
F/T/R choices but is not the authoritative selectable inventory.

## Human output

After `Anomalies`, local rendering prints:

```text
==> Follow-ups
F-1 [action]: <summary>

==> Tasks
T-1 [in_progress, P1]: <title> (<durable-id>; <path>)

==> Roadmap
R-1 [planning, P1]: <title> (<durable-id>; <path>)
```

An empty category prints a single unbulleted `none` line. T and R sections are
complete for the requested local repository, while individual externally
controlled strings remain sanitized and bounded. The existing compact
`Inventory` section keeps GitHub counts and current-task context but stops
showing a misleading one-item planned-task preview.

Fleet rendering uses the same structured local reports for machine consumers.
Its human table stays bounded and adds an F-prefixed fleet follow-up section;
per-consumer task/roadmap details remain available through `--json` or a local
status request for that checkout.

## Skill behavior

The shared skill requires the final response to preserve the three sections
and all collector-issued IDs. It states explicitly that IDs are valid for the
reported snapshot and that a later selection request starts the appropriate
normal workflow only after applying that workflow's own consent and safety
rules. `sd-status` itself never invokes the selection.

## Compatibility, release, and rollback

The JSON additions are backward-compatible and retain schema version 1. Human
output gains headings but preserves existing health, delivery, work-loop,
inventory, anomaly, and strict-housekeeping facts. This is a changed distributed
command semantic, so repository policy requires a minor release.

Rollback reverts the template collector, skill, documentation, tests, manifest
version/changelog, generated mirrors, and candidate evidence together. No
consumer state migration is required.

## Risks

- Large task inventories can produce longer local human output. This is
  intentional because the user requested all tasks; sanitization bounds each
  row, and fleet human output stays compact.
- A root task may be a standalone deliverable rather than a formal program.
  Treating all open roots uniformly is deterministic and matches Trellis's
  source-of-truth hierarchy without inventing new metadata.
- F rows could duplicate task-backed work. Classification excludes generic
  resume/start suggestions and tests pin the de-duplication boundary.
