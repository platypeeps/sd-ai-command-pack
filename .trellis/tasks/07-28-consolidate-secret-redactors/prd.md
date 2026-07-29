# Consolidate the two divergent secret redactors behind one shared pattern set

## Goal

Two secret-scrubbing implementations live in this pack and disagree about what a
secret looks like. The weaker one guards the diagnostic text that environment
blocks carry into agent-visible reports. Give both one pattern set without
flattening their deliberately different failure policies, and close the two
orphaned pieces of the environment-blocked contract while in the same code.

## Origin

Created 2026-07-28 from the repo audit with explicit user consent. Owns finding
A-069 (P2 · S · Plausible · security) and the narrowed residual of A-099
(P3 · M · correctness) after the 2026-07-28 disposition — see Notes.

Both were post-completion residue of
`07-28-analyze-recurring-trellis-workflow-instability`: that task's design
package B specified only "bounded human text without secrets" and set no
requirement to reconcile the two redactors, so neither finding had an owner.

## Requirements

- R1 (A-069): one shared secret-pattern set, defined once. Today
  `scripts/sd_ai_command_pack_lib.py:497` `_ENVIRONMENT_SECRET_RE` matches only
  `bearer <v>`, `[access_|api_]token[=:] <v>`, and `gh[pousr]_`, while
  `scripts/sd-ai-command-pack-fleet-timing.py:28` `SECRET_RE` additionally covers
  `github_pat_`, `xox[baprs]-`, `sk-`, PEM private-key headers, and
  `(token|password|secret|api[_-]?key)\s*[:=]\s*\S+`. A fine-grained GitHub PAT
  (`github_pat_…`) is not matched by `gh[pousr]_` — `[pousr]` excludes the `i` —
  so it passes through the lib redactor verbatim.

- R2 (constraint on R1): the two call sites must keep their different policies.
  This is not one function with two callers:
  - `sd_ai_command_pack_lib.py:519` **substitutes** — `_ENVIRONMENT_SECRET_RE.sub("[redacted]", text)`
    inside `_redact_environment_text` (`:512`), which the fragment composer calls
    for `operation`, `checkpoint`, and `diagnostic` (`:593`, `:595`, `:600`).
  - `sd-ai-command-pack-fleet-timing.py:172` **rejects** — `if SECRET_RE.search(...)`
    raises `FleetTimingError(f"{label} contains secret-like material")`.
  Share the pattern set; do not force either site onto the other's policy. A
  fail-closed reject in the diagnostic path would drop the diagnostic that
  recovery depends on; a silent substitution in the fleet path would let
  secret-shaped operator input reach a timing record that is meant to refuse it.

- R3 (constraint on R1): widening the lib's pattern set must not over-redact.
  The fleet key-value branch ends in `\S+`, the lib's token branch in
  `[A-Za-z0-9._\-]{8,}`. Under `.sub()`, `\S+` is greedy across trailing
  punctuation and will swallow diagnostic context the current pattern preserves.
  Decide per pattern whether the shared form is the detector form, the
  substituter form, or both, and record the choice.

- R4 (A-069): extend the test table to the shapes the shared set adds.
  `tests/test_script_lib.py:670` asserts exactly three: a URL credential, one
  `ghp_`, and one `Bearer`. Add positive cases for `github_pat_`, `xox[baprs]-`,
  `sk-`, a PEM header, and a `password:`/`api_key=` key-value form, plus a
  negative case proving R3's bound (a diagnostic whose surrounding context
  survives redaction).

- R5 (A-099 residual): make the environment-blocked validator reachable from
  production instead of leaving it test-only.
  `validate_environment_blocked_evidence` (`sd_ai_command_pack_lib.py:606`) has
  **no** caller outside `tests/` — verified repo-wide; the only hits are
  `tests/test_script_lib.py` (6 call sites) and `tests/test_housekeeping_result.py:169`.
  Its sibling `cache_setup_blocked_evidence` (`sd_ai_command_pack_lib.py:641`) is
  reachable only through `_cache_env_main`'s `if as_json:` branch
  (`sd_ai_command_pack_lib.py:687-691`), and the sole production
  caller — `scripts/sd-ai-command-pack-toolchain.sh:417-418` — invokes
  `cache-env --repo "$REPO_ROOT" 2>/dev/null` with no `--json` and stderr
  discarded. Pass `--json` from `configure_cache_environment` and consume the
  `{"outcome": "blocked", "environmentBlocked": …}` fragment. Prefer this over
  deletion: `toolchain.sh:419` currently re-states the same remediation as a
  hardcoded prose string that the structured `recoveryAction` already carries,
  so wiring removes a duplicate rather than adding a consumer for its own sake.

- R6: template parity. `templates/scripts/sd_ai_command_pack_lib.py` carries the
  same functions at the same line numbers (`:606` confirmed). Every lib change
  lands in both copies and generated-parity checks stay green.

- R7: no weakening. Every input the current tests redact must still be redacted;
  the change is strictly additive in coverage.

## Acceptance Criteria

- [ ] R1/R4: one pattern set has one definition site, and a table-driven test
      asserts every covered shape is caught by both consumers — substituted in
      the lib path, rejected in the fleet path.
- [ ] R1: a diagnostic containing `github_pat_` plus a fine-grained PAT body
      emits no PAT substring in the resulting fragment. This case fails today.
- [ ] R2: fleet-timing still raises `FleetTimingError` (not a silent
      substitution) on secret-like input, and the lib still returns a bounded
      redacted string (not an exception) — asserted separately.
- [ ] R3: an existing redaction test that keeps surrounding diagnostic context
      still keeps it; no test loses context to greedy matching.
- [ ] R5: `validate_environment_blocked_evidence` has at least one non-test
      caller, and a fixture where cache setup fails produces a validated
      `environment_blocked` fragment through `toolchain.sh` rather than only the
      hardcoded prose message.
- [ ] R6: `scripts/` and `templates/scripts/` copies are identical; `make sync`
      and generated-parity checks pass.
- [ ] `make check` passes.
- [ ] Changelog + version; fleet rollout via normal refresh.

## Notes

- Audit source: `.trellis/audit/report-2026-07-28.md` — A-069 (P2 · S ·
  Plausible · security) and A-099 (P3 · M · Plausible · correctness).
- **A-069 exposure, corrected 2026-07-28.** The audit's `why:` line claimed a PAT
  "passes through verbatim into PR-visible summaries." A repo-wide search found
  **no** GitHub or PR publication path for these fragments. The real exposure is
  agent-visible and local: the `environmentBlocks` array in the housekeeping
  `--json` result (`docs/SD_AI_COMMAND_PACK.md:1154`) and the bare
  `{"outcome": "blocked", "environmentBlocked": …}` payloads from
  `work-loop.py:2844`, `update-spec-kb.py:1542`, and `record-session.py:292`.
  That is still worth fixing — the fragments are built from `git`/`gh` error text
  that echoes environment values — but it is P2 local leakage, not publication.
- **A-099 disposition, decided 2026-07-28.** The finding's headline claim — that
  the five-field schema has no machine consumer and should collapse to
  `{reasonCode, boundary, operation, diagnostic}` — is **rebutted**. Agent-as-consumer
  is the deliberate design of work package B in
  `07-28-analyze-recurring-trellis-workflow-instability`, whose `design.md`
  mandates exactly these fields and states that skills interpret the structured
  blocker. Collapsing the schema would undo a shipped decision, not remove
  accidental complexity. What is *not* rebutted is the orphaned validation the
  finding uncovered along the way: `sd_ai_command_pack_lib.py:606` and the
  `sd_ai_command_pack_lib.py:687-691` branch really are unreachable from production. R5 covers that, and only that. Net scope moved
  from "remove ~226 lines" to "wire ~2 lines and make ~60 lines reachable."
- The audit's own `fix:` line for A-069 — "promote the fleet-timing pattern set
  into one shared redactor" — is half right. It reads as though one redactor
  serves both, which R2 forbids. Recorded here so the merge is not attempted as
  written.
- Adjacent, not overlapping: `07-28-consolidate-shared-script-helpers` moves
  four other duplication clusters (A-046/A-076/A-080/A-085) into the same lib and
  requires that all four "preserve existing `environment_blocked` evidence
  behavior." It does not own the redactor or the validator. If both tasks are
  active, land this one first so that task's constraint is checked against the
  final redactor rather than the current one.
- **R3 states only half the hazard, measured 2026-07-28.** R3 records greedy
  over-redaction (`\S+` swallowing trailing punctuation — reproduced:
  `password: hunter2trailing,` becomes `[redacted] `). The larger hazard is the
  opposite one and R3 omits it: `SECRET_RE` is a **detector**, and most of its
  alternatives match a bare prefix with no body requirement (`gh[pousr]_`,
  `github_pat_`, `xox[baprs]-`, the PEM header). Under `.sub()` that redacts the
  prefix and leaves the credential body —
  `ghp_ABCDEFGH012345678` becomes `[redacted]ABCDEFGH012345678`, which is
  **worse than today's lib output**. The shared artifact therefore cannot be one
  regex; `design.md` specifies a table of shapes each carrying a detector form
  and a substituter form.
- **The current test cannot catch that regression.**
  `tests/test_script_lib.py:687` asserts
  `assertNotIn("ghp_ABCDEFGH012345678", diagnostic)` — prefix and body as one
  literal — which **passes** against `[redacted]ABCDEFGH012345678`. Rewriting the
  assertions to test the body substring alone is step 0 of the implementation and
  passes on today's unchanged code.
- **R5 has a trap the requirement does not mention.** `--json` is not scoped to
  the error path: `_cache_env_main:695-700` switches the **success** output to
  `{"outcome": "ok", "cacheEnv": …}` too, and `toolchain.sh:421` parses
  `key=value` lines with a `while IFS='=' read` loop that hard-fails on an
  unrecognized key and then asserts `count -eq 7`. Adding `--json` to the
  existing call breaks every successful toolchain invocation, in an untested
  shell layer. `design.md` gives two workable shapes; the recommended one
  re-invokes with `--json` only on the already-failing branch.
- Planning complete 2026-07-28: `design.md` and `implement.md` added.
