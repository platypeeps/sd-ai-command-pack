# Contributing

Use Homebrew Python 3.13 for the local virtual environment on macOS.

## Setup

```bash
make setup
```

This command creates `.venv`, installs the pinned requirements, and provisions the shared library.
It also copies the two requirements files into `.venv/sd-requirements/`, which records what the environment was provisioned from.
A linked worktree with no `.venv` borrows the main checkout's, and borrows it only while those copies match its own requirements files.
A worktree that moved a pin is refused by name and told to run `make setup VENV=.venv` for an environment of its own.
A `.venv` that is a symlink into another checkout is the same borrow under a local name, so it is compared too, on a proven mismatch only.
A symlinked environment that records nothing is used anyway, and `make` prints one note naming the checkout to re-provision (sd:1349).
`make setup` detaches a symlink at the path it provisions, and says what it detached; the environment the link pointed at is left alone.
It also removes the record before it changes anything and republishes it only after the last step, so a provision that failed leaves no record to match.
Because a missing record would otherwise mean both "provisioned before this was recorded" and "being built right now", `make setup` writes `.venv/sd-provisioning` before its first change and removes it after the record is published.
An environment carrying that file is refused by every path -- the borrow, the symlink and a real local `.venv` alike -- and the refusal names the checkout to run `make setup` in, which rewrites the marker and clears it on success.
`bin/sd_lib.py` and `hooks/pre-commit` read the same file and treat such an environment as absent.
A `.venv` the checkout carries as a real directory is its own environment and is never compared against the record.
The requirements files use `--require-hashes` locally and in CI.
To update a dependency, change its pin and run the compile command from that file's header:

```bash
uv pip compile --universal --generate-hashes --python-version 3.10 <file> -o <file>
```

Remove a conflicting transitive pin before recompiling. Do not edit hashes by hand.

## Local Checks

```bash
make test
make lint
make audit
make docs-lint
make check
```

`make check` runs `lint`, `audit`, `docs-lint`, then `test`. It stops at the first failure.
Run the full command before each push.

During development, select tests for changed paths:

```bash
make check CHANGED="$(git diff --name-only origin/main) $(git ls-files --others --exclude-standard)"
```

Only a command-line `CHANGED` value selects this mode.
The test runner ignores this mode when `CI` or `GITHUB_ACTIONS` has a non-empty value.
Do not use this mode for paths containing whitespace.
The selector splits the list on whitespace and can miss the intended tests.

The selector runs matching modules and an always-run set of checks.
It cannot detect dependencies that tests do not name.
An empty list, unknown path, or broad change selects the full suite.
Read `.github/scripts/select-tests.py` for the selection rules.

A narrowed run skips coverage combination and the installer coverage gate, then exits 2.
The other three checks still run over their full scope.
A narrowed run does not replace the full check before a push.

`.github/scripts/run-tests.sh` uses every available CPU in CI.
Local runs reserve one CPU when multiple CPUs are available.
Set `TEST_WORKERS` to override either default.
Each shard reports its name, elapsed seconds, and exit status.

Ruff checks `bin/` and `tests/`. Mypy checks `bin/`.
The Makefile owns both path inventories. CI reads those inventories.
Missing optional ShellCheck, Bandit, or Zizmor tools produce warnings.
Use `STRICT=1 make check` to make missing tools fail.
This also requires a bash 3.2 interpreter.

The local lint parses tracked `*.sh` files through `.github/scripts/check-bash32-syntax.sh`.
The script enumerates its inputs from git.
Set `SD_AI_COMMAND_PACK_BASH32` to override its space-separated interpreter candidates.
Without bash 3.2, the script warns and passes unless `STRICT=1`.
CI does not run this syntax check.

Installer coverage requires **100% line and branch coverage** over `bin/sd_install.py`.
The gate also checks file and statement floors.
Lower a floor only in the pull request that reduces the measured implementation.

## Main Branch Policy

Every change to `main` requires a pull request.
Branch protection on `main` requires a pull request, the strict `lint` and `unittest` checks, and enforce_admins.
It requires no approving review, because the sole maintainer cannot approve their own pull request.
[.github/sd-status.json](.github/sd-status.json) records that accepted `reviews` gap, its reason, and the condition that ends it.
Run `bin/sd-status` to inspect live protection.

Use the pack's ship workflow for publication, review and merge.
`sd-ship merge` checks the protection object, the exact-head checks and the review findings before it merges.
Keep the required contexts equal to the contexts that the current workflows produce.

The matrix in `.github/workflows/tests.yml` currently runs Ubuntu with Python 3.13 only.
CI does not verify other Python versions or macOS behaviour.
**The macOS CI leg remains disabled** (R11-D4).
The maintainer restores it manually at the rollout's end. The restoration has no scheduled date.
The local bash syntax check does not replace macOS CI.
Treat local results as evidence from the tested machine only.

## Payload Rules

- `v0.72.0` is the terminal release. Do not add release tags or `CHANGELOG.md` headings.
- `skills/sd-*/SKILL.md` holds the payload. Edit that source directly.
- `python3 bin/sd_install.py --user` renders the skills during installation. The repository has no generated platform copies.
- `python3 bin/sd_install.py --status` reports the serving checkout's commit. Use `--pull` to update that checkout.

## Repository Conventions

### Documentation and decisions

Use Claude's STE-Concise style for new and revised prose:

- Use active voice and simple tenses.
- Limit each sentence to 20 words and one idea.
- Remove filler. Preserve exact identifiers, paths, commands, and quoted evidence.

Keep one authoritative statement of each current rule or decision. Link to it from other documents.
Governing documents contain current instructions and, when needed, one sentence explaining the reason.
Put dated evidence in the existing work item's history. Preserve original review findings and their dispositions there.
Update the current status in place. Record a history entry only when the decision, scope, or evidence materially changes.
Do not append repeated corrections or copy decision discussions between documents.
Git history preserves earlier wording.

### Citations

Cite code declarations by symbol: `source:bin/sd-docs-lint::check_pr_link`.
The citation check requires one matching declaration.
For a file without a supported declaration, name the file in prose.
Use `path:line` only for markdown targets. Keep historical citations tied to their original version.

Preview citation repairs before applying them:

```bash
python3 tests/test_doc_citations.py --repoint
python3 tests/test_doc_citations.py --repoint --apply
```

The repair tool matches anchored text. It refuses ambiguous or missing matches.
Do not replace line numbers without checking their targets.

#### The optional claim-support reading

Rule 6 compares recorded text against the cited line.
It cannot tell whether that passage still supports the sentence citing it.

A second reading asks a model that question, and it is taken wherever it can
be:

```bash
make docs-lint
```

It needs `jev` on `PATH`. `jev` ships in a private companion repository, so
most checkouts do not have it, and a run without it is a run without this
pass — silently, because announcing a missing optional companion would put a
line in every pull request here forever. The pass prints notes only. It never
fails a run and never changes an exit code.

Taking the reading sends the citing sentence and the cited passage to a
third-party model. Both are capped, and neither carries a path, an item name,
or the citation marker.

**Read `docs/work` there as "the checkout you are standing in", not "this
one".** `sd-docs-lint` picks its repository from the working directory, and
the pass walks every recorded citation under that repository's `docs/work` —
not only the ones a change touched. So a private consumer repo that runs this
binary from its own root takes the reading over its own prose. `make
docs-lint` above is the command that names the pass; the ones that will
actually surprise you are **`make check`**, which wires it into the pre-merge
gate, and **`sd-ship`**, which lints at delivery. The payload is the same
either way; what the flip changed is which repositories take the reading and
how often.

Switch it off for a checkout whose `docs/work` must not leave the machine:

```bash
JEV_SD_DOCS_LINT=0 make check    # or export it once, for every invocation
```

`0`, `off`, `false`, `no` and `disabled` all switch it off, in any case.
Anything else leaves it on, including the `1` this used to require: a typo is
not an outage. The switch only ever subtracts — it cannot make a reading
happen that `jev` itself declines, so a machine with no key behaves exactly
like one with the switch off.

#### The optional review-tier reading

`bin/sd-review` takes a second reading of the same shape, and it was
undocumented here until review said so. `sd_route.route` decides the tier and
keeps the decision; the reading is a second opinion over a diff shape the
policy's globs cannot see, and it is taken wherever `jev` says it can answer.

What leaves the machine: the tier names, the repository-relative paths the
change touches (capped, then a count), the number of lines it moves, and the
routing reason `sd_route` composed. **No file contents, no diff, no code**, and
no absolute path, repository name, branch, author or commit message.

**The tier names are the running checkout's, not this one's — same rule as
above, and it bites harder here.** `load_policy` reads the policy out of the
repository the command runs in, and `sd-review` hands that policy's
`tier_order` straight to the reading. The four standard tiers carry a fixed
description; **a tier a repository invented is sent as a bare name, with
nothing to say what it means.** So a private repo that declares a tier called
`embargo-legal` sends that string to a third-party model, and the name is the
whole of what arrives. Name your tiers as though they leave the machine,
because they do.

```bash
JEV_SD_REVIEW=0 sd-review --scope branch    # or export it once
```

The same vocabulary and the same subtract-only rule apply. **It prints no
*note*, which is not the same as changing nothing**: on the path where the
reading works, the result object gains a `jev` key, the routing reason gains a
clause, and the tier itself may move — that is the point of taking it. The
note naming this switch appears only when the reading was attempted and
failed.

### Permissions

Put machine-specific rules in ignored `.claude/settings.local.json`.
Put repository workflow rules in tracked `.claude/settings.json`.
Do not grant arbitrary execution or generic file readers through Bash permissions.
Use scoped commands and the harness's file tools.

`tests/test_permission_allowlist.py` derives the tracked allowlist from three inventories:

- Public Makefile `.PHONY` targets.
- The README installer table.
- GitHub MCP tools named by shipped skills.

Change the relevant inventory instead of editing grants by hand.
The derivation excludes modes with path placeholders and effects that begin with `Remove` or `Delete`.
Only README surfaces marked `Read-only:` receive wildcards. Other grants match exact commands.
Every granted path must exist.
Executable Python entrypoints require both direct and `python3` invocation forms.
An added `./` prefix can change permission matching.

Edit `.gitignore` directly. No generator maintains it.

## Specs To Read First

Read the [current architecture](docs/current-architecture.md) before changing the installer or command set.
That page links the historical design and implementation records.

Some surviving `docs/spec/**` pages describe the retired installer model.
Read each page's dated notice before using it.
The Machine-Scope Installer section's final location remains undecided.
Its current location is `docs/spec/backend/manifest-and-filesystem.md`.

Keep an `index.md` that links every surviving page in each spec directory.
Spec changes remain subject to review through `never_skip`.
The `sd-spec` skill maintains specs during shipping.
Keep `docs/fleet/README.md` as the historical link target.
Preserve the marked historical review quotations in `docs/review-learnings.md`.
