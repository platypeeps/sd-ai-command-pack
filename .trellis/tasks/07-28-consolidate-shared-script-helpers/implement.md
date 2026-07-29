# Implementation — consolidate duplicated script helpers into the shared library

Four independent commits in the PRD's order. Nothing here couples; do not batch
them into one diff.

## Order

### Commit 1 — A-085, atomic write

1. Move the hardened `atomic_write_text` (`review-learnings.py:290`, 67 lines) and
   `default_text_file_mode` (`:276`) into `scripts/sd_ai_command_pack_lib.py`.

2. Delete the 31-line copies at `record-session.py:71`/`:61` and
   `update-spec-kb.py:393`/`:383`, repoint both onto the lib.

3. The hardening delta is **two** mechanisms, not three: the cross-device guard
   (`st_dev` comparison raising `"atomic update would cross filesystems"`) and the
   directory fsync after `os.replace`. The symlink refusal and the file-level
   `os.fsync` already exist in all three copies.

   **Gate:** both added mechanisms fail by raising. Confirm the two newly hardened
   call paths — session receipts and the KB write — handle a raise, since today
   they cannot receive one.

### Commit 2 — A-080, cache-env contract

4. Have `cache-env` emit the key set as data and validate it generically.

5. Convert **all seven** copies, not the three the PRD names. Measured:

   ```
   sd_ai_command_pack_lib.py:38-45   CACHE_ENV_KEYS tuple (authority)
   sd_ai_command_pack_lib.py:47-54   key → subdirectory dict
   shell-lib.sh:194                  case glob
   toolchain.sh:425                  case glob
   toolchain.sh:308                  positional args into the doctor heredoc
   toolchain.sh:362                  dict inside that heredoc's Python
   toolchain.sh:401-408              printf diagnostic block
   ```

6. Remove the magic arity assertions: `shell-lib.sh:210` (`-ne 7`) and
   `toolchain.sh:435` (`-eq 7`).

7. **Decide `toolchain.sh:401-408` deliberately.** It is operator-facing
   diagnostic text, one labelled `printf` per key. Generating it from data changes
   what the operator reads. Either convert it or record why it stays — but if it
   stays, AC2 is not met and the PRD should say so.

   **Gate:** AC2 is "adding an eighth cache variable requires no shell-side edit."
   Test it literally — add a dummy eighth key, run the shell paths, revert.
   Converting the two `case` globs and stopping satisfies the PRD's wording and
   fails this test.

### Commit 3 — A-046, state root

8. **Decide the migration before writing code.** Two of the four sites ignore
   `SD_AI_COMMAND_PACK_STATE_HOME` today:

   | site | function | honors the pack var |
   |---|---|---|
   | `work-loop.py:295` | `resolve_state_root` | yes |
   | `recovery-artifacts.py:123` | `resolve_state_root` | yes |
   | `fleet-timing.py:371` | `resolve_state_root` | **no** |
   | `fleet-controller.py:212` | `default_state_home` | **no** |

   For a user with that variable set, unifying **moves** live fleet timing records
   and campaign state. Old state is orphaned, not migrated.

   **Gate:** pick read-through fallback (resolve new; if absent and legacy exists,
   read legacy, write new) or a documented one-time move in the changelog. Record
   the choice. This is the highest-consequence step in the task.

9. `fleet-controller.py:212` is not a fourth copy of `resolve_state_root` — it is
   `default_state_home`, a different signature with no absolute-path validation,
   no Windows branch, and `/fleet-campaigns` baked into the root. Move that
   suffix to the caller per R1's "callers keep only their subdirectory name".

10. Move `STATE_HOME_ENV` (`work-loop.py:38`, `recovery-artifacts.py:49`),
    `resolve_state_root`, and `ensure_private_directory` into the lib with one
    blocked-write contract. Preserve `recovery-artifacts.py:155`'s behavior gap
    noted in the PRD — raw `OSError` escaping where the work-loop twin raises with
    evidence — by adopting the *evidence-raising* form, not the leaking one.

### Commit 4 — A-076, git invocation

11. Migrate the two clean bypasses onto the lib's `run_git`:
    `review-local.py:541` `_git` and `surface-check.py:124` `_run_git`. Neither
    file references `run_git_command` today (`grep -c` returns 0 for both), so
    both are fresh migrations. Preserve `review-local`'s `binary` overloads and
    `GIT_TERMINAL_PROMPT=0`, and `surface-check`'s bytes return.

12. **`work-loop.py:202` keeps a local adapter.** Do not repoint its call sites.
    Its contract is `-> str | None` and it never raises: `OSError`, `UnicodeError`,
    and `TimeoutExpired` all become `None` (`:227-228`), as does any non-zero exit
    (`:229`). About ten call sites read `None` as "unavailable" —
    `resolve_repository:237`, `:1335`, `:1341`, `:1354`, `:1359`, `:1369`, `:1421`,
    `:1659`, `:1670`. The lib's `run_git` raises.

    **Gate:** the goal is one git *invocation*, not one git *error policy*. Wrap
    the lib call in the existing swallowing adapter. Rewriting ten sites' error
    handling is a different change and belongs in its own task.

    Preserve `errors="strict"` at this site. The lib defaults to
    `errors="replace"` (`sd_ai_command_pack_lib.py:376`); under `replace`,
    non-UTF-8 git output stops raising and starts returning mojibake that the
    callers then parse. That converts "unavailable" into "wrong answer".

13. Preserve `build_tool_environment`'s `CacheSetupError` → `WorkLoopError`
    conversion with its `CACHE_ROOT_ENV` remediation text (`work-loop.py:204-214`).
    R5: `environment_blocked` evidence behavior must survive all four clusters.

14. Collapse the **three** delegating adapters — not five — to two lib shapes with
    a per-script error adapter passed via `context=`:

    ```
    record-session.py:102    run_git(*args) -> CompletedProcess
    pr-body-scope.py:277     _run_git(root, *args) -> tuple[int, str, str]
    review-learnings.py:992  _run_git(args, repo_root, *, check, accept_one)
    ```

    Exactly three files import `run_git as run_git_command`
    (`pr-body-scope.py:55`, `record-session.py:52`, `review-learnings.py:39`).
    `audit-route.py`, `fleet-review-classify.py`, and `recovery-artifacts.py` call
    the lib's `run_git` directly in list form and need **no change** — counting
    them is what produced "five".

    Keep `pr-body-scope.py:283`'s `CommandError` → `(124, "", str(exc))`
    flattening. It is error shaping the lib does not do.

### Every commit

15. Mirror lib edits into `templates/scripts/sd_ai_command_pack_lib.py`, then
    `make sync`.

16. Changelog + version.

## Validation

AC1 — the state roots converge (commit 3):

```bash
SD_AI_COMMAND_PACK_STATE_HOME=/tmp/sdstate python3 -m pytest tests/ -k "state_root or state_home" -q
```

Today `fleet-timing` and `fleet-controller` ignore that variable; after commit 3
they must not.

AC2 — decisive, and it must be run literally (commit 2):

```bash
grep -rn "XDG_CACHE_HOME|PYTHONPYCACHEPREFIX" scripts/*.sh
```

Expect no hand-maintained key alternation. Then add a dummy eighth key to
`CACHE_ENV_KEYS` and confirm no shell file needs editing.

AC4 — no script builds a git environment outside the lib (commit 4):

```bash
grep -rn "subprocess.run(\s*$\|\"git\", \*args\|\[\"git\"" scripts/*.py
```

Expect hits only in `sd_ai_command_pack_lib.py` and `work-loop.py`'s adapter.

AC3 — receipts and KB write through the hardened writer (commit 1):

```bash
grep -n "def atomic_write_text" scripts/*.py
```

Expect exactly one, in the lib.

```bash
diff scripts/sd_ai_command_pack_lib.py templates/scripts/sd_ai_command_pack_lib.py && make sync && make check
```

**Not verified by any of the above:** the A-046 migration decision. No test can
tell you whether orphaning a user's existing fleet state is acceptable. That is
step 8's gate and it is a judgement call, not a check.

## Review gates

- Commit 3 does not merge without a recorded migration decision (step 8).
- Commit 4 does not repoint `work-loop.py:202`'s call sites (step 12). If the diff
  touches `resolve_repository` or the `:1335`-`:1670` cluster, the scope grew.
- `errors="strict"` survives at `work-loop.py`. Check the final file, not the diff.
- Commit 2's AC2 is tested by adding a key, not by reading the diff.
- All four preserve `environment_blocked` evidence behavior (R5). Check against
  the redactor as it exists at merge time — if
  `07-28-consolidate-secret-redactors` is active, land that first.

## Rollback

Each commit reverts independently. Commit 3 is the exception: once state has been
written under the new root, reverting orphans it in the other direction. That
asymmetry is the argument for choosing the read-through fallback in step 8.
