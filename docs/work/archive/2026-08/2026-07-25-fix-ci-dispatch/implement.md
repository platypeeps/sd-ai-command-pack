# Implementation — per-job dispatch protocol for sd-fix-ci

One commit. Prose plus regeneration. No scripts, no registry, no manifest kind.

## Order

1. **Decide the fan-out bound before writing prose.** There is no cap on failing
   jobs. `max-reruns=N` (`SKILL.md:113`) bounds reruns, not workers. A wide red
   matrix dispatches one worker per red leg, each with its own toolchain cache
   setup and `gh` API cost.

   **Gate:** this is the pilot. `sd-test-gaps` has `max-gaps` and
   `sd-fleet-refresh` has waves; sd-fix-ci is the one command in the rollout
   with no natural bound. Decide here or `07-25-dispatch-rollout` inherits the
   gap.

2. Add `## Dispatch protocol` to
   `templates/.agents/skills/sd-fix-ci/SKILL.md`, placed after the `## Workflow`
   section and before `## Safety rules`.

   Location matches the reference: `templates/.agents/skills/sd-audit-repo/SKILL.md:156`.
   **Do not** put it in `.github/command-sources/sd-fix-ci.md` — that file is 16
   lines of routing and stays that way.

3. The dispatch unit is workflow step 3 (`SKILL.md:75`, "Classify every failing
   job before acting on any of them"). No workflow restructuring is needed; the
   parallel unit already exists.

4. Step 4 stays with the parent, in full. It pushes commits, opens PRs via
   `sd-create-pr`, and spends the shared `max-reruns` budget.

   **Gate:** a shared counter incremented by parallel workers is not a bound.
   If the final text lets a worker call `gh run rerun`, `max-reruns` is
   unenforceable.

5. **Do not write trust-classification prose into `SKILL.md`.** Measured:
   `templates/.agents/skills/sd-audit-repo/SKILL.md` contains zero occurrences
   of "trust". The block is generator-injected —
   `.github/scripts/generate-command-surfaces.py:179-184` holds
   `CHECKOUT_TRUST_POLICY_MARKER` and the policy text, emitted per
   `CommandInfo.executes_checkout_code` / `trusted_static_only`
   (`installer/registry.py:726`, `:728`). That is why it appears at
   `.claude/commands/sd/fix-ci.md:27` and in no authored source.

   R3 is satisfied by one sentence carrying the *already-resolved* state
   forward:

   > Every dispatch prompt restates the command's resolved
   > `checkout-trust: <state> (<reason-code>)` before the role-specific
   > instructions. Workers do not reclassify; a worker result cannot change the
   > state or unlock a gate the command closed.

   **Gate:** if the diff adds the words "trusted_local_branch",
   "untrusted_fork_pr", or "indeterminate_" to any `SKILL.md`, it has created a
   second hand-maintained copy of a generator-owned classifier. Back it out.

6. **Switch the log fetch to per-job, or the task's stated goal is not met.**
   `SKILL.md:73` currently uses `gh run view <run-id> --log-failed`, which
   returns *every* failing job's log in one call. A parent that runs it and
   splits the blob has already absorbed everything.

   Per-job fetch is supported:

   ```
   -j, --job string   View a specific job ID from a run
   --log-failed       View the log for any failed steps in a run or specific job
   ```

   Parent enumerates jobs with `gh run view <run-id>` (identities only), passes
   each worker its job id, worker fetches its own log.

   **Gate:** this is the whole task. Prose describing per-job workers over a
   whole-run log blob passes every acceptance criterion and delivers nothing.

   Record the two costs in the prose rather than leaving them to be
   rediscovered: `gh`'s own help warns the per-job path falls back to API
   fetches that are "slower and more resource-intensive" and fails outright if
   more than 25 job logs are missing; and every `gh` call routes through
   `bash scripts/sd-ai-command-pack-toolchain.sh run -- gh …` (`SKILL.md:27-33`),
   so N workers means N cache setups.

7. Parent resolves run-level facts once and passes them in the change context:
   behind-default-branch status (needed for `stale-baseline`, `SKILL.md:87`) and
   the PR-head/local-HEAD match note (`SKILL.md:68-70`). Workers must not
   re-derive them — N workers deriving one run-level fact can disagree inside a
   single report.

   Per-job evidence stays per-job: "the same job passing on the same commit
   earlier" (`SKILL.md:81-83`) is one job's history.

8. Write the worker contract into the command body (AC2):

   - input: run id + job id + job name; resolved `checkout-trust: …`; run-level
     change context; `Active task: <path from task.py current>` prefix when a
     Trellis task is active (audit-repo convention, `SKILL.md:163-165`)
   - output: exactly one class from `real-code | flake | infra | stale-baseline`;
     evidence **quotes**, not summaries (`SKILL.md:94` requires concrete flake
     evidence); a suggested fix or rerun disposition as a proposal
   - worker is read-only: no writes, no `gh run rerun`, no pushes

9. Keep the `real-code`/`flake` tiebreak with the parent (`SKILL.md:91-93`:
   prefer `real-code` and reproduce locally first). A worker seeing one job
   cannot apply a rule whose purpose is conservatism across the whole run.

10. Capability-first fallback phrasing (R1), matching
    `templates/.agents/skills/sd-audit-repo/SKILL.md:158-160`: on sub-agent
    dispatch platforms run per-job triage in parallel; on inline platforms
    classify jobs sequentially in one context. Same outcome either way (R5).

11. Report contract unchanged (R4). `SKILL.md:150-152` keeps its shape:
    `<job> · <real-code|flake|infra|stale-baseline> · <evidence one-liner>`.

12. `make generate`, then `make sync`. Regenerate the catalog in
    `docs/SD_AI_COMMAND_PACK.md`.

13. Changelog + version bump.

## Validation

AC1 — generation is byte-stable across the fan-out:

```bash
make generate && git diff --stat && make generate && git diff --exit-code
```

The second `generate` must produce no diff. A non-empty second diff means the
generator is not idempotent for this body.

The adapters that must all carry the new section:

```bash
grep -l "Dispatch protocol" .claude/commands/sd/fix-ci.md .opencode/commands/sd-fix-ci.md .github/prompts/sd-fix-ci.prompt.md .gemini/commands/sd/fix-ci.toml templates/.commands/sd-fix-ci.md
```

AC3 — trust restatement present, and present *once*, without a duplicated
classifier:

```bash
grep -c "checkout-trust" templates/.agents/skills/sd-fix-ci/SKILL.md
```

Expect 1. Then confirm the classifier itself was not copied:

```bash
grep -rn "trusted_local_branch\|untrusted_fork_pr\|indeterminate_" templates/.agents/skills/
```

Expect no hits.

```bash
make check
```

**Not verified by any of the above:** that a dispatch platform actually
produces the same classifications as the inline path. That needs one real red
CI run triaged both ways, and there is no fixture for it. The parent task's
cross-child acceptance asks for exactly this comparison for sd-audit-repo
(`07-25-agent-artifacts`, "contract-identical ledgers"); the equivalent check
here is one real red run, and it is a human observation, not a test.

## Review gates

- Step 6 is the task. If the final `SKILL.md` still tells the parent to run
  `gh run view <run-id> --log-failed` and split, the goal is unmet regardless of
  what the acceptance criteria say.
- No trust classifier prose in any `SKILL.md` (step 5).
- No worker may call `gh run rerun` or push (steps 4, 8).
- The fan-out bound is recorded (step 1), because three more commands inherit
  this decision.
- `.github/command-sources/sd-fix-ci.md` is unchanged and still 16 lines.
- `07-25-dispatch-rollout` does not start until this is reviewed. Both PRDs
  state the ordering; it is only real if it is enforced here.

## Rollback

Single commit, additive prose. Revert restores the sequential classification
path, which never stopped working — R5 guarantees the inline outcome is
today's outcome, so a revert is a no-op for behavior on every platform.

The one non-reverting consequence is pattern propagation: if
`07-25-dispatch-rollout` has already copied the shape into three more commands,
reverting here leaves four bodies to fix instead of one.
