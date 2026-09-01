# Contributing

Use Homebrew Python 3.13 on macOS for the local virtualenv; Apple/Xcode Python
often misses dev dependencies or writes caches into protected locations, and
some security scanners can lag newer Python AST changes.

## Setup

```bash
make setup
bash scripts/sd-ai-command-pack-toolchain.sh doctor
```

`make setup` creates `.venv` and installs `requirements-dev.txt` and
`requirements-security.txt`.

Both requirements files are hash-pinned compiled resolutions, installed with
`--require-hashes` locally and in CI so the transitive closure cannot drift
between runs. To bump a dependency, edit its `==` pin and rerun the compile
command recorded in the file's header
(`uv pip compile --universal --generate-hashes --python-version 3.10 <file> -o <file>`);
if the bump conflicts with a stale transitive pin, delete that transitive's
block and recompile. Do not hand-edit hashes. Dependabot updates these files
with matching hashes on its own.

## Local Checks

```bash
make test
make lint
make audit
make check
```

`make check` is exactly `test lint audit`, which is exactly what CI runs.
`make full-check` and `make generate` are gone: the first wrapped a shipped
script that no longer exists, and the second regenerated committed per-platform
copies that no longer exist either — the installer renders from `skills/` at
install time, so there is nothing to keep in sync.

`make check` runs coverage-gated tests, Ruff and mypy over `bin/`, optional
ShellCheck, and optional Bandit/Zizmor. Missing optional tools print warnings
instead of blocking Python-only contributor setups. Run `STRICT=1 make lint`
to turn those missing-tool skips into hard errors for parity with CI.

`make lint` also parses every tracked shell script with bash 3.2 — the
interpreter macOS keeps at `/bin/bash` — through
`.github/scripts/check-bash32-syntax.sh`, so syntax that only bash 3.2 rejects
fails before the push. That gate matters more while the macOS CI leg is
dropped (R11-D4): it is now the only automated check that runs anything
against the interpreter macOS actually ships.

Its rationale narrowed at step 3e, and the narrowing is worth stating rather
than leaving the old reason in place. The gate existed because the pack shipped
shell scripts that ran on whatever bash a consumer's macOS had. Nothing is
shipped now. What it still protects is this repository's own three scripts under
`.github/scripts/`, which `make check` runs through `/bin/bash` locally — a real
subject, just a much smaller one. The script
list is enumerated from `git ls-files` at run time, never maintained inside the
gate. A platform with no bash 3.2 (any Linux) prints
`warning: no bash 3.2 interpreter found` and passes; `STRICT=1` turns that
missing interpreter into a failure, and `SD_AI_COMMAND_PACK_BASH32` overrides
the interpreter search with a space-separated candidate list.

Installer coverage is gated at **100% line and branch** over
`bin/sd_install.py`, and the gate enumerates its subject from git rather than
matching a glob. A glob drifts in two directions and reports green through both:
a new module lands outside the pattern unmeasured, or code is deleted and the
same 100% then certifies less. Enumeration closes the first; a declared floor
closes the second.

Which floor does that work changed at step 3e, and the reason is recorded in the
gate itself. Until 3e the installer was `install.py` plus seventeen `installer/`
modules, so a file count caught a module vanishing. The machine-scope installer
is one file, and "at least one file" catches nothing — the surface could be
gutted to a stub and still pass. So the floor is now a statement count, with
`MIN_FILES` kept as the cheaper check that fails readably if the file is deleted
outright. Lower either only in the pull request that legitimately shrinks the
surface, where a reviewer can see the scope change.

Three coverage lanes were retired at the same step, each because its subject
stopped existing rather than because the bar was lowered: the shipped-script
aggregate and per-file floors, the shipped-script documentation gate, and the
kcov `Shell coverage` job. That last one is the only retirement that touched
branch protection, since it was a required context; the workflow change and the
protection change were sequenced together (R11-D6). Nothing measured by those
lanes is now unmeasured — the payload they measured is deleted.

Ruff covers pack-owned Python in `bin/` and `tests/`; mypy covers `bin/`. The
authoritative path lists live in the Makefile as `LINT_RUFF_PATHS` and
`LINT_MYPY_PATHS`, and CI reads them with `make -s lint-ruff-paths` rather than
restating them — the workflow carried its own hand-copied list until 2026-08-29
and had silently omitted every `bin/` file.

## Main Branch Policy

Every change to `main` goes through a pull request. Merge authority is GitHub
branch protection; there is no local pre-push hook, no server-side path policy,
and no bookkeeping fast lane. A pull-request head and a push to `main` run the
same four unconditional jobs — the `unittest` matrix, `lint`, `bash 3.2 syntax`,
and `security` — producing five contexts. Contexts are named
by a job's `name:`, not its YAML key, so the bash lane is required as
`bash 3.2 syntax` and never as `bash32`; requiring the key would pin a context
that never reports and block every pull request. Three changes moved this set
inside two days. The macOS leg was dropped for the duration of the
artifacts-as-product rollout (R11-D4; restored by hand at the end of the
rollout, no date); `bash32` was added because the bash 3.2 syntax gate turned
out never to have run in CI at all (R11-D5); and `Shell coverage` was removed at
step 3e, because the shipped shell it measured was deleted (R11-D6).

That sentence is only true while protection is actually enforcing, so state the
condition rather than the conclusion. Protection here is enforcing as of
2026-08-30: `enforce_admins: true`, `strict: true`, and the five required
contexts match the five the workflow produces. No dimension is currently out
of step.

One was, briefly: `bash 3.2 syntax` began reporting when R11-D5 merged but was
not added to the protection object until 2026-08-30, so for a few hours a red
result there did not block a merge. Adding it is also what flipped the
then-open #607 from CLEAN to BLOCKED, until that branch carried the workflow
producing the context — the required-context ordering trap in its additive
direction, the mirror of the removal case R11-D4 sequenced around. Both are
recorded because the trap has now been hit in both directions within a day.

That window is closed, and this paragraph is not what establishes it:
`sd-status` reads the live protection object and reports whatever gaps exist at
the time it runs, rather than trusting anything written here. Which is the
point — a dated claim in a document is the thing most likely to be wrong, as
the sentence this one replaces was.

`enforce_admins` was deliberately left off in earlier work
(see `docs/work/archive/2026-07/2026-07-09-main-push-server-side-guard/`,
which explicitly declined to enable it, and `docs/work/archive/2026-07/2026-07-03-chore-push-scope-guard/`,
which records it being enabled and disabled again the same day). That decision is
reversed: an exemption for the only account that merges here made the doctrine
prose, not authority — a direct push to `main` landed on 2026-08-29 precisely
because nothing server-side stopped it. If protection is ever relaxed again, this
section is wrong until it is rewritten; `sd-status` reads the live protection
object and reports the gap instead of trusting this paragraph.

CI intentionally tests the supported Python floor (3.10) and current project
runtime (3.13). Intermediate 3.11/3.12 jobs would duplicate the same
compatibility interval while increasing Actions cost; add one only when a
version-specific defect provides evidence that endpoint coverage is
insufficient.

The macOS 3.13 leg is **temporarily dropped** (R11-D4, 2026-08-29). It ran
12m18s on every pull request, and GitHub bills macOS runners at ten times the
Linux rate, so the rollout was paying that on roughly fifteen more pull
requests. It is a cost saving, not a latency one: the run is bounded by
`Shell coverage` at 13m40s, so wall-clock time is unchanged. What is lost
is named rather than waved away: with the leg gone, **no CI job runs on macOS
at all**, so macOS-only Python behaviour, filesystem case-insensitivity, and
platform-specific path handling are unverified in CI until it returns. The only
remaining macOS coverage is the maintainer's own `make check` before a push --
one machine, not a gate.

The leg was originally due back at step 7. It is not: the restore is now a
manual step the maintainer triggers at the end of the rollout (R11-D4
amendment, 2026-08-31), because steps 8 through 11 still land pull requests and
restoring at step 7 would pay the ten-times runner cost on every one of them.
The consequence is stated rather than buried: the dated deadline was what made
this removal falsifiable, and "when the rollout is done" is not a date. This
paragraph is the record instead, and it has no expiry -- it stands, in the
present tense, until a macOS job actually reports.

An earlier draft of this paragraph claimed the bash 3.2 syntax gate in `lint`
covered macOS in CI. It did not -- no CI job invoked `check-bash32-syntax.sh`
at all, and that gate had only ever run in a local `make lint`. Finding that
gap is what prompted closing it: the **`bash32`** job now builds bash 3.2 from
source and runs the gate under `STRICT=1`.

That covers bash 3.2 *syntax*, which is a real slice of macOS compatibility and
not the whole of it. macOS-only Python behaviour, filesystem
case-insensitivity, and platform path handling stay unverified in CI until the
macOS leg is restored.

## Payload Rules

- 0.72.0 (tag `v0.72.0`) is the terminal release. There are no further
  releases: do not add a `CHANGELOG.md` heading and do not create a tag. The
  release preparation command, the candidate ledger, the payload gate, and the
  auto-tag job were deleted with it, and `manifest.json` itself was deleted at
  step 3e.
- `skills/sd-*/SKILL.md` is the payload, and there is exactly one copy of it.
  There are no per-platform mirrors to keep in sync and nothing to re-render
  after an edit: `bin/sd_install.py --user` renders from `skills/` at install time, and
  a machine picks up an edit the next time it runs.
- There is no versioning scheme any more, because there is nothing to version.
  A machine is at whatever commit its serving checkout is at, which
  `bin/sd_install.py --status` reports, and `--pull` moves forward. The 0.x minor/patch
  rules that stood here governed a release train that no longer exists.

## Repository Conventions

- Put machine-specific Claude permissions in the ignored
  `.claude/settings.local.json`, not tracked `.claude/settings.json`.
- The managed block in `.gitignore` is no longer generated by anything, and
  nothing reads its markers. They were kept for `migrate-trellis`, which was
  deleted at step 7 having finished its job — but `grep '\.gitignore'` over
  that file returned nothing even before the deletion: it stripped marker
  pairs from `AGENTS.md`, never from `.gitignore`. The markers are vestigial.
  They are left in place rather than removed here because
  `docs/spec/backend/manifest-and-filesystem.md` still specifies them, and
  that whole spec tree is known-stale (see below) — one correction, not two.
  Edit that section by hand like any other.

## Specs To Read First

The `docs/spec/**` tree still describes the pre-3e installer, manifest, and
adapter model in several places, and `docs/FLEET_ROLLOUT.md` with `docs/fleet/**`
still describes a release train and a fleet of consumer checkouts that no longer
exist. Those pages are stale by construction — step 3e deleted what they describe
— and they are corrected as the steps that own them arrive (fleet residue at
steps 4 and 7) rather than rewritten speculatively here. Deleting them in 3e was
considered and rejected: a deletion widened because the tree is already open is
how a reviewable pull request stops being one. Read
`docs/work/2026-08-29-artifacts-as-product/` for what is actually true now.

That deferral did not hold, and the paragraph above is left standing as the
record of the plan rather than rewritten to match what happened. Steps 4 and 7
both closed without reaching these trees — step 7's checklist row said "triage
survivors" and the step closed on 2026-09-01 with the row unaddressed — so the
triage ran on **2026-09-01** as its own pass instead. Every page under
`docs/spec/**` and `docs/FLEET_ROLLOUT.md` now opens with a dated notice naming
what was deleted, when, and which record explains it; `docs/fleet/` carries the
same notice in a new `README.md`, because JSON takes no header. The notices
supersede: nothing below them was edited.

Deletion was **not** part of that pass. 7,839 lines of specification is a
content decision for the maintainer, so the pass produced a per-file
disposition with evidence — keep, stale-notice, or delete — and left the delete
column as a recommendation. It is in the step 7 entry of
`docs/work/2026-08-29-artifacts-as-product/implement.md`.

One thing to know before acting on that recommendation: `docs/spec/**` is not
orphan text, even where its content is. `bin/sd-docs-lint` rule 4 enumerates
the tree at run time and fails any spec directory that holds pages without an
`index.md` linking each of them; `.github/sd-review.json` and `bin/sd_route.py`
both carry `docs/spec/**` in `never_skip`, so a change there is never routed
past review; and `skills/sd-spec/SKILL.md` writes into it as the second stage
of `sd-ship`. Rule 4 tolerates an index that links a page which is gone, so
deleting a page is safe — but a directory has to leave with its index, not
before it.

**The recommendation was executed on 2026-09-02, and the two paragraphs above
stand as written.** The maintainer took the delete column. Eighteen files and
9,324 lines went: `docs/spec/frontend/` and `docs/spec/tooling/` left whole,
index included; three of `docs/spec/backend/`'s seven pages went while three
stayed; and `docs/FLEET_ROLLOUT.md`, `docs/fleet/consumers.json` and
`docs/fleet/surface-partition.json` went with them. `docs/spec/**` is now seven
files in two directories.

Two files were rewritten rather than deleted, and each for a stated reason.
`docs/spec/backend/index.md` had to survive because rule 4 requires an index
wherever pages remain, so it was cut down to an index of the three survivors
plus a record of what left. `docs/fleet/README.md` was written the day before
to carry a notice for two JSON files that could not hold one; with both files
gone it is a tombstone instead, kept at its path so links into `docs/fleet/`
from this file, from `CHANGELOG.md`, and from archived work items still answer
rather than 404.

What did **not** change: the six stale-notice pages are untouched, including
`docs/spec/backend/manifest-and-filesystem.md`, whose Trellis-gitignore section
is still why `.gitignore` keeps its vestigial `SD-AI-COMMAND-PACK` markers. The
two open questions the triage recorded against that page — the gitignore markers
and whether its Machine-Scope Installer section belongs in `docs/spec/` or
`docs/work/archive/` — are still open. `docs/review-learnings.md` still cites
`docs/FLEET_ROLLOUT.md` in three entries marked **historical**; those are
quotations from PR #184 and #188 review comments and were true when written, so
they stay.
