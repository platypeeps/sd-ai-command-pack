# Implementation — declare and pin the build dependency toolchain

Three commits, in this order: A-109, A-108, A-110. They do not couple. Do not
batch them.

## Order

### Commit 1 — A-109, Python floor

1. Add a `[project]` table to `pyproject.toml`. `requires-python` alone is not
   valid PEP 621 — `name` and `version` (or `dynamic`) are required. Add
   `[build-system]` and `[tool.uv] package = false` in the same commit so no
   frontend starts trying to build a wheel of the repository root.

2. Delete `pyproject.toml:2` (`target-version = "py310"`). Ruff 0.15.21 infers
   it. Verified by execution:

   ```
   requires-python >=3.10 -> linter.unresolved_target_version = 3.10
   requires-python >=3.13 -> linter.unresolved_target_version = 3.13
   ```

   **Gate:** re-run the check after deleting the line. If ruff's inference is
   not active for any reason, the deletion silently relaxes lint to ruff's
   default target and nothing fails.

3. Keep `pyproject.toml:24` (`python_version = "3.10"`). Mypy has no
   `requires-python` inference. Deleting it drops the mypy floor to mypy's own
   default.

4. Add a check that `tests.yml:268`'s matrix floor leg matches
   `requires-python`. AC2 accepts "derived from **or** checked against", so a
   test is sufficient — no workflow templating needed. `toolchain.sh:54`
   (`sys.version_info < (3, 10)`) should be covered by the same check.

5. Leave `toolchain.sh:193` as prose but keep it in sync. It names both the
   floor and the recommended install version in operator-facing text; it is not
   a machine copy and should not be generated.

6. Delete the stray `uv.lock` (52 bytes, `requires-python = ">=3.13"` at
   `uv.lock:3`) and **keep** the `.gitignore` entry.

   **Gate:** the PRD says drop the gitignore. The line is `.gitignore:176`, not
   `:175` — `:175` is the comment above it. Dropping the ignore commits a
   second dependency lock that nothing in CI validates and that commit 3's
   compiled requirements will contradict. If the ignore is dropped anyway,
   regenerate `uv.lock` in the same commit as commit 3 and record which lock is
   authoritative.

### Commit 2 — A-108, Node

7. **Do not add the `.mjs` version assertion. It already exists.**
   `MIN_NODE_VERSION = { major: 16, minor: 9, label: '16.9.0' }` at
   `scripts/sd-ai-command-pack-review-preflight.mjs:20`, enforced at `:415-419`
   via `unsupportedNodeVersionMessage(process.version)` with `process.exit(2)`.
   The work is raising the floor, not adding the check.

8. Raise `MIN_NODE_VERSION` to a supported LTS in both copies:
   `scripts/` and `templates/scripts/`. Update the prose at
   `docs/SD_AI_COMMAND_PACK.md:810` ("requires Node 16.9 or newer").

   **Gate:** the `templates/` copy installs into consumer repos. This is a
   floor raise on other people's machines. Changelog entry must say so, and it
   needs a version bump — not an internal CI note.

9. Add `actions/setup-node` to `ci-scope` (`tests.yml:17`) and `lint`
   (`tests.yml:316`). SHA-pin with a version comment, matching the existing
   form:

   ```
   uses: actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0 # v7.0.0
   uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6.3.0
   ```

   An unpinned `uses:` will be flagged by zizmor in the `security` job.

10. Pin to a major already present on the runner image. `ci-scope` is the
    gating job and the **only** job that runs on the bookkeeping fast lane —
    `unittest`, `lint`, and `security` are all gated on
    `needs.ci-scope.outputs.mode == 'full'` (`:259`, `:317`, `:357`). A version
    not in the tool cache turns every fast-lane run into a download on the one
    job that must not become flaky.

11. Do not add a `package.json`. `review-preflight.mjs` imports only `node:`
    builtins (`:2-7`) and the repository has no npm surface. There is no Node
    dependency graph to lock, only a runtime version to pin.

12. Leave `full-check.sh:990` (`if ! have node; then`) as a presence check. It
    is a local convenience wrapper; the `.mjs` is the enforcement point.

    Note `lint` only runs `node --check` (`:350-351`) — it parses, never
    executes, so it never reaches the assertion. Both jobs need Node; only one
    is enforcing anything.

### Commit 3 — A-110, hash-pinned lockfiles

13. **Decide the matrix shape before writing any compile command.** The
    `unittest` job spans three environments (`tests.yml:266-272`):

    ```
    ubuntu-latest  python 3.10
    ubuntu-latest  python 3.13
    macos-latest   python 3.13
    ```

    `--require-hashes` refuses the install if any requirement lacks a hash and
    refuses any distribution whose hash is not listed. `coverage`, `ruff`,
    `mypy`, and `bandit`'s `rich` all ship platform- and interpreter-specific
    wheels. Two options:

    - `uv pip compile --universal --generate-hashes` — one file spanning the
      matrix; makes `uv` a build-time dependency.
    - per-environment files keyed off `matrix.python-version` — no new tool,
      more files to keep consistent, and the macOS divergence stays invisible
      without a third file.

    **Gate:** a file resolved under a single interpreter passes ubuntu/3.13 and
    fails the 3.10 or macOS leg with `THESE PACKAGES DO NOT MATCH THE HASHES`.
    That error reads as a supply-chain alarm, not a resolution bug. Decide, then
    prove on all three legs before merging.

14. **Decide the file layout.** `.github/dependabot.yml` declares
    `package-ecosystem: pip` with `directory: "/"`, which scans every
    root-level requirements file. Dependabot edits `.txt` in place and does not
    model a `.in` → compiled `.txt` relationship. Two root files describing the
    same dependency set get independent PRs that disagree.

    Recommended: let the compiled output **be** `requirements-dev.txt` and
    `requirements-security.txt`. Every install path and cache key keeps working
    unchanged. Cost is the readable comment header currently at the top of both
    files.

15. Add `--require-hashes` to all four install sites:

    ```
    tests.yml:288   unittest (3 matrix legs)   requirements-dev.txt
    tests.yml:336   lint                       requirements-dev.txt
    tests.yml:376   security                   requirements-security.txt
    Makefile:11     local setup                both
    ```

16. Repoint `cache-dependency-path` if the filenames change: `tests.yml:285`,
    `:333`, `:373`.

    **Gate:** this failure is silent. A stale cache key still installs
    correctly, it just stops caching — which surfaces as intermittent CI
    slowness, not a failure.

17. Direct dependencies are already `==`-pinned (`coverage==7.15.1`,
    `PyYAML==6.0.3`, `ruff==0.15.21`, `mypy==2.3.0`, `bandit==1.8.6`,
    `zizmor==1.16.3`). The exposure this commit closes is the transitive
    closure only. Do not describe it as pinning direct versions — that is
    already true.

### Every commit

18. `make sync` after any `templates/` edit (commit 2).

19. Changelog + version. Commit 2's entry is consumer-facing.

## Validation

AC2 — `requires-python` declared and the matrix checked against it (commit 1):

```bash
python3 -c "import tomllib,pathlib;print(tomllib.loads(pathlib.Path('pyproject.toml').read_text())['project']['requires-python'])"
```

Ruff inference still active after deleting `target-version` (commit 1, step 2):

```bash
.venv/bin/ruff check --show-settings --no-cache pyproject.toml 2>/dev/null | grep target_version
```

Expect `3.10`. Anything else means the deletion relaxed the lint floor.

AC1 — the `.mjs` fails closed below the floor (commit 2). The assertion already
exists, so this tests the raise, not the addition:

```bash
node -e "process.version='v14.0.0'" 2>/dev/null; node scripts/sd-ai-command-pack-review-preflight.mjs --help; echo "exit=$?"
```

Exit 2 with `error: …` on an under-floor interpreter. Testing this properly
needs an actual old Node; a version-string stub does not exercise
`process.version`. If no old Node is available, unit-test
`unsupportedNodeVersionMessage` directly against a version string instead and
say that is what was tested.

AC3 — `--require-hashes` and an identical re-resolve (commit 3). This must run
on all three matrix legs, not just the local machine:

```bash
python3 -m pip install --require-hashes --dry-run -r requirements-dev.txt
```

```bash
make check
```

**Not verified by any of the above:** that the pinned Node major is present in
the GitHub runner tool cache. That is a property of the runner image, not of
this repo, and it changes without notice. The observable proxy is fast-lane
wall-clock on the `ci-scope` job before and after commit 2 — a jump means the
version is being downloaded.

## Review gates

- Commit 2's diff must not add a second Node-version assertion. Check the final
  `.mjs`, not the diff: exactly one `MIN_NODE_VERSION` per copy.
- Commit 2's diff must not add `package.json`.
- Commit 3 does not merge on a green ubuntu/3.13 run alone. All three matrix
  legs must have installed under `--require-hashes`.
- Commit 3 must not leave two root-level requirements files for the same
  dependency set (step 14).
- `setup-node` is SHA-pinned with a version comment, or zizmor fails the
  `security` lane.
- If `.gitignore:176` is dropped, `uv.lock` is regenerated in commit 3 and one
  lock is recorded as authoritative (step 6).

## Rollback

Commits 1 and 2 revert cleanly; commit 1's only irreversible act is deleting a
regenerable local `uv.lock`.

Commit 3 reverts cleanly as a diff but not operationally: once compiled files
are the install source, every dependency change requires a recompile. A revert
that leaves the compiled files in place without `--require-hashes` produces a
lock nothing enforces — worse than either end state. Revert the file layout and
the flag together.
