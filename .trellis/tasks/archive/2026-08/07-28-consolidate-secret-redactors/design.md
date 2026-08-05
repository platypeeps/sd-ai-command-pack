# Design — consolidate the two divergent secret redactors

## Scope boundary

The two pattern definitions and the two policies that consume them:

- `scripts/sd_ai_command_pack_lib.py:497` `_ENVIRONMENT_SECRET_RE`, consumed by
  `_redact_environment_text` (`:512`) which **substitutes** at `:519`.
- `scripts/sd-ai-command-pack-fleet-timing.py:28` `SECRET_RE`, consumed at `:172`
  which **rejects** by raising `FleetTimingError`.

Plus R5's two orphans, which are in the same file and the same blast radius.
Not in scope: any other duplication cluster — `07-28-consolidate-shared-script-helpers`
owns those.

## The shared artifact cannot be one regex

This is the central finding, and the PRD's R3 states only half of it.

R3 records the over-redaction hazard: the fleet key-value branch ends in `\S+`,
which under `.sub()` is greedy across trailing punctuation. Real, and confirmed.
But the **opposite** hazard is larger and the PRD does not mention it.

`SECRET_RE` is a **detector**. Most of its alternatives match a bare prefix with
no body requirement at all — `gh[pousr]_`, `github_pat_`, `xox[baprs]-`, the PEM
header, and `sk-` plus exactly one character. For `search()` that is correct and
deliberate: seeing the prefix is sufficient evidence to refuse the input. Reused
under `.sub()` it redacts the prefix and **leaves the secret body in the text**.

Measured 2026-07-28 by running both patterns over the same inputs:

```
IN  : fatal: could not read Username: ghp_ABCDEFGH012345678 rejected
  fleet.sub : fatal: could not read Username: [redacted]ABCDEFGH012345678 rejected
  lib.sub   : fatal: could not read Username: [redacted] rejected
```

The fleet pattern, naively promoted into the lib's substitution path, makes the
`ghp_` case **worse than today**. Same for `xoxb-` (`[redacted]1111-2222-abcdefg`)
and `sk-` (`[redacted]BCDEF0123456789`).

And the lib pattern is genuinely blind where the PRD says it is:

```
IN  : auth failed for github_pat_11ABCDE_xyzXYZ0123456789 in remote
  lib.sub   : auth failed for github_pat_11ABCDE_xyzXYZ0123456789 in remote
```

`gh[pousr]_` cannot match `github_pat_` — `[pousr]` excludes the `i` — and no
other lib alternative applies. R1's claim confirmed.

R3's own hazard also reproduces, in the direction it predicted:

```
IN  : password: hunter2trailing, then continue
  fleet.sub : [redacted] then continue
```

`\S+` swallowed the trailing comma along with the value.

**Therefore the shared artifact is a table of shapes, each carrying two forms:**

| shape | detector form | substituter form |
|---|---|---|
| `ghp_`/`gho_`/`ghu_`/`ghs_`/`ghr_` | prefix alone | prefix + body charset + min length |
| `github_pat_` | prefix alone | prefix + body charset + min length |
| `xox[baprs]-` | prefix alone | prefix + body charset + min length |
| `sk-` | prefix + 1 char | prefix + body charset + min length |
| PEM private-key header | header alone | header **plus the block to `END`** |
| `bearer <v>` | prefix alone | prefix + bounded body |
| `(token\|password\|secret\|api[_-]?key)[:=] <v>` | key + `\S+` | key + bounded body, no trailing punctuation |

The detector column may stay maximally loose; false positives there cost an
operator a rejected timing record. The substituter column must be conservative in
extent but complete in body coverage; a false negative there leaks a credential
and a greedy match destroys the diagnostic.

The PEM row is the one that is not a mechanical widening. A detector sees the
`-----BEGIN … PRIVATE KEY-----` header; a substituter that redacts only the
header leaves the entire key material in the text. It needs a multi-line span to
`-----END … PRIVATE KEY-----`, with a bound so an unterminated header does not
consume the whole diagnostic.

## Two policies, one table

R2 forbids collapsing the call sites, and the reasons are asymmetric:

- The lib path guards a **diagnostic that recovery depends on**. Fail-closed
  there deletes the information the agent needs to unblock itself.
- The fleet path guards a **record meant to refuse** secret-shaped operator
  input. Silent substitution there would accept what it exists to reject.

So the shared module exports the table plus two thin accessors — a compiled
detector alternation for `fleet-timing.py:172`, and an ordered list of
`(pattern, replacement)` pairs for `_redact_environment_text`. Neither call site
gains the other's behavior. `fleet-timing.py` keeps raising
`FleetTimingError(f"{label} contains secret-like material")`; `_redact_environment_text`
keeps returning a bounded string.

Substituter ordering matters and must be explicit: the PEM span runs before the
key-value rule, or a `PRIVATE KEY-----` header sitting after a `key:` on the same
line gets partially eaten by the shorter rule first.

## R7 — no weakening, checked mechanically

R7 says the change is strictly additive in coverage. That is testable rather than
assertable: run the *old* lib pattern and the *new* substituter set over the same
corpus and require that every span the old one redacted is still redacted. A
widened pattern set that happens to reorder alternations can silently lose a case
the old one caught; the assertion catches it.

The corpus is `tests/test_script_lib.py:670`'s existing three shapes (URL
credential, `ghp_`, `Bearer`) plus R4's new ones. Keeping the old pattern around
as test-only data, not as live code, is the cheap way to express this.

## R5 — wiring the orphans, and the trap in it

Confirmed 2026-07-28:

- `validate_environment_blocked_evidence` (`sd_ai_command_pack_lib.py:606`) has
  **zero** non-test callers. Repo-wide, the only non-test hits are the two
  definition sites (`scripts/` and `templates/scripts/`).
- `cache_setup_blocked_evidence` (`:641`) is reachable only through the
  `if as_json:` branch in `_cache_env_main` at `:687-691`.
- `toolchain.sh:417-418` calls `cache-env --repo "$REPO_ROOT" 2>/dev/null` with
  no `--json` **and stderr discarded**, so today a cache failure loses both the
  structured evidence and the `f"error: {error}"` text. `toolchain.sh:418`
  then prints its own hardcoded remediation prose.

**The trap:** `--json` is not scoped to the error path. `_cache_env_main` at
`:695-700` switches the *success* output too:

```python
if as_json:
    cache_env = {variable: environment[variable] for variable in CACHE_ENV_KEYS}
    print(json.dumps({"outcome": "ok", "cacheEnv": cache_env}))
else:
    for variable in CACHE_ENV_KEYS:
        print(f"{variable}={environment[variable]}")
```

`configure_cache_environment` parses that output with `while IFS='=' read -r key value`
(`toolchain.sh:421`) and hard-fails on any unrecognized key —
`fail "cache setup returned an unexpected variable: $key"` — then asserts
`count -eq 7`. So passing `--json` unconditionally breaks **the success path of
every toolchain invocation**, in a shell function with no test coverage.

Two workable shapes:

- **A — retry on failure only** (recommended). Keep the current `key=value` call.
  On non-zero exit, re-invoke with `--json` to capture the evidence fragment,
  then fail with the structured `recoveryAction` instead of the hardcoded prose.
  Confined to the already-failing branch, so the success path is untouched.
  Cost: `build_tool_environment` runs twice on failure. Verify it is idempotent
  before adopting — it is a cache-directory setup, so a second call after a
  failure is plausible but not free.
- **B — parse JSON on both paths.** Cleaner contract, but rewrites the
  `key=value` loop and its two guards (empty-value check, `count -eq 7`) into a
  JSON extraction, in the untested shell layer. Larger diff, larger blast radius.

Either way `2>/dev/null` on the failing invocation should go — it is discarding
the `error:` text that the non-json path emits.

`validate_environment_blocked_evidence` gets its non-test caller here too:
validate the fragment before `toolchain.sh` consumes it, so a malformed fragment
fails at the producer rather than reaching an agent as a plausible-looking
blocker.

## Compatibility

The redactor change is not a contract change: `_redact_environment_text` returns a
string before and after, and `fleet-timing.py:172` raises the same error type. No
payload key moves, so no deprecation window applies.

R6 template parity is mechanical but not optional — `templates/scripts/sd_ai_command_pack_lib.py`
carries the same functions and the generated-parity check compares the copies.
Every lib edit lands in both, then `make sync`.

The one visible behavior change is the `toolchain.sh` failure message: hardcoded
prose becomes the structured `recoveryAction`. Keep the text equivalent — the
current string already says what `recoveryAction` carries, which is why R5 calls
this removing a duplicate rather than adding a consumer.

## Rollout and rollback

Three independent commits, in this order:

1. Shared table plus the two accessors, both call sites repointed, tests widened.
   Self-contained; revertable alone.
2. Template parity + `make sync`. Mechanical.
3. R5 wiring. Touches shell, not the redactor. Revertable alone.

Rollback is a plain revert at any point — nothing here is persisted, versioned, or
consumed across a release boundary.

## Risk

The dangerous outcome is not a missed pattern; it is a **regression disguised as a
widening** — and the existing test suite does not catch it. Verified 2026-07-28:

`tests/test_script_lib.py:687` asserts
`self.assertNotIn("ghp_ABCDEFGH012345678", diagnostic)` — the prefix *and* the
body as one literal. Under prefix-only substitution the diagnostic becomes
`… token [redacted]ABCDEFGH012345678 and …`, and that assertion **passes**:

```
assertNotIn("ghp_ABCDEFGH012345678") passes: True
assertNotIn("ABCDEFGH012345678")     passes: False
```

The credential body is sitting in the output and the test is green. (The sibling
`Bearer` assertion on the next line *would* fail, since the fleet pattern has no
`bearer` alternative at all — so a naive wholesale swap gets caught by accident,
by the wrong test, for the wrong reason. That is not a safety net worth relying
on.)

So: AC1's table-driven test must assert on the **body substring alone**, never on
prefix+body as one literal, and must exercise the substituter path specifically.
Rewriting `:687` to `assertNotIn("ABCDEFGH012345678", diagnostic)` is step 1 of
the implementation, before any pattern changes — it should pass today and is the
gate that makes the rest of the work checkable.
