# Declare and pin the build dependency toolchain

## Goal

Make the build and CI toolchain reproducible and its version floors machine-readable, so a runner-side Node or transitive-dependency change stops arriving as unreviewed workflow instability.

## Requirements

- **Node (A-108):** add `actions/setup-node` with an explicit version to both jobs that run `review-preflight.mjs`, assert `process.versions.node` against a floor inside the `.mjs`, and document a supported-LTS floor. Today the only contract is prose naming Node 16.9 (EOL 2023-09) at docs/SD_AI_COMMAND_PACK.md:810, and full-check.sh:990 checks presence only.
- **Python floor (A-109):** add a minimal `[project]` table to `pyproject.toml` with `requires-python >=3.10`, and check the CI matrix against that single source instead of the five hand-maintained copies (pyproject.toml:24, toolchain.sh:54, toolchain.sh:193, and others).
- Drop the `uv.lock` gitignore at `.gitignore:175` — its `requires-python >=3.13` currently contradicts the 3.10 floor from behind a gitignore.
- **Lockfile (A-110):** commit hash-pinned compiled requirements for both `requirements-dev.txt` and `requirements-security.txt`, install with `--require-hashes`, and point Dependabot at the compiled files.

## Acceptance Criteria

- [ ] CI pins an explicit Node version and the `.mjs` fails closed below the floor.
- [ ] `pyproject.toml` declares `requires-python`, and the CI matrix is derived from or checked against it.
- [ ] CI installs with `--require-hashes` and a re-run resolves an identical tree.
- [ ] `make check` passes.

## Notes

- Source: `.trellis/audit/report-2026-07-28.md` — finding A-108 (P2 · M · Node undeclared), A-109 (P2 · S · no [project] table), A-110 (P2 · M · no lockfile).
- The shipped runtime is pure stdlib, so this is build-time exposure only — which is also why A-111 (no CVE scan) is lower priority and not bundled here.
- ~11 transitives currently re-resolve unreviewed on every CI run, which is a plausible contributor to the lint and type flakes that read as workflow instability.
- The three sub-changes are independent; A-109 is the smallest and unblocks the others.
- **Citation corrections, re-derived 2026-07-28.** All three findings are P2, so the audit's citations were unverified pointers.
  - **A-108: the `.mjs` floor assertion already exists.** `scripts/sd-ai-command-pack-review-preflight.mjs:20` declares `MIN_NODE_VERSION = { major: 16, minor: 9, label: '16.9.0' }` and `:415-419` enforces it with `process.exit(2)`. The work is **raising** an EOL floor and pinning CI, not adding a check. Implementing R1 as literally written produces a duplicate assertion and leaves `16.9.0` in place.
  - **A-108: the two jobs are not symmetric.** `ci-scope` (`tests.yml:17`) executes the `.mjs` at `:204`/`:211`; `lint` (`tests.yml:316`) only runs `node --check` at `:350-351`, so it parses and never reaches the assertion. `ci-scope` is also the only job that runs on the bookkeeping fast lane (`unittest`/`lint`/`security` are all gated on `mode == 'full'` at `:259`/`:317`/`:357`), so adding a network-dependent setup step there is a real tradeoff. `full-check.sh:990` is cited accurately.
  - **A-108: do not add a `package.json`.** `review-preflight.mjs` imports only `node:` builtins (`:2-7`) and the repo has no npm surface. There is no Node dependency graph to lock, only a runtime version to pin.
  - **A-109: the floor is written five times and the PRD's list misses two.** Measured: `pyproject.toml:2` (`target-version = "py310"`, ruff), `pyproject.toml:24` (mypy), `toolchain.sh:54` (`sys.version_info < (3, 10)`), `toolchain.sh:193` (operator prose), `tests.yml:268` (matrix floor leg). The two elided are the ruff copy three lines above the one named, and the CI matrix leg — the only copy exercised against a real interpreter.
  - **A-109: exactly one copy is eliminable, and it was verified.** Ruff 0.15.21 infers `target-version` from `project.requires-python` (executed: `>=3.10 -> linter.unresolved_target_version = 3.10`), so `pyproject.toml:2` can be deleted. Mypy has no such inference; `:24` must stay. AC2's "derived from **or checked against**" is satisfied for the rest by a test.
  - **A-109: `uv.lock` is at `.gitignore:176`, not `:175`** (`:175` is the comment). The `>=3.13` contradiction is a symptom of the missing `[project]` table, not an independent defect — once `requires-python` exists a regenerated lock says `>=3.10`. Dropping the ignore commits a second dependency lock that nothing in CI validates and that A-110's compiled files will contradict; `design.md` recommends deleting the stray file and keeping the ignore.
  - **A-109: `[project]` is not free.** PEP 621 requires `name` and `version`; `requires-python` alone is invalid. A `[project]` table makes the checkout look installable to every PEP 517 frontend. Needs `[build-system]` and `[tool.uv] package = false` in the same commit.
  - **A-110: direct dependencies are already `==`-pinned** (`coverage==7.15.1`, `PyYAML==6.0.3`, `ruff==0.15.21`, `mypy==2.3.0`, `bandit==1.8.6`, `zizmor==1.16.3`). The exposure is the transitive closure only.
- **A-110's real constraint is the matrix, and the PRD does not state it.** `--require-hashes` is all-or-nothing, and the `unittest` job spans ubuntu/3.10, ubuntu/3.13, and macos/3.13 (`tests.yml:266-272`) while `coverage`/`ruff`/`mypy`/`rich` ship platform- and interpreter-specific wheels. A single file compiled under one interpreter fails the other legs with `THESE PACKAGES DO NOT MATCH THE HASHES`, which reads as a supply-chain alarm rather than a resolution bug. Either resolve universally (`uv pip compile --universal`) or generate per-environment files; `design.md` requires the choice before any compile command is written.
- **"Point Dependabot at the compiled files" is not a one-line config change.** `.github/dependabot.yml` uses `directory: "/"`, which scans every root-level requirements file, and Dependabot's pip updater edits `.txt` in place with no `.in`-to-compiled model. Two root files for one dependency set get contradictory PRs. Simplest resolution: the compiled output *becomes* `requirements-dev.txt` / `requirements-security.txt`. Also repoint `cache-dependency-path` at `tests.yml:285`, `:333`, `:373` — that failure is silent.
- Created from the 2026-07-28 repo audit with explicit user consent via the `audit.followups` decision. Planning complete 2026-07-28: `design.md` and `implement.md` added.
