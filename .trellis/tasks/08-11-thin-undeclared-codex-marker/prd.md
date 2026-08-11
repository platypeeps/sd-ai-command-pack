# Undeclared codex usage from a pack-shipped doc blocks every conversion

## Goal

Resolve the `undeclared codex usage` `packDefect` that the resweep
reports for all eight registered consumers, so `packDefects: 0` becomes
reachable and children 3–5 of `08-09-thin-migration` can convert.

This task owns only that defect. The seven stale-path surfaces are
`08-10-thin-prompt-surface-repoint`, whose design is converged and whose
scope deliberately excludes this.

## Evidence

Measured 2026-08-11 against all 8 consumers, with the scanner from the
archived sibling task:

```bash
.venv/bin/python .trellis/tasks/archive/2026-08/\
08-10-thin-conversion-tooling/research/fleet-blocker-scan.py --out /tmp/scan.json
```

Note the scanner does **not** run from that path unmodified: it computes
`ROOT = Path(__file__).resolve().parents[4]`, which was correct at its
live location and is wrong two levels deeper under `archive/2026-08/`. It
was run from a copy with `ROOT` pinned. Fixing the scanner is not this
task's job, but nobody should lose an hour rediscovering it.

Every consumer reports the same synthetic row:

```
file: codex   line: null
detail: undeclared codex usage: the codex CLI is invoked in 1 surviving
        file(s), e.g. .claude/sd-ai-command-pack/planning-adversarial-review.md
```

Totals: `packDefects` **17 in 8 files** for the five consumers carrying
the pack's PR template, **15 in 7** for `mezmo_benchmark`,
`sd-github-review`, and `anomaly-metric-creator`. Exactly one hit in one
file more than the seven-surface baseline, in every consumer.

Three facts establish ownership:

- The cited file is **pack-shipped**: `manifest.json:124` maps
  `templates/.claude/sd-ai-command-pack/planning-adversarial-review.md`
  to `.claude/sd-ai-command-pack/planning-adversarial-review.md`. It
  reached consumers on 2026-08-06 (`4f27104f`).
- **No consumer declares `codex`.** All eight declare exactly
  `["claude", "gemini", "github", "opencode"]` in
  `docs/fleet/consumers.json`.
- The detector is newer than the surfaces it flags. `undeclared codex
  usage` landed 2026-08-10 in the tooling task's rounds 12–14 and reached
  `main` on 2026-08-11. The earlier 16/7 measurement was not wrong when
  taken; the detector improved under it.

So this is not drift and not a consumer defect. The pack ships a document
instructing an agent to run `codex exec`, the conversion keeps that
document, and the resweep correctly observes codex usage in a repository
that never declared codex.

## The tension this task has to resolve

The detector is not obviously wrong. A surviving file really does tell an
agent to run the codex CLI, and conversion is *designed* to block on
undeclared platform usage — that rule exists so a conversion cannot
silently delete a platform's surfaces out from under a consumer using it.

But the usage here is a pack-authored description of an **optional
review lane**, not the consumer's own toolchain. A consumer that has
never installed codex still carries the file. Whether that should count
is the question, and it is a real one rather than a bug to be patched
away.

## Options — option 5 chosen 2026-08-11

Recorded so the design phase starts from evidence rather than a blank
page. Each has a named cost. Options 1-4 were enumerated before design
and are all rejections; option 5 was added during design and is the
chosen resolution, with `design.md` D2 carrying the rejection reasons.

1. **Declare `codex` for the eight consumers.** Cheapest edit, worst
   outcome: `retainVendoredFor` carries `["codex", "pi"]`, so declaring
   codex retains `.agents/**` rows as vendored and partly defeats the
   thin conversion the declaration was meant to unblock.
2. **Narrow the detector** to ignore pack-shipped documentation. Belongs
   to the resweep's owner, and weakens a gate whose purpose is to catch
   exactly this shape. Needs an argument for why pack docs are different
   that does not also excuse real usage.
3. **Stop shipping the contract to consumers**, or ship it machine-scope
   only. Consumers do run the planning flow the contract governs, so this
   trades a conversion blocker for a capability loss and must show the
   capability is genuinely not needed repo-locally.
4. **Rewrite the contract** so the lane is described without a literal
   invocation. Clears the scan, makes the document worse, and is the
   option most likely to be chosen for the wrong reason.
5. **Split the document and ship the lane conditionally** — added
   2026-08-11 during design, and **chosen**. The host-side contract (80
   of 129 lines) keeps shipping to every consumer; the Codex lane (lines
   41–89) moves to `templates/.codex/sd-ai-command-pack/`, under a
   manifest row carrying `platform: "codex"`. It is not a sibling of the
   host contract — the `.codex/` placement is load-bearing, because
   `.claude/sd-ai-command-pack/**` is an unconditional `consumer-config`
   override that would break the conversion on receipt drift
   (`design.md` D1). The row reaches only repositories that declare the
   platform **or pass `--all` or `--platform codex`**; a normal install
   in an undeclared repository does not select it. None of the eight
   declares the platform, so the marker disappears without weakening the
   detector, degrading the document, or retaining the shared machine
   slice. It was not in the original four because it
   depends on a measured fact this PRD did not have:
   `ACTIVE_TRELLIS_PLATFORM_MARKERS` has no `codex` entry, so a
   `codex` row is never auto-selected even in the eight repositories
   that *do* have a populated `.codex/` directory. Evidence and the
   rejected alternatives are in `design.md`.

## Requirements

1. Decide between the options above with evidence, and record the
   rejected ones and why — the same discipline the sibling task used.
2. Whatever ships, `packDefects` for the `codex` row reaches zero for all
   eight consumers, measured, not reasoned about.
3. No consumer loses a capability it uses today without that loss being
   stated explicitly and accepted.
4. If the resolution changes install semantics or the delete set, it
   carries its own review — contract C-B is not renegotiated in passing.
5. Shipped-payload changes carry a `manifest.json` bump and a matching
   CHANGELOG heading.

## Non-goals

- The seven stale-path surfaces. Those are
  `08-10-thin-prompt-surface-repoint`.
- Fixing the archived scanner's `parents[4]` bug. Worth a follow-up, not
  worth blocking on.

## Acceptance criteria

- [ ] The chosen option is recorded with its evidence, and the **four**
      rejected options each carry a stated reason. Four, not three: the
      chosen resolution is option 5, added during design, so all four of
      the originally enumerated options are rejections.
- [ ] `packDefects` reports no `codex` row for any of the eight
      consumers, measured with the scanner.
- [ ] The seven-surface count is unchanged by this task — it neither
      fixes nor breaks them, so a combined run with the sibling task
      reaches zero and this one alone does not.

> **The two criteria above have a fleet half this task cannot close, and
> that is stated here rather than discovered at completion.** Both need a
> consumer *carrying this version*. None is on it, and putting one there
> mutates eight repositories this task holds no authorization for — the
> exact boundary `08-10-thin-prompt-surface-repoint` hit, where four
> criteria had to be restated at completion because they had been written
> as if the fleet were in scope. Writing the boundary down now avoids
> repeating that.
>
> What this task measures: both on the disposable fixture, plus the
> mechanism proof (runs 1–5 and 8 of `implement.md`) that the row is not
> selected without the declaration. What children 3–5 measure: the fleet
> halves, through each consumer's pre-conversion resweep, which already
> gates on `packDefects` reaching zero. The fixture is explicitly **not**
> a stand-in for the fleet — it cannot see a consumer installed with
> `--all`, nor one whose developers run Codex without declaring it, and
> both are consumer-specific facts only that consumer's own resweep
> reports.
- [ ] Any capability a consumer loses is named in the PRD and in the
      CHANGELOG entry. Option 5 **does** lose one, and the first draft of
      this criterion said otherwise: the Codex lane is gated by runtime
      probes (`command -v codex`, `codex exec --help`), not by
      `docs/fleet/consumers.json`, so every consumer whose developers
      have the CLI on PATH runs the lane today and stops after the split.
      Three effects get named: that loss, this repository no longer
      installing the appendix into its own tree (`design.md` D4), and all
      eight consumers gaining an `install.py` hint offering
      `--platform codex`, which installs the appendix without recording a
      declaration and thereby re-arms the very `packDefect` this task
      removes (`design.md` D4.1).
- [x] The lane loss above is **accepted by the operator**, recorded with
      a date, before implementation starts. It is a capability decision,
      not an implementation detail, and requirement 3 makes acceptance
      explicit rather than implied by shipping. **Accepted 2026-08-11**,
      after the two alternatives were offered with their prices
      (declaring `codex` fleet-wide, which partly defeats the conversion;
      narrowing the detector, which weakens the gate).

      **The restore path shown with that decision was wrong, and the
      correction goes back to the operator.** It said the lane returns
      with `install.py <repo> --platform codex`. Round 2 refuted all
      three parts: the flag does not declare the platform
      (`fileops.py:184` filters selection only), does not buy the
      75-target retention (conversion reads `entry.get("platforms")` from
      the fleet registry, `install.py:919`), and is refused outright on
      an already-converted consumer (`install.py:1268-1273`) — which is
      every one of the eight, once children 3-5 land. The durable
      restore is a `docs/fleet/consumers.json` declaration; see
      `design.md` D4.1's corrected table. Either form is recorded there and
      in the CHANGELOG rather than in the shipped contract, because
      `--platform codex` carries the `codex` token and would reintroduce
      the marker into the file the split clears.
- [ ] `make check` green; `manifest.json` and CHANGELOG updated if the
      shipped payload changed.

## Blocking relationship

Blocks children 3–5 of `08-09-thin-migration`, jointly with
`08-10-thin-prompt-surface-repoint`. Neither task alone unblocks
conversion: `packDefects` must reach zero, and each task owns a disjoint
part of the count.
