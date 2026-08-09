# Implementation plan: deployment-thin-consumers (parent)

Parent task is not the code-implementation target. Its execution =
sequence the children, keep cross-child contracts coherent, and run
final acceptance-level integration validation. Code lands in children.

## Children (created 2026-08-09, linked in task.json)

| Order | Task | Parent requirement |
|-------|------|--------------------|
| 1 | `08-09-thin-surface-partition` | 1 |
| 2 | `08-09-thin-plugin-packaging` | 2 (Claude) |
| 3 | `08-09-thin-machine-installer` | 2 (rest) |
| 4 | `08-09-thin-fleet-status-pins` | 4 |
| 5 | `08-09-thin-migration` | 3, 5, 6 |

Each child PRD states its own ordering constraints; tree position is
not a dependency system. Children 1-4 all ship before any consumer
converts; child 5 is last.

## Ordered checklist

1. [ ] Each child completes its own planning (design/implement
       artifacts as warranted, adversarial review) and ships through
       the normal workflow (task.py start, PR, CI, merge).
2. [ ] Parent re-checks cross-child contract drift at each child's
       convergence: partition output schema, receipt shape, pin
       semantics, revert command name — the same value must agree in
       every artifact that cites it.
3. [ ] After `thin-migration` completes: run the acceptance-level
       integration validation below; check every parent PRD AC box or
       file an explicit follow-up task per gap; then archive parent.

## Acceptance-level integration validation (parent, run before archive)

Concrete checks, not deliverable mapping:

- **Release reach:** perform one pack release; verify a migrated
  consumer repo has zero resulting commits and `sd-pack-update` on a
  machine lands the new version
  (`claude plugin list --json` shows it; machine receipt matches).
- **Payload-free CI:** on a migrated consumer at HEAD,
  `git grep -l "sd-ai-command-pack"` returns only `repo-native` +
  `consumer-config` + pin-receipt paths per the partition output, and
  its CI run is green with zero pack steps.
- **Skew visibility:** with plugin version ≠ latest release,
  `sd-status` fleet mode emits an F-row naming the skew; nothing
  reports clean.
- **Rollback:** run `install.py TARGET --revert-thin` on one migrated
  consumer; verify fat payload restored, thin artifacts absent except
  the intentional per-repo `enabledPlugins` disable marker, CI green;
  then re-convert.
- **Retirement closure:** grep of install/fleet spec surfaces (the
  requirement-6 enumeration) finds zero descriptions of consumer
  vendoring as current behavior; retired gate code paths removed or
  rescoped, verified by the pack test suite
  (`.venv/bin/python -m unittest`).

## Validation commands (parent bookkeeping)

- `python3 ./.trellis/scripts/task.py list --mine` shows the five
  children linked under the parent.
- `node scripts/sd-ai-command-pack-review-preflight.mjs` on every
  parent bookkeeping push.

## Review gates

- Planning adversarial review (host + Codex contract) before parent
  `task.py start`.
- Each child carries its own planning review before its start.

## Rollback points

- Before any child ships: parent + artifacts are bookkeeping only;
  revert = archive parent, delete children.
- After machinery children (1-4) ship but before migration: fleet
  remains fully fat; new machinery is dormant.
- During migration: any consumer reverts via
  `install.py TARGET --revert-thin`; vendoring gates still active
  until the final conversion.
