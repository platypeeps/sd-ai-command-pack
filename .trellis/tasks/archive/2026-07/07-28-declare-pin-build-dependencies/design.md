# Design — declare and pin the build dependency toolchain

## Scope boundary

Three independent sub-changes that share only `pyproject.toml` and
`.github/workflows/tests.yml`. Land them as three commits in the order
A-109 → A-108 → A-110. Nothing in A-108 or A-110 depends on A-109's output,
but A-109 is the one that deletes a duplicate rather than adding a file, so
it is the cheapest place to establish the pattern.

The shipped runtime is pure stdlib in both languages. `review-preflight.mjs`
imports `node:child_process`, `node:crypto`, `node:fs`, `node:path`,
`node:url`, `node:util` and nothing else (`:2-7`), and there is **no
`package.json` in the repository**. So there is no Node dependency graph to
lock — only a Node *runtime version* to pin. Do not add a `package.json` as
part of A-108; it would create an npm surface this repo does not have.

All three findings are **P2 — unverified citations**. Everything below was
re-derived 2026-07-28. Two of the three requirements are misstated in the PRD.

## A-109 — Python floor. Smallest, and it deletes a copy. Land first.

### The floor is written five times, and the PRD's list misses the one in the file it edits

| site | form | machine-checked? |
|---|---|---|
| `pyproject.toml:2` | `target-version = "py310"` (ruff) | yes |
| `pyproject.toml:24` | `python_version = "3.10"` (mypy) | yes |
| `scripts/sd-ai-command-pack-toolchain.sh:54` | `if sys.version_info < (3, 10)` inside `PYTHON_PROBE_CODE` | yes |
| `scripts/sd-ai-command-pack-toolchain.sh:193` | `fail "selected Python is older than 3.10 … run 'make setup' with Python 3.13"` | no — operator prose |
| `.github/workflows/tests.yml:268` | `python-version: "3.10"` (matrix floor leg) | yes |

The PRD names `pyproject.toml:24`, `toolchain.sh:54`, `toolchain.sh:193`, "and
others". The two it elides are the two that matter most: `pyproject.toml:2`,
which lives three lines above the copy it does name, and `tests.yml:268`, which
is the only one CI actually exercises against a real interpreter.

`toolchain.sh:193` is a different kind of copy — it is a human-readable error
string that names both the floor (3.10) and the recommended install (3.13). It
cannot be derived from `requires-python` without changing what the operator
reads. Treat it as prose to keep in sync, not as a copy to eliminate.

### Only one copy is actually eliminable, and it was verified

Ruff infers `target-version` from `project.requires-python`. Confirmed by
execution against the pinned ruff (`requirements-dev.txt`, `ruff==0.15.21`):

```
requires-python >=3.10 -> linter.unresolved_target_version = 3.10
requires-python >=3.13 -> linter.unresolved_target_version = 3.13
requires-python >=3.8  -> linter.unresolved_target_version = 3.8
```

So adding `[project] requires-python = ">=3.10"` lets `pyproject.toml:2` be
**deleted**. Mypy has no equivalent inference — `python_version` at `:24` must
stay written out. Five copies become four, and the remaining three
machine-checked ones get a single source to be *checked against*, which is what
AC2 actually asks for ("derived from **or checked against** it").

### Adding `[project]` is not free

PEP 621 requires `name` and `version` (or `dynamic`) in a `[project]` table —
`requires-python` alone is not a valid table. Declaring `[project]` makes this
directory look like an installable distribution to every PEP 517 frontend,
including `uv`, which is the tool that produced the stray `uv.lock` in the
first place. Without a `[build-system]` table a frontend will guess a backend
and try to build a wheel of the repository root.

Mitigation: declare `[project]` with an explicit name/version and add
`[tool.uv] package = false` so `uv` treats the checkout as a non-package
project rather than something to build and install. Verify no `make` target,
CI step, or `pip install -r` path starts building the repo root after the
change — `pip install -r requirements-dev.txt` does not, but a bare
`pip install .` or `uv run` will now behave differently than it does today.

### `uv.lock`: the PRD's line number is off by one, and dropping the gitignore is the wrong fix

`.gitignore:175` is the comment; the pattern `uv.lock` is at **`.gitignore:176`**.
The file exists on disk, is 52 bytes, and carries `requires-python = ">=3.13"`
at `uv.lock:3`.

The contradiction the PRD flags is real, but it is a *symptom* of the missing
`[project]` table, not an independent defect: with no `requires-python` to
read, `uv` stamped the lock with the interpreter it happened to run under.
Once `[project] requires-python = ">=3.10"` exists, a regenerated lock says
`>=3.10` and the contradiction is gone.

Committing that lock is a different decision, and the design position is **do
not**. CI installs with `pip install -r requirements-dev.txt` at three sites
(`tests.yml:288`, `:336`, `:376`) plus `Makefile:11`. A committed `uv.lock`
would be a second dependency lock that nothing validates and that A-110's
compiled requirements would immediately contradict. Delete the stray file and
keep the ignore. If the ignore is dropped anyway, A-110's compiled files must
be treated as authoritative and the `uv.lock` regenerated in the same commit,
or the repo ships two locks that disagree.

## A-108 — Node. The `.mjs` floor assertion already exists.

### Correction: half of R1 is already implemented

The PRD asks to "assert `process.versions.node` against a floor inside the
`.mjs`". That assertion is present:

```js
// scripts/sd-ai-command-pack-review-preflight.mjs:20
const MIN_NODE_VERSION = { major: 16, minor: 9, label: '16.9.0' };
```

enforced at `:415-419` in the `isMainModule()` block:

```js
const unsupportedNode = unsupportedNodeVersionMessage(process.version);
if (unsupportedNode) {
  console.error(`error: ${unsupportedNode}`);
  process.exit(2);
}
```

It fails closed with exit 2. So the work is not "add an assertion" — it is
**raise the floor** from an EOL version and **stop CI from silently satisfying
it with whatever the runner image ships**. Writing this task as "add the
assertion" risks a diff that duplicates the check and leaves `16.9.0` in place.

`docs/SD_AI_COMMAND_PACK.md:810` ("The script requires Node 16.9 or newer") and
`full-check.sh:990` (`if ! have node; then` — presence only) are both accurately
cited. `full-check.sh` checking presence only is correct behavior for a local
convenience wrapper; the `.mjs` is the enforcement point and should stay so.

### Correction: "both jobs that run review-preflight.mjs" are not symmetric

| job | line | what it does |
|---|---|---|
| `ci-scope` (`tests.yml:17`) | `:204`, `:211` | **executes** the `.mjs` |
| `lint` (`tests.yml:316`) | `:350`, `:351` | `node --check` only — parses, never runs |

`lint` never reaches the version assertion. Its Node dependency is the parser,
which is a much weaker constraint. More importantly, `ci-scope` is the job that
computes CI scope for every event *and is the only job that runs on the
bookkeeping fast lane* — `unittest`, `lint`, and `security` are all gated on
`needs.ci-scope.outputs.mode == 'full'` (`:259`, `:317`, `:357`).

That makes the tradeoff explicit: adding `actions/setup-node` to `ci-scope`
inserts a new network-dependent step into the gating job on the fast lane,
where today the only external action is `actions/checkout`. Pin to the major
version already present on the runner image so the action resolves from the
tool cache rather than downloading; a version not on the image turns every fast
lane run into a download.

Every action in this workflow is SHA-pinned with a version comment
(`actions/checkout@9c091bb… # v7.0.0`, `actions/setup-python@ece7cb06… # v6.3.0`).
`setup-node` must follow the same form, or the `security` job's zizmor lane
will flag it.

### Floor choice

The current floor (16.9, EOL 2023-09) is below every Node version any current
runner image ships, so it is inert. Raise it to a supported LTS and pin CI to
the same major. Whatever is chosen, the number now lives in three places —
`MIN_NODE_VERSION` in `scripts/`, the same constant in
`templates/scripts/sd-ai-command-pack-review-preflight.mjs`, and the CI pin —
plus the prose at `docs/SD_AI_COMMAND_PACK.md:810`. There is no inference
mechanism here the way ruff gives one for Python; these stay hand-synced, and
the template-parity check is what catches drift between the first two.

## A-110 — Hash-pinned lockfiles. The hard one.

### Where dependencies are installed today

| site | file | cache key |
|---|---|---|
| `tests.yml:288` (`unittest`, 3 matrix legs) | `requirements-dev.txt` | `:285` |
| `tests.yml:336` (`lint`) | `requirements-dev.txt` | `:333` |
| `tests.yml:376` (`security`) | `requirements-security.txt` | `:373` |
| `Makefile:11` (local) | both | — |

Direct dependencies are already `==`-pinned: `coverage==7.15.1`,
`PyYAML==6.0.3`, `ruff==0.15.21`, `mypy==2.3.0`, `bandit==1.8.6`,
`zizmor==1.16.3`. So the PRD's "~11 transitives re-resolve unreviewed" is about
the transitive closure only — `mypy`'s `typing_extensions`/`mypy_extensions`,
`bandit`'s `PyYAML`/`rich`/`stevedore`/`pbr`, and so on. Direct-version flake is
not the exposure; transitive flake is.

### The constraint the PRD does not state: one compiled file cannot cover this matrix

The `unittest` job spans three environments (`tests.yml:266-272`):

```
ubuntu-latest  python 3.10
ubuntu-latest  python 3.13
macos-latest   python 3.13
```

`--require-hashes` is all-or-nothing: pip refuses the install if *any*
requirement in the file lacks a hash, and it refuses to install any
distribution whose hash is not listed. `coverage`, `ruff`, `mypy`, and
`bandit`'s `rich` dependency all ship platform- and interpreter-specific
wheels, so the hash set must cover linux-x86_64 and macos-arm64 for both cpy310
and cpy313. A `pip-compile --generate-hashes` run resolves for the interpreter
it runs under; environment-marked transitives that only apply below 3.11 will
be absent from a 3.13-resolved file and present in a 3.10-resolved one.

Two workable shapes:

- **Universal resolve.** `uv pip compile --universal --generate-hashes`
  produces one file whose markers and hashes span the whole matrix. One file,
  one Dependabot target, and it makes `uv` a build-time dependency of the repo
  — which is defensible given `uv` is already being run here incidentally.
- **Per-environment files.** `requirements-dev-py310.txt`,
  `requirements-dev-py313.txt`, keyed off `matrix.python-version`. No new tool,
  but it multiplies the files Dependabot must keep consistent and makes the
  macOS leg's divergence invisible unless a third file is added.

Pick one before writing any compile command. The failure mode of picking
neither is a hash file that passes on ubuntu/3.13 and fails the macOS leg with
an opaque `THESE PACKAGES DO NOT MATCH THE HASHES` error.

### The other constraint: `cache-dependency-path` must move with the file

`tests.yml:285`, `:333`, `:373` key the pip cache on the *current* filenames.
If the compiled output lands beside the hand-edited file under a new name and
those three paths are not repointed, CI keeps restoring a cache keyed on a file
that no longer drives the install. That is silent — the install still works, it
just stops being cached correctly, which reads as intermittent CI slowness.

### Dependabot

`.github/dependabot.yml` declares `package-ecosystem: pip` with
`directory: "/"`, which scans every requirements file at the root. Dependabot's
pip updater edits `.txt` files in place and does not understand a `.in` →
compiled `.txt` relationship. If both a hand-edited source and a compiled
output live at the root, Dependabot will open PRs against both and they will
disagree.

The PRD's "point Dependabot at the compiled files" is therefore not a
one-line config change — it means either the hand-edited files stop living at
the root (move the `.in` sources into a subdirectory Dependabot does not scan)
or the compiled files *become* `requirements-dev.txt` / `requirements-security.txt`
and there is no separate source file. The second is simpler and keeps every
existing install path and cache key working unchanged. It costs the readable
comment header currently at the top of both files.

## Compatibility

Nothing here crosses the installed-payload boundary. The shipped pack is
stdlib-only in both languages, so no consumer of a released version is affected
by any of the three sub-changes. This is build-time and CI-time exposure only —
the same reason the PRD correctly excludes A-111 (CVE scan) from this task.

The one consumer-visible artifact is the Node floor in
`templates/scripts/sd-ai-command-pack-review-preflight.mjs`, which is installed
into consumer repos. Raising it there raises the requirement on every repo that
installs the pack. That is intended, but it is a floor raise on other people's
machines and belongs in the changelog as such, not as an internal CI note.

## Rollout and rollback

Three commits: A-109, A-108, A-110.

- A-109 reverts cleanly. Its only irreversible action is deleting `uv.lock`,
  which is a regenerable local artifact.
- A-108 reverts cleanly in CI. The floor raise in `templates/` is the part that
  reaches consumers, so it needs a changelog entry and a version bump.
- A-110 reverts cleanly as a diff but not operationally: once `--require-hashes`
  is in place, any dependency change requires recompiling. Reverting mid-stream
  leaves a compiled file that nothing enforces.

Template parity applies to the `.mjs` edit; `make sync` after.

## Risk

Ranked:

1. **A-110's matrix coverage.** A single compiled file resolved under one
   interpreter will fail the 3.10 leg or the macOS leg. This is the most likely
   way the task ships broken, and the failure is a hash mismatch that reads as
   a supply-chain alarm rather than a resolution bug.
2. **A-110's Dependabot split-brain.** Two root-level files describing the same
   dependency set, both updated independently.
3. **A-109's `[project]` side effects.** A valid `[project]` table changes what
   PEP 517 frontends do in this checkout. Contained by `[tool.uv] package = false`
   and an explicit `[build-system]`, but it is a change in kind, not degree.
4. **A-108 adding a network step to the fast-lane gating job.** Real but small,
   and avoidable by pinning to the runner image's bundled major.
5. **A-108 duplicating an assertion that already exists.** Low consequence,
   but it is what happens if R1 is implemented as literally written.
