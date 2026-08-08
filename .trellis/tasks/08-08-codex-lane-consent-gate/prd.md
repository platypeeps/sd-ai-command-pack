# Gate the shipped Codex review lanes on consent, not capability

## Goal

Make the two shipped Codex review lanes run because an operator asked for them,
never merely because the `codex` CLI is installed. Both currently launch on a
successful capability probe alone, with no consent step anywhere in the path.

`08-07-plugin-review-provider-lanes` established that rule for the *planned*
provider mechanism and explicitly left these two live surfaces to their own
task. This is that task.

## The two lanes

Both gate on capability. Neither gates on consent.

1. **Planning adversarial review.**
   `.claude/sd-ai-command-pack/planning-adversarial-review.md:41-44`:

   ```text
   On Claude Code, capability-check the optional native Codex lane with both
   `command -v codex` and `codex exec --help`. When both succeed, launch one
   review-only `codex exec` command in a separate background Bash task before
   starting the host review.
   ```

   The word "optional" describes the lane's availability, not an operator
   choice: nothing in the contract or its rule file offers a way to decline it.

   `.claude/rules/sd-planning-adversarial-review.md` makes the contract
   mandatory whenever a run "creates or materially updates an active Trellis
   task's `prd.md`, `design.md`, or `implement.md`" — which is to say, on
   ordinary planning work. Installed plus planning edit therefore equals a
   `codex exec` run.

2. **Local review.** `.agents/skills/sd-review-local/SKILL.md:166` has the same
   shape for `codex review`:

   ```text
   if command -v codex >/dev/null 2>&1; then
     codex review --help
   fi
   ```

   `sd-review` forbids delegating to `sd-review-local` ("Never call, alias, or
   fall back to `sd-review-local`"), so this lane is not reachable through the
   current review entry point. It is still shipped, still documented, and still
   directly invocable through its own `.claude/commands/sd/review-local.md`
   adapter, so it is a live surface rather than dead code.

## Why this is a defect and not a preference

The capability probe answers "can this run?" and is then used to answer "should
this run?". Those are different questions, and the second one sends the
repository's planning artifacts and diffs to a third party.

Precision matters here: presence alone is not quite the trigger. Both lanes also
require a help or compatibility probe to succeed, and `sd-review-local`
additionally requires a supported flag. The accurate claim is that **a
compatible installed CLI runs with no consent check** — a stricter capability
gate is still not a consent gate.

Observed live while filing `08-07-plugin-review-provider-lanes`: the planning
lane ran twice against that task's own `prd.md`, sending it to `codex exec`,
because the CLI happened to be installed. The reviews were useful. Nobody was
asked.

## Precedent to reuse, not re-litigate

`08-07-plugin-review-provider-lanes` requirements 15-22 already settle the
shape of consent for this repository, and this task adopts them rather than
inventing a second system:

- consent is per provider, and absent configuration resolves to **not
  selected**, never to selected;
- the per-machine layer lives outside the repository, under the existing user
  state root `SD_AI_COMMAND_PACK_STATE_HOME` (`sd_ai_command_pack_lib.py:116`,
  resolved through `resolve_state_root` at `:248`), because a tracked,
  fleet-propagated file cannot express one person's choice without propagating
  it to every consumer;
- an installed-but-unconsented tool is reported distinctly from an absent one;
- `policy.allowedDataHandling` stays an organizational prohibition rather than
  the consent switch.

Where that task's mechanism is expressed as `review.json` provider fields, this
one is expressed in shipped skill and contract prose. The **decision** is
shared; the surface differs.

## Requirements

### Consent

1. Each lane requires a consent signal in addition to its existing capability
   probe. Both must pass for the lane to launch; neither alone is sufficient.
2. Absent consent resolves to the lane's **existing skipped path**, not to an
   error, a prompt, or a blocked run. Both lanes already define that path —
   `sd-review-local` reports `Codex: skipped (CLI unavailable or incompatible)`
   and the contract reports `Codex: skipped` or `Codex: failed` with a reason —
   so this adds a reason, not a mechanism.
3. Consent is recorded per machine, under the existing user state root named
   above, and never in a tracked file that fleet propagation would carry to
   other consumers.
4. Consent is **per lane**. A single global "external reviewers" switch is
   forbidden, and so is one shared per-tool record: consenting to planning
   review is not consenting to ship diffs from a different command, even though
   both reach the same vendor. A lane added later inherits nothing.
5. The consent signal is concretely specified before implementation, because
   "consent is recorded" is otherwise unfalsifiable. `resolve_state_root`
   returns a directory and nothing more (`sd_ai_command_pack_lib.py:248`), and
   the surface footprint below contains no runtime consent helper to call. The
   task must define the file path under the state root, its schema and lane
   keys, the reader, and how consent is granted and revoked.
6. Reading the consent record **fails closed**. Missing file, unparseable
   content, unexpected schema version, unreadable permissions, or a path that is
   a symlink or non-regular file all resolve to *no consent* — never to an error
   that blocks the run, and never to an optimistic grant.
7. Consent scope over repositories is explicit. A record under the user state
   root is machine-wide by construction, so the task states whether granting
   consent once enables the lane in **every** repository on that machine or only
   in named ones. Machine-wide is defensible; arriving there by accident is not.

### Reporting

8. *Skipped because not installed*, *skipped because incompatible*, and
   *skipped because no consent was recorded* are distinguishable in the
   report. A reader must not have to guess whether the CLI is missing or merely
   unconsented, because the remedies differ.
9. The existing rule "Do not claim Codex approval when its optional CLI lane is
   skipped or fails" extends unchanged to a no-consent skip. A skipped lane
   never becomes evidence of review.
10. When `codex` is installed and compatible but unconsented, the report emits
    one advisory line naming what would enable it. Consent that nobody can
    discover is indistinguishable from a removed feature. Advisory only: never a
    prompt, never a blocker.

### Scope of the change

11. The host's own adversarial review remains mandatory and unchanged. This task
    gates the Codex lane, not the review obligation; a run without Codex still
    performs the host review the contract requires.
12. Source and `templates/` twin mirrors change together. The gating text lives
    in both, and a change to one alone is drift the release gates are built to
    catch.
13. Generated command surfaces and the tests that assert this behaviour are
    updated in the same change: `.github/scripts/generate-command-surfaces.py`,
    `tests/test_claude_planning_review.py`, `tests/test_review_local.py`, and
    `tests/test_surface_generation.py` all encode the current
    capability-only gate.

## Surface footprint

`git grep -l "command -v codex" origin/main` returns 15 paths outside
`.trellis/tasks/`, one of which is a journal entry rather than a surface. The
14 real ones:

```text
.agents/skills/sd-review-local/SKILL.md
.claude/commands/sd/review-local.md
.claude/sd-ai-command-pack/planning-adversarial-review.md
.claude/skills/sd-review-local/SKILL.md
.github/scripts/generate-command-surfaces.py
.trellis/spec/frontend/adapter-guidelines.md
docs/SD_AI_COMMAND_PACK.md
templates/.agents/skills/sd-review-local/SKILL.md
templates/.claude/commands/sd/review-local.md
templates/.claude/sd-ai-command-pack/planning-adversarial-review.md
templates/docs/SD_AI_COMMAND_PACK.md
tests/test_claude_planning_review.py
tests/test_review_local.py
tests/test_surface_generation.py
```

`.claude/rules/sd-planning-adversarial-review.md` does not contain the probe
text but is what makes the planning lane mandatory, so it belongs in the change
set even though the grep misses it. Enumerate from the repository rather than
from this list when implementing — the list is a snapshot, and the point of
counting was to establish that this is a mirrored-surface change with
generation and test gates behind it, not a one-file edit.

## Acceptance criteria

- With `codex` installed, compatible, and no consent recorded: neither lane
  launches a `codex` process, and both report a skip naming absent consent
  rather than absent capability.
- With `codex` installed, compatible, and consent recorded: both lanes behave
  exactly as they do today.
- With `codex` absent and consent recorded: both lanes report the
  not-installed skip, unchanged from today.
- A planning run that skips Codex for lack of consent still performs the host
  adversarial review, and still refuses to proceed past an unresolved blocking
  concern.
- No skipped lane — for any of the three reasons — is reported or summarized as
  Codex approval.
- Consent recorded on one machine does not appear in any tracked file and does
  not reach another consumer through fleet propagation.
- Consent for one lane does not enable the other, and no single record enables
  both.
- A consent record that is missing, unparseable, wrong-schema, unreadable, or
  not a regular file yields *no consent* and a successful run, never an error
  and never an optimistic grant.
- Whether consent is machine-wide or per repository is stated in `design.md`
  with a rationale, and the implemented behaviour matches that statement.
- Source and `templates/` copies are identical after the change, and the
  surface-generation and review tests pass against the new gate.

## Open decisions

**Whether per-lane consent is too granular — resolved: no, keep it per lane.**
A shared per-tool record was considered on the grounds that both lanes reach one
vendor and one egress destination. It is rejected because the lanes send
different things at different times: the planning lane sends planning artifacts
during ordinary task editing, and `sd-review-local` sends diffs during an
explicit review. An operator may well want the first and not the second, and a
shared record makes that inexpressible. Requirement 4 is normative; this entry
records the rejected alternative so it is not reopened.

**Whether an unconsented lane should be silent or advisory by default.**
Requirement 7 specifies advisory. If that proves noisy on machines where the
CLI is installed for unrelated work, the fallback is to emit it once per
repository rather than per run, never to drop it entirely.

**Whether the planning contract's mandatory framing should change.** Today the
rule file makes the contract apply to ordinary planning work. Gating the Codex
lane on consent does not require relaxing that, since the host review is what
the contract mainly obliges. Recommendation: leave the mandate alone and gate
only the lane.

## Out of scope

- The `codex` local review **provider** entry, owned by
  `08-07-default-local-review-lanes` — whose R1 and AC5/AC6 contradict opt-in
  as written, flagged on that PR and recorded in
  `08-07-plugin-review-provider-lanes`.
- The provider-side opt-in mechanism itself, owned by
  `08-07-plugin-review-provider-lanes`.
- The adversarial-review round budget, owned by
  `08-07-codex-review-round-budget`.
- Deprecating, removing, or rewriting `sd-review-local`. This task gates its
  Codex lane; whether that skill should still ship is a separate question.
- The planning lane's prompt fragility. Its first invocation while filing
  `08-07-plugin-review-provider-lanes` returned a Trellis triage question
  instead of a review, because the repository's own SessionStart rule reached
  the subprocess. That is a real defect and a different one; a consent gate
  neither causes nor fixes it.
