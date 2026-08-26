# A hard provider failure at a findings-mapped exit code is recorded as findings

## Origin

Found on 2026-08-26 shipping PR #563 at pack 0.71.60. Deterministic `sd-check`
passed 7/7, the branch was base-updated and CI-green, and `sd-review` still
returned:

```
status: findings
diagnostic: local review findings require disposition before remote routing
local.remoteGate: {"state": "blocked", "reason": "actionable-local-findings"}
local.findings: []
local.disposition: {"outstanding": 0, "dispositioned": 0, "accepted": 0}
```

Zero findings, zero outstanding, and a gate demanding that findings be
dispositioned. Nothing can clear it: `rebutted`, `miscited`, and `accepted` all
take a finding id, and there are no ids.

The provider had not found anything. It had died. Running the same argv by hand:

```
gito review --what d9a4c00d --vs 3787ae4e --out <dir>/provider-output
'code': 402  "This request requires more credits, or fewer max_tokens.
You requested up to 65536 tokens, but can only afford 63920."
gito exit=1        # <dir>/provider-output is empty
```

`retries = 3` in `.gito/config.toml` was consumed; all four attempts returned
402. This is a billing wall, not a transient blip, and not a review.

## The mechanism

Three steps, each defensible alone.

1. The exit code is mapped to an outcome before anything knows whether a report
   exists (`templates/scripts/sd-ai-command-pack-review-local.py:2037`):

   ```python
   status_value = provider.outcome_by_exit.get(exit_code, "failed")
   ```

   Both shipped adapters map `"1": "findings"` — prism at `:293` and gito at
   `:308`. That is the right reading of the convention: these tools exit 1 when
   they find something. They also exit 1 when they fail.

2. The payload is then parsed, and there are two ways the exit-map verdict
   survives a review that did not happen.

   **Route A — no payload (this is the one #563 hit).** A dead provider writes
   no report, so `_gito_payload` returns `None` (`:1876`); `_prism_payload`
   does the same on unparseable stdout (`:1845`). The recovery for a missing
   payload covers exactly one case (`:2087`):

   ```python
   elif exit_code == 0:
       status_value = "failed"
       stderr += b"\nprovider did not produce a valid structured review report"
   ```

   A provider that exits 0 and writes nothing is correctly called failed. A
   provider that exits **1** and writes nothing keeps whatever step 1 assigned
   it — `findings` — and the branch that would have corrected it never runs.
   Confirmed on #563: the attempt's `provider-output` directory was empty.

   **Route B — a payload that parses clean.** Not observed on #563, but
   reachable from the same mapping. When a payload does parse, the exit-map
   verdict is sticky (`:2080`):

   ```python
   status_value = (
       "findings"
       if findings
       or status_value == "findings"      # <- set by the exit map at :2037
       or payload_status == "findings"
       else payload_status
   )
   ```

   `_gito_payload` and `_prism_payload` both return `"clean"` for a report with
   no findings (`:1868`, `:1923`). That `"clean"` cannot win: the middle
   disjunct already holds, so a provider that exits at a findings-mapped code
   while reporting nothing is relabelled `findings` and its successful clean
   review is discarded. Both routes end at the same contradiction — status
   `findings`, `findings: []`.

3. `_aggregate_outcome` ranks `findings` ahead of `failed` (`:2171`), so one
   masked lane sets the whole receipt's outcome.

The result is an attempt recorded as `status: "findings"` with `findings: []`
and `exitCode: 1`, and a receipt whose own numbers contradict its verdict.

## The gate is not the defect

The obvious-looking fix is to let the gate release a `findings` outcome that
lists nothing. That would be wrong, and the code says so at `:2505`:

> A provider that reports `findings` but lists none has given evidence nobody
> can inspect, rebut, or classify by severity, so it still blocks — and it
> blocks ahead of every release path below.

That guard is deliberate and worth keeping: it is what stops an empty or
truncated provider payload from being waved through as clean. The gate reasoned
correctly about the input it was handed. The input was false.

So the fix belongs at the attempt-status resolution, not at the gate, and a
change that relaxes `:2511` should be read as a regression of a guard rather
than a fix for this.

## What this fix will not fix

Correcting the status does **not** unblock a PR whose provider is down, and the
task should not be sold as if it does.

With the status corrected, the single configured provider's `failed` status
makes `_aggregate_outcome` return `"failed"`, which is in `TERMINAL_FAILURES`,
so the gate takes its `:2522` branch — by that half of the condition, not by
`degraded`. This repository's local policy is `optional`
(observed `plan.localPolicy: "optional"`), so the gate returns
`eligible-with-limitations`. The router on this repository is `absent`
(`setup-descriptor-absent`), and `sd-review`'s own rule is explicit that
`eligible-with-limitations` is not sufficient there:

> A router classified `absent` may complete locally only when routing is
> optional and the local stage's `remoteGate.state` is `eligible`. …
> `eligible-with-limitations` is not eligible here.
> (`templates/.agents/skills/sd-review/SKILL.md`)

PR #563 would therefore still be blocked — correctly, because no review
actually happened. What changes is that the operator is told "the local review
lane failed" instead of "disposition your findings", and is pointed at the
credit balance instead of at a finding list that does not exist. Whether a
repository should be able to ship past a documented unavailable local lane is a
separate policy question and is out of scope here.

## Why it is worth fixing anyway

The failure mode is silent and self-certifying. A receipt that says
`actionable-local-findings` reads as a reviewer having done its job and found
problems. It is durable evidence, retained and replayed, and it names a cause
that never happened. An operator following it looks for findings, finds none,
and has no path forward from the artifact itself — the diagnosis has to be
rebuilt by running the provider by hand, which is how this one was found.

It also fires on the most ordinary provider outage there is: an expired key, an
exhausted balance, a rate limit, a network refusal. Any of them exits nonzero
without writing a report.

## Goal

A provider that fails without producing a valid report is recorded as failed,
whatever exit code it used, and the receipt's gate reason names the failure
rather than asserting findings that do not exist.

## Directions worth weighing

- **A. Widen the payload-absent recovery.** The narrow reading: at `:2087`,
  treat *any* absent payload as a provider failure rather than only
  `exit_code == 0`. A provider that genuinely found something must produce a
  report to say what — an unparseable or missing report is a failure at every
  exit code, not just zero. Smallest change that makes the receipt honest.
- **B. Also refuse a `findings` status that carries no findings.** Defence in
  depth for the case where a payload parses but is empty while the exit code
  claims findings. Belongs beside A, at the same place, and keeps the `:2511`
  guard as the last line rather than the only one.
- **C. Do nothing and document the exit-code convention.** Rejected: the
  artifact that misleads is the durable receipt, and documentation elsewhere
  does not travel with it.

A and B are complementary. Neither touches the gate.

## Out of scope

- Whether an optional local lane that is genuinely unavailable should be able to
  release a PR when the router is absent. That is a policy decision about
  `eligible-with-limitations`, not a correctness bug, and it is the thing that
  would actually unblock a PR during an outage.
- Provider credential and balance management.
- The `_aggregate_outcome` findings-over-failure ranking at `:2171`. It is
  deliberate, documented at `:2517`, and correct once the per-attempt status is
  truthful; the archived `08-25-aggregate-outcome-masks-provider-failure`
  covered that ranking and did not reach this path.

## Acceptance criteria

- [ ] A provider that exits at a findings-mapped code and writes no report is
      recorded with `status: "failed"`, not `"findings"`. The test drives a
      real nonzero exit with an absent report rather than constructing the
      attempt record directly.
- [ ] The same holds for a report that exists but does not parse, at a
      findings-mapped exit code.
- [ ] A provider that exits at a findings-mapped code while reporting a valid
      **clean** payload is recorded as `clean`, not `findings` — route B above,
      the sticky disjunct at `:2083`.
- [ ] A provider that exits at a findings-mapped code and writes a valid report
      listing findings is still `findings` — the existing behaviour is pinned by
      a test so the fix cannot over-reach.
- [ ] The resulting `remoteGate.reason` for a failed optional lane names the
      failure (`local-review-limited` or `required-local-review-failed`), and no
      longer reads `actionable-local-findings`.
- [ ] The `:2511` empty-findings guard is unchanged, and a test asserts it still
      blocks when a payload parses to a `findings` status with an empty list.
- [ ] Both shipped adapters are covered. They share the `"1": "findings"`
      mapping (prism `:293`, gito `:308`) and both payload parsers return
      `None` on an unusable report (`_prism_payload:1845`,
      `_gito_payload:1876`), so neither is protected from either route.
- [ ] All four copies of `sd-ai-command-pack-review-local.py` are byte-identical
      and `make generate` reports `shipped-surface closure: clean`. The
      canonical copy is `templates/scripts/`; the three generated mirrors are
      `scripts/`, `plugins/sd/bin/`, and `plugins/sd/machine-payload/scripts/`.
      Verified by a single digest across all four:

      ```bash
      find . -name sd-ai-command-pack-review-local.py -not -path './.git/*' \
        -print0 | xargs -0 shasum -a 256 | awk '{print $1}' | sort -u | wc -l
      # expect exactly 1
      ```
