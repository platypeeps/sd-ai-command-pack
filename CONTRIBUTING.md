# Contributing

Use Homebrew Python 3.13 for the local virtual environment on macOS.

## Setup

```bash
make setup
```

This command creates `.venv`, installs the pinned requirements, and provisions the shared library.
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
The repository has an accepted branch-protection exception in [.github/sd-status.json](.github/sd-status.json).
That file owns the reason and the condition that ends the exception.
Run `bin/sd-status` to inspect live protection.

Use the pack's ship workflow for publication and review.
While protection is absent, `sd-ship merge` refuses the missing protection object.
Under the recorded exception, the maintainer reads every check before using `gh pr merge`.
No server rule or local pre-push hook enforces this check.
When protection returns, require the contexts that the current workflows produce.

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

An optional second reading asks a model that question:

```bash
JEV_SD_DOCS_LINT=1 make docs-lint
```

It needs `jev` on `PATH`. `jev` ships in a private companion repository, so
most checkouts do not have it, and a run without it is a run without this
pass. The pass prints notes only. It never fails a run and never changes an
exit code. A run that leaves the opt-in unset prints nothing about it at all.

Enabling it sends the citing sentence and the cited passage to a third-party
service. Both are capped, and neither carries a path, an item name, or the
citation marker. Leave the opt-in unset when `docs/work` is private.

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
