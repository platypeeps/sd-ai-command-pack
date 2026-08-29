---
title: Parity test enumerates git-ignored .opencode paths
status: done
created: 2026-08-18
branch: task/opencode-parity-ignores-git
---
# Parity test enumerates git-ignored `.opencode` paths

## Goal

Make `test_opencode_plugins_do_not_require_local_dependency_manifest` assert what
it means — that the *tracked* `.opencode` payload carries no external dependency
— instead of asserting facts about whatever happens to be on the developer's
disk.

## Problem

The test has two failure modes, both from the same root cause: it enumerates and
stats the working tree, while the property it protects is about the git index.

**1. It fails on a correctly set up checkout.** `tests/test_generated_parity.py:1370`
asserts the OpenCode manifest does not *exist* (the path is bound at `:1364`).
`CONTRIBUTING.md:203-211` — tracked, and pinned by this same test file at
`:1336-1337` — tells developers not to *track* that manifest or a Bun lockfile,
and gives them the command that creates both:

> Do not track the OpenCode manifest or any `.opencode` Bun lockfile in this
> repo unless the checked-in OpenCode plugins or tools import external npm
> packages. … `cd .opencode` / `bun install --lockfile-only`

(paraphrased; the verbatim text is at `CONTRIBUTING.md:203-211`, and spelling the
manifest path here would trip the very check this task's sibling
`08-18-preflight-path-refs-ignore-aware` exists to fix)

Follow that and the suite goes red:

```
AssertionError: True is not false : .opencode/package.json is only needed when plugins import packages
```

"Do not track" and "must not exist" are different claims, and the test asserts
the second while the documentation states the first.

**2. Behind that, it walks `node_modules`.** `.gitignore:136` ignores
`.opencode/node_modules/` outright, so it is never payload. But
`opencode_module_sources` (`test_generated_parity.py:187-192`) globs
`**/*{suffix}` under `.opencode` with no ignore filter, so once assertion 1 stops failing, the scan descends into
`.opencode/node_modules/` and reports the vendored packages' own imports as pack
external imports. `assertEqual([], external_imports)` then fails on
`@opencode-ai/plugin`'s internals — code this repository does not ship and has no
say over.

The two are ordered: fixing only the first exposes the second, which is why they
belong to one task.

## Impact

Local `make check` is red for any developer whose `.opencode` is installed. The
workaround in use has been to move `.opencode/{package.json,package-lock.json,node_modules}`
out of the tree before running checks, which also breaks the OpenCode plugins
locally. CI is green only because its checkout never runs the install step, so
the gate protects nothing there and blocks work here.

## Requirements

1. The enumeration is authoritative about tracked payload. Derive the file set
   from git, not from a filesystem glob, so an ignored path cannot enter it and
   a newly tracked `.opencode` module cannot escape it.
2. The manifest and lockfile assertions test *trackedness*, not existence. A
   locally installed manifest, `package-lock.json`, `node_modules/`, or
   `bun.lock` must not affect the result.
3. The gate keeps its teeth: a tracked `.opencode` module that imports an
   external package still fails the test.
4. The test passes both on a pristine checkout with no `.opencode` install and on
   one with the full install present.
5. No shipped payload changes. This is test-only, so no `manifest.json` bump, no
   `make sync`/`make generate`, and no candidate-ledger refresh.

## Acceptance criteria

- [x] With `.opencode/{package.json,package-lock.json,node_modules}` present, the
      test passes; the failure above is quoted as the before-state.
- [x] In a pristine worktree with no `.opencode` install, the test passes.
- [x] A tracked `.opencode` module temporarily given an external import makes the
      test fail, and the failure names that file; reverting restores green.
- [x] `opencode_module_sources` (or its replacement) returns zero paths under
      `.opencode/node_modules/` when that directory is populated, asserted by a
      test rather than by inspection.
- [x] `make check` passes with the `.opencode` install in place.
- [x] `git status --short` shows no `.opencode` payload change and no
      `manifest.json` version change.

## Out of scope

- Any other assertion in `test_generated_parity.py`, and the CONTRIBUTING/Makefile
  string pins at `:1322-1359`.
- Whether `.opencode` should vendor a manifest at all — the current
  no-external-dependency policy is the thing being protected, not revisited.
- Other surfaces that resolve paths against the working tree. One is already
  recorded: `templates/scripts/sd-ai-command-pack-review-preflight.mjs:3198`
  validates documentation path references with `(candidate) => exists(candidate)`,
  so a deliberately git-ignored path reads as a missing one and fails
  `CI scope`. That is the same defect in shipped payload, it needs a version
  bump, and it is filed as `08-18-preflight-path-refs-ignore-aware`. The prose
  above works around it by naming the manifest rather than spelling its path
  outside a fenced block.
