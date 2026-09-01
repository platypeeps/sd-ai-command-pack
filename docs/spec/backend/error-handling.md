# Error Handling

> [!important]
> **Partly stale as of 2026-09-01.**
> The Overview, Error Types, Error Handling Patterns and Common Mistakes
> sections specify `install.py` -- its `SystemExit` sites, its `0`/`2`/`3` exit
> contract, `require_trellis_repo()`, `install_file()`, `run_diff_check()` -- and
> that file was deleted on 2026-08-30 by step 3e (`43170716`, #610). The
> `.trellis/config.yaml` mention already carries an inline absent marker.
>
> Three lessons below outlive their subject and are worth keeping: "Don't:
> treat multiplicity as ambiguity" (its `claude plugin list --json` example is
> still live, and `dashboard/plugins.py` reads a `sd plugin list --json` of the
> same shape), "Don't: block on a normal steady state", and "Don't: say 'this
> command' in a diagnostic that gets forwarded". That last one's example names
> `sd-ai-command-pack-review.py`, which is gone; the rule is not about that file.
>
> The text below is unedited. It is the record of what that machinery
> specified, not guidance for the repository as it stands. The triage that
> produced this notice is recorded under step 7 in
> `docs/work/2026-08-29-artifacts-as-product/implement.md`.

> How errors are handled in this project.

---

## Overview

This is a command-line installer. Errors should be clear, deterministic, and
expressed through process exit codes and concise terminal output.

## Error Types

- Use `SystemExit` for fatal CLI validation failures, as in
  `require_trellis_repo()` and missing template checks in `install_file()`.
- Use integer return codes from `main()` for expected command outcomes:
  normal install/remove uses `0` for success and `2` for file conflicts;
  inspection uses `0` for a successful current/informational result, `1` for
  invalid state or operational/audit failure, and `3` when `--check` finds a
  valid install or refresh action is required. Argparse usage errors remain
  `2` before `main()` runs.
- Reject incompatible flag combinations early, such as `--backup` without
  `--force`.
- Avoid custom exception classes until there is more than one caller that needs
  structured recovery.

## Error Handling Patterns

- Validate prerequisites before writing files. `require_trellis_repo()` runs
  before selecting and installing templates.
- Represent non-fatal install outcomes with status strings such as
  `unchanged`, `created`, `updated`, `conflict`, and `overwritten`. `updated`
  is a write that needed no `--force`, so it never contributes to the
  conflict exit `2`.
- Use `subprocess.run(..., check=False)` when a command result is part of the
  installer contract, such as `git diff --check`.
- Catch `FileNotFoundError` only for optional tooling. `run_diff_check()` warns
  and continues if `git` is missing.

### Don't: treat multiplicity as ambiguity

**Problem**: an external listing reports the same subject more than once, and
the reader refuses the whole result.

```python
# Don't do this
matches = [e for e in entries if e.get("id") == wanted]
if len(matches) > 1:
    return UNAVAILABLE, f"{wanted} is listed more than once"
```

**Why it's bad**: several entries usually mean several *registrations* of one
thing, not several things. `claude plugin list --json` emits one entry per
scope — user, then one per project that enables the plugin — and every entry
carries the same version and install path. Refusing them reports a machine
unknowable when it is perfectly knowable, and the failure text names an action
that does not exist ("resolve the duplicate install"), which sends the operator
to break a working configuration. The cost compounds: a refusal upstream of a
comparison suppresses the comparison's alarm too, so a real divergence goes
unreported rather than merely unexplained.

**Instead**: reconcile on the field actually consumed, and refuse only a
genuine disagreement. Normalize before deduplicating, so entries differing
only past a truncation limit do not read as a conflict.

```python
# Do this instead
versions: list[str] = []
for entry in matches:
    version = entry.get("version")
    normalized = safe_text(version, limit=80) if isinstance(version, str) else ""
    if normalized and normalized not in versions:
        versions.append(normalized)
if not versions:
    return UNAVAILABLE, f"no listed {wanted} entry carries a version"
if len(versions) > 1:
    return UNAVAILABLE, f"{wanted} is listed at conflicting versions ({', '.join(sorted(versions))})"
return versions[0], None
```

Each reader reconciles on its own consumed field: the status collector on
`version`, the machine updater on `installPath`. Two readers of the same
listing can legitimately disagree about whether a given listing is conflicting.

**Test point**: a fail-closed refusal needs a case proving the *benign* shape
still succeeds, not only cases proving failures refuse. Assert the reconciled
value and that the downstream verdict it feeds is reachable — a test that
injects the downstream verdict directly proves the renderer works, never that
the collector can produce it.

### Don't: block on a normal steady state

**Problem**: a fail-closed check fires on a condition that is ordinary, or that
the operator cannot resolve at the moment it fires. Every run reports the same
verdict, so the verdict stops carrying information and readers learn to skip it.

The failure is not that the check is wrong; it is that it cannot discriminate.
The signal that fires on all fourteen branches fires identically on the one that
holds stranded work.

```python
# Wrong: every extra branch is a blocker, including branches another live
# worktree holds and therefore nobody can delete.
if extras:
    anomalies.append("extra local branches remain: " + ",".join(extras))
```

```python
# Right: classify, and reserve blocking for what this run was responsible for.
classification = classify(extras)          # both modes, one code path
details.extend(advisory_from(classification))
if expect_clean:
    details.extend(strict_postconditions(...))   # blocking
```

Three rules make this concrete:

- **Blocking belongs to postconditions.** A check earns a blocking severity when
  it verifies something *this run* was supposed to achieve. Pre-existing state
  the run never touched is reported, not blocked on.
- **Impossible is not the same as failed.** A condition the operator cannot act
  on -- a branch held elsewhere, a resource owned by another process -- is
  advisory. Blocking on it produces a verdict that can never clear. Prove the
  impossibility from evidence (the worktree inventory), and keep the blocking
  code for every other cause; "the switch failed" and "the switch could not have
  succeeded" are different findings.
- **A claim about absence needs complete evidence.** "No pull request exists"
  may only be asserted from evidence that was available, untruncated, and
  current. A bounded listing that came back full proves nothing about what is
  missing from it. Report `unknown` with the reason instead; an unknown is
  useful and a false negative is not.

Severity has exactly one owner. When two scripts must agree on it -- a producer
that replays codes into a consumer -- pin the two tables together in a test
rather than trusting them to stay in step; a code that is advisory on one side
and blocking on the other yields a clean verdict from a run that exited nonzero.

**Test point**: reclassifying one condition must not become a general
exit-zero rule. Pair the test that proves the reclassified case passes with one
test per surviving blocking condition proving it still fails, and assert the
exact verdict -- `verdict == "clean"`, not `verdict != "blocked"`, since
`failed` and `indeterminate` would satisfy the negative form.

### Don't: say "this command" in a diagnostic that gets forwarded

**Problem**: a stage prints a remedy naming its own flag.

```python
# Don't do this: correct only for a caller who invoked this stage directly.
BOOKKEEPING_EVIDENCE_SHAPE = (
    ...
    "Obtain the three target values from the "
    '"target" object in this command\'s own --plan-only --json report'
)
```

`sd-ai-command-pack-review.py` also accepts `--bookkeeping-evidence`, forwards
it to the stage, and relays the stage's rejection back verbatim. That
controller has no `--plan-only`. To a caller who used it, "this command" reads
as the controller, so the remedy sends them to a flag it rejects with
`unrecognized arguments`.

**Instead**: name the executable, so the sentence is true from every entry
point that can surface it.

```python
# Do this instead.
    "Obtain the three target values from the "
    '"target" object of an '
    '"sd-ai-command-pack-review-local.py --plan-only --json" report'
```

**Why**: a diagnostic is data that travels. Any message a wrapper can relay is
read outside the process that wrote it, so deixis — "this command", "the flag
above", "rerun with the same arguments" — resolves against the wrong referent.
Self-reference is safe only in a message no other surface forwards, and that
property is not visible from the line that writes it. Prefer the absolute name.

**Check**: for each argument a wrapper forwards, confirm the wrapped command's
diagnostics name the tool the remedy belongs to rather than referring to
themselves.

## API Error Responses

There is no HTTP API. For CLI errors, print actionable text that names the
failing path or conflict and the user action, such as re-running with
`--force`.

## Common Mistakes

- Do not let Python tracebacks leak for expected user errors like a missing
  `.trellis/config.yaml` [absent: target-repo Trellis path], conflicting target file, or target path occupied by a
  directory or other non-file.
- Do not collapse conflicts into success. Tests expect conflict handling to
  leave the target file untouched.
- Do not silently ignore safety flags that cannot take effect.
- Do not use `check=True` for commands whose failure should be reported as a
  normal installer result.
