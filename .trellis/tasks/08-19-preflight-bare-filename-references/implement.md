# Implementation plan — validating bare-filename documentation references

Edit `templates/scripts/sd-ai-command-pack-review-preflight.mjs` only; the other
three copies are generated at step 6. Line numbers below cite the root copy
`scripts/sd-ai-command-pack-review-preflight.mjs`, which is byte-identical.

## 0. Baselines — record before any edit

- [ ] `node scripts/sd-ai-command-pack-review-preflight.mjs; echo "exit=$?"`
      → expect `exit=0` and the line
      `PASS documentation path references resolve to existing repo files, are optional by configuration, or are marked absent at the point of use.`
      Zero `FAIL … references missing path …` lines today; any at the end is a
      regression.
- [ ] `.venv/bin/python -m unittest tests.test_review_preflight` → record the
      `Ran N tests … OK` line.
- [ ] `node .trellis/tasks/08-19-preflight-bare-filename-references/research/measure-baseline.mjs`
- [ ] `node .trellis/tasks/08-19-preflight-bare-filename-references/research/measure-proposed.mjs`
      → record `residualLocator` and its file list. Planning measured **4** at
      `c10de14f`, `7f02caaa` and `09993578`. Every other figure drifted between
      those HEADs; this one did not. If it moved, work from the new list, not
      from `prd.md`'s table.

## 1. Fix the corpus first (R6)

Markers only — no checker edit in this step. They are inert until step 3 ships
the rule, so the gate cannot go red here.

Locate each span by **content, not line number**. These files are live: during
planning the `08-08-upstream-handoff-register` site moved from line 78 to 103
under a concurrent session. Take the current list from step 0's
`measure-proposed.mjs` output rather than from the lines below.

- [ ] `.trellis/tasks/08-07-default-local-review-lanes/prd.md` — the
      `review-local.sh:535-538` span
      → `[absent: surface deleted by 07-24-remove-retired-review-surfaces]`.
- [ ] `.trellis/tasks/08-08-upstream-handoff-register/prd.md` — the
      `regression.test.ts:12526-12723` span
      → `[absent: upstream Trellis repository]`.
- [ ] `.trellis/tasks/08-09-deployment-thin-consumers/research/consumer-ci-usage.md`
      — both `ci.yml:293` spans → `[absent: consumer repository]`.

The marker must sit on the same line, separated from the closing backtick by
nothing but spaces or tabs (`ABSENT_PATH_MARKER_PATTERN`, `:157`). Two of these
sit mid-sentence and one inside parentheses; place the marker immediately after
the span, not at end of line.

- [ ] Re-run `measure-proposed.mjs`. **`residualLocator` must be 0.** A non-zero
      count here means a marker did not take — do not proceed.
- [ ] Re-run the preflight. Still `exit=0`; the markers changed nothing yet.

Do not touch the 59 noun-form references. They are declined by rule (R4), not
by annotation.

## 1b. Scope confirmation gate — before any checker edit

**Blocking.** Confirm with the operator that the locator-only scope is accepted:
line-cited bare filenames become checked, unsuffixed ones stay declined. It is
the one place this plan departs from the original PRD's stated rule, every test
below encodes it, and once step 2 lands the decision is propagated to four
copies of the checker. Asking after the code exists makes the gate ceremonial.

## 2. Checker — resolution rule (R1, R2, R4, R5)

All edits in `templates/scripts/sd-ai-command-pack-review-preflight.mjs`.

**The governing rule for this step: eligibility tests shape, resolution consults
the index.** Never the other way round. If `shouldCheckDocumentationPathReference`
ever needs to know whether a file is tracked, the design has been misread and
R1's failing half is gone.

- [ ] Hoist the line-suffix regex out of `resolvesToLineSuffixedPath` (`:5056`)
      into a module constant `LINE_SUFFIX_PATTERN` beside
      `ABSENT_PATH_MARKER_PATTERN` (`:157`), and have `resolvesToLineSuffixedPath`
      use it. Eligibility and resolution must not carry a second copy that can
      drift. **Keep it flagless** — adding `g` gives the shared literal a
      persistent `lastIndex`, so the two callers would alternate results on
      identical input.
- [ ] Add `bareReferenceExtensions` to the `config` defaults near
      `topLevelReferenceFiles` (`:385-394`): `md`, `mdx`, `py`, `mjs`, `js`,
      `ts`, `sh`, `json`, `jsonl`, `toml`, `yml`, `yaml`, `txt`, `cfg`, `ini`.
- [ ] Add `bareReferenceExtensions` to the `loadConfig` merge list (`:451-467`).
      It must go in the `Array.isArray` block with the other seven arrays — that
      block is what gives R9 fail-closed behaviour, so do not add a bespoke path.
- [ ] Add `PACK_NAME_PREFIXES = ['sd-ai-command-pack-', 'sd_ai_command_pack_']`
      as a module constant, with a comment stating that the list is **closed**
      and why: these are the pack's own file-naming convention in its executable
      and Python-module forms, and an open-ended match would resolve names the
      author never wrote.
- [ ] Add `trackedFileBasenames()` — one `runGit(['ls-files', '-z'])` call,
      cached in a module-level variable alongside `installedTargetsCache` and
      `documentationGuardFilesCache` (`:35-36`), returning a
      `Map<basename, string[]>`. Reset it in the cache-reset block at `:307-308`.
- [ ] Add `resolveBareFilenameReference(name, basenames)`: strip the line suffix,
      then try `name`, then each prefix in `PACK_NAME_PREFIXES` that `name` does
      not already start with. Return the first non-empty candidate list, or
      `null`.
- [ ] `shouldCheckDocumentationPathReference` (`:5133`): before the final
      `referencePrefixes.some(...)` return at `:5179`, add the bare-filename
      branch — no `/`, no `..`, matches `BARE_REFERENCE_PATTERN` built from
      `bareReferenceExtensions`, and `LINE_SUFFIX_PATTERN` matches.
      **Add no new parameter.** All four conditions are shape tests over the
      target string. Do not thread the basename index in here: it would be dead
      weight, and consulting it would make eligibility and resolution the same
      predicate, so `nope-xyz.py:9` could never be reported.
- [ ] **Export `resolveDocumentationReference`** (`:5197`). It has no `export`
      keyword today while 40 siblings do. R2 and R3 are claims about resolution
      and are untestable without a repository until this changes.
- [ ] `resolveDocumentationReference` (`:5197`): take the index from
      `options.trackedBasenames`, defaulting to `trackedFileBasenames()`. When
      the target is a bare filename, return the first resolved candidate path.
      When it resolves to nothing, **return the bare target unchanged** so
      `findMissingDocumentationPathReferences` probes it and reports it missing.
      Returning `null` would silently swallow the one case R1 exists for.

**Enumerate the declines (R5).** The checker declines exactly three classes, all
decided on shape. Write the comment block above the new branch in the style of
the `design.md`/`implement.md` exemption comment at `:3186-3190`:

1. no line suffix — used as a noun, not a locator;
2. a `..` segment — traversal, which the pattern's charset alone does not
   exclude;
3. an extension outside `bareReferenceExtensions`.

**Do not write "foreign-repository references" into this comment.** The checker
has no notion of a foreign repository and cannot decline one; such a reference
is eligible, unresolvable, and reported like any other, and it is the per-site
`[absent: <reason>]` marker from step 1 that accepts it. A comment claiming
otherwise documents a rule the code does not contain. Each of the three classes
above is pinned by an assertion in step 4 — the comment records intent, the
tests are what discharge R5.

- [ ] Leave `findMissingDocumentationPathReferences` (`:5011`) unchanged.

## 3. Verify against the real checker

- [ ] `node scripts/sd-ai-command-pack-review-preflight.mjs; echo "exit=$?"`
      after `make sync`. **`exit=0`, zero `FAIL … references missing path …`.**
      This is the binding check — the measurement scripts reimplement the guard
      walk and can agree with a checker that is still wrong.
- [ ] Spot-prove the rule fires rather than passing vacuously:
      ```
      node -e "import('./scripts/sd-ai-command-pack-review-preflight.mjs').then(m=>{
        for (const t of ['review.py:555','install.py:12','fleet_lib.py:3','review.py','coverage.py','nope-xyz.py:9'])
          console.log(t, m.shouldCheckDocumentationPathReference(t));
      })"
      ```
      Expect `true` for the four locator-form names and `false` for `review.py`
      and `coverage.py` (noun form). `nope-xyz.py:9` is `true` at eligibility and
      is caught as missing at resolution.
- [ ] Temporarily add `` `no-such-file-zzz.py:1` `` to a guard doc, re-run, and
      confirm it is reported. Remove it. Without this the "fails when it resolves
      to nothing" half of R1 is asserted only by a unit test.

## 4. Tests (`tests/test_review_preflight.py`)

**Every assertion here must fail against the unmodified checker.** Nothing bare
is eligible today, so `shouldCheck…('review.py') === false`,
`…('coverage.py') === false`, `…('../escape.py:1') === false` and
`…('a..b.py:1') === false` all pass *right now* and assert the absence of a rule.
Each is therefore written as a **pair** whose other half fails today.

### 4a. Eligibility, inline-JS block (~`:809-823`)

Shape only — pass no index. These call `shouldCheckDocumentationPathReference`.

- [ ] Pair (R1/R4): `'review.py:555'` → `true` **and** `'review.py'` → `false`.
      The first half fails today.
- [ ] Pair (R5, traversal): `'a.b.py:1'` → `true` **and** `'a..b.py:1'` → `false`.
      Pins the separate `..` guard — the pattern's charset admits `..`, so
      without the guard the first half passing implies the second half failing.
- [ ] Pair (R5, extension): `'thing.py:1'` → `true` **and** `'thing.zzz:1'` → `false`.
- [ ] `'nope-xyz.py:9'` → `true`. **Eligibility is index-free**, so a name that
      resolves to nothing is still eligible; this is the assertion that stops a
      future refactor from folding the index into eligibility.

### 4b. Resolution, against the newly exported `resolveDocumentationReference`

Pass a literal index — no repository needed. This is where R2 and R3 live;
they cannot be asserted at eligibility, because a near-miss name is eligible by
shape exactly as `nope-xyz.py:9` is.

- [ ] R2 positive: index `{'sd-ai-command-pack-review.py': ['scripts/sd-ai-command-pack-review.py']}`,
      target `'review.py:9'` → resolves to `scripts/sd-ai-command-pack-review.py`.
- [ ] R2 closed-set negative: same index, target `'ai-command-pack-review.py:9'`
      (reachable only by substring) and `'review.py:9'` against an index keyed
      by an invented third prefix → both resolve to nothing.
- [ ] R3: index mapping one basename to several genuinely distinct paths →
      resolves (non-null) rather than being reported missing.
- [ ] Prefix skip: a target already starting with `sd-ai-command-pack-` is not
      double-prefixed.

### 4c. End-to-end (~`:4223-4306`)

**Fixture fix, blocking.** `make_repo` (`tests/install_test_support.py:210-220`)
runs `git init` and never stages; `run_install` (`:1284-1305`) copies files
without adding them. The existing reference tests at `:4174-4222` and
`:4223-4260` write docs and never commit. Resolution reads `git ls-files` — the
**index** — so in that fixture shape nothing bare ever resolves: both positive
tests below fail and the negative one passes vacuously.

- [ ] Each end-to-end case here must `git add` **and** `git commit` the target
      file *before* writing the citing document, then assert. Add a small helper
      (`self.run_git(root, "add", "-A")` + `commit`) rather than repeating it;
      state in the test docstring that staging is load-bearing, so a later
      cleanup does not remove it and turn the suite green-but-vacuous.

- [ ] Locator-form bare filename naming a **committed** file → returncode 0.
- [ ] Locator-form bare filename naming nothing → returncode 1 with
      `references missing path`.
- [ ] **Tracked-not-present:** a file that is committed and then deleted from the
      working tree still resolves, proving the index — not the filesystem — is
      the source. Fails if someone swaps `git ls-files` for a directory walk.
- [ ] Pack-shorthand: commit `scripts/sd-ai-command-pack-thing.py`, cite it as
      `` `thing.py:4` `` → returncode 0.
- [ ] Same reference with `[absent: <reason>]` → returncode 0 (the marker still
      governs the new class).
- [ ] **R7:** a bare filename naming nothing and carrying **no** line suffix →
      returncode 0. This is the property that keeps an unmeasured consumer
      corpus green, and it is the one criterion that would fail loudest if the
      locator restriction were ever dropped.
- [ ] **R8:** assert **one** `git ls-files` invocation for a document containing
      many bare references, not one per reference. Simplest discharge: put a
      counting shim on `PATH` ahead of real git, or assert the module-level
      cache is populated once. Left to inspection, this is the requirement a
      naive implementation most likely violates.

### 4d. Config wiring (R9, both directions)

The fail-closed test alone is satisfied whether or not `bareReferenceExtensions`
is ever added to the `loadConfig` key list — a key that is never merged also
never merges a malformed value. The positive test is what discharges the wiring.

- [ ] **Positive:** `.sd-ai-command-pack/review-preflight.json` with
      `{"bareReferenceExtensions": ["rst"]}`; a citation `` `notes.rst:3` ``
      naming nothing is now **reported**, where without the config entry it is
      declined. This fails if step 2's merge-list line is omitted.
- [ ] **Fail-closed:** the same key set to a non-array (e.g. `"py"`); the
      built-in set stays in force and an unresolvable locator-form reference is
      still reported. Guards a malformed value reading as "nothing to check" —
      the bash 3.2 lesson `08-18`'s PRD records under its requirement 5.

## 5. Re-measure

- [ ] Re-run both scripts under `research/`. `residualLocator` stays 0;
      at `09993578` `resolved` was 392 and `ambiguousDistinct` 212, with 107
      newly passing (95 resolved-bucket + 12 ambiguous-bucket) and 4 failing.
      Allow drift as tasks archive; a jump in `residualLocator` means the rule
      regressed.

## 6. Propagate

- [ ] `make generate` then `make sync`.

      Order is immaterial for this file and the house sequence is kept.
      `generate-plugin.py` does **not** read the root `scripts/` copy: its
      docstring line `scripts/<name> -> bin/<name>` is a target mapping, while
      `read_source` reads `root / source` from `manifest.json`, whose row for
      this file carries
      `source: templates/scripts/sd-ai-command-pack-review-preflight.mjs`.
      Both generators read `templates/`, so neither depends on the other's
      output. (Verified at `7f02caaa`; `read_module` at `:328` does read
      root-authored `installer/*` modules, but this task touches none.)
- [ ] `cmp` all four copies of the checker — byte-identical.
- [ ] `git diff --stat` shows no hand-edit outside `templates/`, `tests/`,
      `.trellis/tasks/`, and the four marker sites.

## 7. Release payload obligations

This edits `templates/scripts/*.mjs` — shipped payload — so CONTRIBUTING's
payload rules apply and the `Release payload gate` CI job runs
`run_pack_source_drift_gates` against the PR base. Skipping these fails
`CI Result`, not just a local check.

- [ ] Bump `manifest.json` `version` (minor: the gate checks a class of
      reference it did not check before, which is behaviour a consumer will
      notice).
- [ ] Matching top `CHANGELOG.md` heading. State the consumer-visible effect
      plainly: line-cited bare filenames are now validated; bare filenames
      without a line suffix are not.
- [ ] `make release-prep` — regenerates surfaces, self-syncs, refreshes
      `docs/fleet/candidate-validation.json`, then runs `make check`. Run this
      **after** all payload edits, never mid-cycle.

## 8. Gates

In order; each must pass before the next.

- [ ] `.venv/bin/python -m unittest tests.test_review_preflight` — fastest signal.
- [ ] `make test` — **zero** skips (`Makefile` fails the gate on `skipped=[1-9]`).
- [ ] `make lint`
- [ ] `make audit`
- [ ] `make full-check`
- [ ] `make release-prep` (step 7) — ends in `make check`; run last so no later
      edit invalidates its ledger.

## 9. Verification checks — named before the work

Each names the result that means failure.

| # | Check | Failure |
|---|---|---|
| V1 | `node scripts/sd-ai-command-pack-review-preflight.mjs; echo "exit=$?"` | anything but `exit=0`, or any `FAIL … references missing path …` |
| V2 | `measure-proposed.mjs` `residualLocator` | non-zero |
| V3 | Injected `no-such-file-zzz.py:1` in a guard doc | **not** reported — R1's failing half is dead |
| V4 | Pair: `shouldCheck…('review.py:9')` and `shouldCheck…('review.py')` | anything but `true` / `false`. The pair is the check — the `false` half alone passes today |
| V5 | Near-miss name passed to the **exported resolver** with an index that only a substring match could satisfy | resolves to non-null — the prefix set is not closed (R2). *Asserting this at eligibility proves nothing: a near-miss is eligible by shape, exactly as `nope-xyz.py:9` is* |
| V6 | Config pair: well-formed `{"bareReferenceExtensions":["rst"]}` widens; non-array leaves defaults in force | widening does not take effect (merge-list line omitted), or the malformed value opens the gate (R9) |
| V7 | `grep -cF '(?::~?\d+' templates/scripts/…-preflight.mjs` → expect **1**; `grep -c LINE_SUFFIX_PATTERN …` → expect **≥3** | ≥2 for the first: a second hand-written copy of the suffix regex survives. *The earlier `grep -n ':~\?\\d'` form was inert — verified 0 hits against the file that contains the regex at `:5056`* |
| V8 | `grep -n 'LINE_SUFFIX_PATTERN = /' …` | the literal carries a `g` flag — shared `lastIndex` makes the two callers alternate results |
| V9 | `grep -n 'export function resolveDocumentationReference' …` | no hit — R2/R3 remain untestable without a repository |
| V10 | `grep -n 'trackedBasenames' …` inside `shouldCheckDocumentationPathReference` | any hit — the index leaked into eligibility and R1's failing half is gone |
| V11 | **R7:** unresolvable bare name with no line suffix, end-to-end | returncode 1 — an unmeasured consumer corpus would go red |
| V12 | **R8:** count `git ls-files` invocations over a many-reference document | more than 1 — one subprocess per reference |
| V13 | `cmp` × 4 copies after `make generate && make sync` | any difference |
| V14 | `make test` | any failure, or any skip |
| V15 | `make release-prep` | manifest/changelog/ledger inconsistent with the payload |

V3, V5 and V10 are the ones that matter most: a rule that resolves everything
passes V1 trivially while checking nothing, and V10 is the specific refactor
that would silently cause it. V7 and V13 are the blast-radius checks — they
enumerate from the tree rather than re-reading the file just edited.

## Review gates

- **Before step 2** — the scope-confirmation gate at step 1b. It is placed there
  deliberately: after step 2 the decision is already propagated to four copies
  of the checker, so asking then is ceremonial.
- After step 5: report the before/after measurement table. A `residualLocator`
  above 0, or a `resolved` count far from ~392, means the rule is not the one
  designed and needs a second look before the payload bump.

## Rollback points

| After step | Rollback |
|---|---|
| 1 | Revert four marker edits. Inert prose; nothing depends on them. |
| 2-6 | Revert the checker commit. Markers may stay — they are inert without the rule. |
| 7-8 | `git revert` the merge commit. No migrations, no persistent state, no consumer-side writes. |
