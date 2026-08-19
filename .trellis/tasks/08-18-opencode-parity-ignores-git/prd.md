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
asserts `.opencode/package.json` does not *exist* (the path is bound at `:1364`). The repository deliberately
ignores that path, and instructs developers to create it:

```
.opencode/.gitignore:1:node_modules       .opencode/node_modules
.opencode/.gitignore:2:package.json       .opencode/package.json
.opencode/.gitignore:3:package-lock.json  .opencode/package-lock.json
```

`CONTRIBUTING.md` carries both halves — "Do not track `.opencode/package.json`
or any `.opencode` Bun lockfile" and a `cd .opencode` install step — and
`test_generated_parity.py:1336-1337` pins those two strings in this same file. So a developer who
follows the documented setup makes the suite red:

```
AssertionError: True is not false : .opencode/package.json is only needed when plugins import packages
```

The ignore rule and the assertion contradict each other. Ignoring a path is a
statement that it may exist untracked; the assertion says it may not exist at
all.

**2. Behind that, it walks `node_modules`.** `opencode_module_sources`
(`test_generated_parity.py:187-192`) globs `**/*{suffix}` under `.opencode` with
no ignore filter, so once assertion 1 stops failing, the scan descends into
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
   locally installed `.opencode/package.json`, `package-lock.json`,
   `node_modules/`, or `bun.lock` must not affect the result.
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
- Other suites that glob the working tree; if the same pattern exists elsewhere it
  is a separate finding, recorded but not fixed here.
