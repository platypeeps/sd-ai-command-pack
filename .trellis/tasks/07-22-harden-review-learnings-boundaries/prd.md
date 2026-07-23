# Harden review learnings write boundaries

## Goal

Make `sd-review-learnings` observably read-only by default and prevent accidental
writes outside the repository. Add a complete invocation, safety, mutation, and
final-report contract while preserving intentional in-repository learning
updates.

## Evidence

- `templates/.agents/skills/sd-review-learnings/SKILL.md:14-88` lacks the
  consistent arguments, safety, and final-report sections used by stronger
  mutating skills.
- `templates/scripts/sd-ai-command-pack-review-learnings.py:1405-1408` accepts
  absolute or repository-relative targets without a repository-containment
  policy.
- Lines 1355-1386 and 1545-1560 create parent directories and write the target.

## Dependencies

- Consume `07-22-add-portable-structured-questions` for explicit external-write
  confirmation in interactive skill flows.
- No dependency on routed-review consolidation; coordinate only documentation
  naming if that task changes review terminology.

## Requirements

- R1: Default invocation is scan/report only and performs no write, directory
  creation, task creation, staging, commit, push, or remote mutation.
- R2: Require an explicit update mode for repository-local writes. The skill
  must state the exact canonical target and planned mutation before invoking it.
- R3: Resolve the repository root and target canonically, including symlinks.
  Reject lexical and symlink escapes outside the repository by default.
- R4: Permit an external target only through a separate explicit option plus a
  structured confirmation that names the resolved absolute path and impact.
  Noninteractive runs stop rather than inferring consent.
- R5: Validate target type, encoding, ownership expectations, and existing
  content before writing. Use atomic replacement and preserve unrelated
  content according to the current section/update contract.
- R6: Report mode, repository root, resolved target, containment class,
  findings, proposed/applied changes, and whether any write occurred.
- R7: Add explicit arguments, safety rules, mutation boundaries, failure
  behavior, and final-report sections to the canonical skill.
- R8: Do not stage, commit, or publish the learning update; those remain
  separate lifecycle actions.

## Acceptance Criteria

- [ ] Default scan leaves filesystem and Git state unchanged.
- [ ] Explicit repository-local update writes only the resolved intended file
  and preserves unrelated content.
- [ ] `../`, absolute external, symlink-escape, broken-symlink, directory, and
  unreadable target fixtures fail safely by default.
- [ ] External update requires both the explicit option and a recorded
  interactive confirmation; unavailable/noninteractive question capability
  stops without writing.
- [ ] Atomic-write interruption cannot leave a partial target.
- [ ] Final reports distinguish proposed, applied, skipped, and failed writes.
- [ ] Focused script/skill/generated parity tests and `make check` pass.

## Out Of Scope

- Automatically committing or publishing learned guidance.
- Writing to upstream Trellis or another repository by default.
- Changing review finding classification unrelated to write safety.
