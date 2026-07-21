# Refine first-review boundary warning

## Goal

Prevent the first-review boundary-risk sweep from treating test harness code as
new production boundary behavior, while preserving warnings for equivalent
runtime source changes.

## Background

- The review preflight scans added lines from changed executable source files
  for parser, subprocess, filesystem, environment, and integrity patterns.
- A consumer PR that added only dependency-free package-script configuration
  and `test_project_check.py` under the conventional `tests/` directory
  triggered subprocess, filesystem, and environment advisories because the
  test used a stub runner and temporary paths.
- Declarative `package.json` files are not part of the executable-source scan;
  the false positive came from the changed test file.
- Template scripts are canonical and the installed root script must remain a
  byte-identical mirror.

## Requirements

1. Restrict the first-review boundary-risk content scan to changed executable
   source paths that are not conventional test paths.
2. Recognize tests by conventional directory segments (`test`, `tests`, and
   `__tests__`) and conventional executable-source filenames (`test_*`,
   `*_test`, `*.test`, and `*.spec`).
3. Keep production files with similar but non-test names, such as
   `test-runner.sh` under the `scripts/` directory, eligible for the risk scan.
4. Do not change authored-source size accounting, multi-task scope checks,
   untracked-file read bounds, or the risk-category token rules themselves.
5. Preserve warnings when any changed production source adds a boundary-risk
   trigger, including when tests change in the same diff.
6. Update the canonical template first and synchronize its installed root
   mirror.

## Acceptance Criteria

- [ ] A test-only change containing subprocess, filesystem, and environment
      tokens produces no boundary-risk behavior warning.
- [ ] Equivalent tokens in changed production source still produce the
      existing advisory with the applicable categories.
- [ ] Mixed production and test changes derive categories only from production
      added lines.
- [ ] Path classification tests cover conventional test directories,
      conventional test filenames, and non-test names beginning with `test-`.
- [ ] Existing oversized/unreadable production-source behavior and diff-size
      checks remain green.
- [ ] Canonical/template parity and the repository full quality gate pass.

## Out of Scope

- Adding `package.json` or other declarative manifests to the risk-token scan.
- Making test-path conventions configurable.
- Changing the advisory text, category regexes, or remote-review workflow.
