# Convert the canary cohort to thin mode and prove revert

Child 3 of `08-09-thin-migration`.

## Authorization and operator answers

**2026-08-12 — cohort authorized.** The user authorized the canary cohort
rollout (`platypeeps/rwbp-coordinator`, `platypeeps/loadsmith`,
`platypeeps/hoa-manager`) in session, after being told the conversion
mutates those three repositories. This closes the first acceptance
criterion. It does not extend to post-canary, per the paragraph below.

**2026-08-15 — campaign re-authorized at 0.71.11, and widened to consumer
product code.** Asked how far to take the conversion given the measured gates
below, the user chose "refresh + rewrite + convert": refresh the three canaries
to the current pack version, **rewrite their own blocker citations in
consumer-owned code**, then convert, flip the registry, and execute the revert
proof. This is a deliberate widening past the 2026-08-12 authorization, which
covered conversion plus an installer-managed refresh. It authorizes editing
product code in `rwbp-coordinator`, `loadsmith`, and `hoa-manager` only, and
nothing in any other consumer.

**2026-08-15 — measured state, superseding the 0.71.2 figures below.** Every
number in the original text was taken at pack 0.71.2. The pack is now 0.71.11.
Re-measured today:

| gate | measured | PRD's assumption |
|---|---|---|
| canary payload | all three `0.71.6`, `refresh-required` | step 0 assumed a refresh away |
| machine scope | `0.71.2` plugin and payload against target `0.71.11` | requirement 8, recorded satisfied at 0.71.2 |
| pack-owned citations | **15 `packDefects` per consumer**, identical by file and text, six `repo-native` surfaces — of which the conversion already repoints 14 | child 2b recorded as shipped |
| consumer citations | rwbp-coordinator 49 / loadsmith 50 / hoa-manager 34, across 8 / 5 / 9 files | requirement 1 step 1 |
| verdict | **`blocked` for all three** | — |

The 15 pack-owned citations are the finding that changes the plan: `decide()`
(`scripts/sd-ai-command-pack-thin-resweep.py:1773`) returns `blocked` on a
non-empty `packDefects` bucket, so they would block all three canaries even
with every consumer-owned citation rewritten.

**Review round 2 found the diagnosis inverted.** The first reading — the pack
ships broken text, so fix the text — is wrong. The conversion already repoints
14 of the 15 (`installer/thin.py:675` exists for exactly this population;
executed, it takes loadsmith's six files from 17 citations to 1). The pack's
fat wording is *correct*: a fat consumer really does have those scripts. What
is wrong is that the resweep judges pre-conversion bytes while `--thin` demands
a `clear` verdict, so **no consumer in the fleet can convert today** —
this task is simply the first to try. The fifteenth citation is a genuine
defect in one rewrite rule. Design D2b and D2c; phase 0 is two code changes and
no template edits.

Child 2b is not re-opened and is not at fault: its acceptance criteria measured
whether the cited paths **resolve**, which is a different property from whether
they are **cited**, and the gate that now governs did not exist in its form
then. See `design.md` D0a.

Of the 133 canary blockers exactly **one** is a bare basename, so 0.71.11's
kept resolver path helps by giving the rewrite a surviving target, not by
clearing citations on its own.

**2026-08-12 — fleet refresh scope widened, separately.** The canaries all
hold stale payloads, so requirement 1 step 0 cannot be satisfied without a
refresh first. Asked whether to refresh only the cohort or the whole fleet,
the user authorized refreshing **all eight consumers** to 0.71.2. That is a
deliberate widening beyond this cohort and covers the *refresh only*;
conversion stays scoped to the three canaries named above.

**2026-08-12 — requirement 3, operator answers.** `sven.delmas`, the
operator working in these repositories, was asked which of the three
consumers run Codex. Their answers:

- `rwbp-coordinator` — **runs codex**
- `loadsmith` — **runs codex**
- `hoa-manager` — **runs codex**

The user answered that they run Codex in some or all three; absent a
per-consumer split, all three are recorded as `runs codex`, which is the
conservative reading — it demands more of the plan, not less. Per
requirement 3 this is not a blocker but a precondition: each of these
consumers requires **confirmed machine provisioning before conversion**,
recorded on this line when confirmed.

**Machine provisioning confirmed 2026-08-12**, which is the precondition
`runs codex` attaches to all three lines above. It was not satisfied when
the answers were recorded and was brought up in two steps:

- `install.py --machine` — 115 files (114 owned-current, 1 owned-stale);
  receipt moved from 0.71.1 to 0.71.2, payload
  `sha256:25367a0070eebb3a8db618803a82f3987d6c7f4d503a03ddeeb5d1caa44758ae`.
- `claude plugin marketplace update sd-ai-command-pack` then
  `claude plugin update sd@sd-ai-command-pack` — from 0.71.1 to 0.71.2. The
  marketplace refresh alone does not move an installed plugin, and
  `plugin install` reports "already installed" rather than upgrading.

Verified after both: `machineScope.state: installed`,
`packVersion: 0.71.2`, `pluginVersion: 0.71.2`, `comparison: "current"`,
against `targetPackVersion: 0.71.2`.

*Correcting a claim recorded earlier in this session:* the intermediate
reading `comparison: "current"` at 0.71.1 was **not** a reporting defect.
`comparison` relates the plugin to the machine payload, not to
`targetPackVersion`; at 0.71.1/0.71.1 it was correct, and it moved to
`skew` the moment the machine reached 0.71.2 alone. Nothing here belongs
to `.trellis/tasks/08-09-machine-status-copy-unavailable`.

**Superseded by the authorization above, retained for provenance.** This
task mutates
repositories outside `sd-ai-command-pack`: `platypeeps/rwbp-coordinator`,
`platypeeps/loadsmith`, `platypeeps/hoa-manager`. The coordinator's GitHub
owner is `platypeeps` (`docs/fleet/consumers.json:28`, and its `origin` is
`git@github.com:platypeeps/rwbp-coordinator.git`); only its *local
checkout path* is `~/repos/rwbp/`. R13 changed this line to `rwbp/` on the
strength of that path and R14 demonstrated the repository does not exist
under that owner — the path and the slug are different facts. The autonomous
work-loop's run-level authority does not extend to them. Authorization
is per cohort; authorizing this cohort does not authorize post-canary.

Also requires children 1, 2, and 2b shipped. Child 2b is not optional
sequencing: until the pack's own surviving surfaces stop citing removed
paths, every consumer's resweep returns `packDefects` and `--thin`
refuses. Measured 2026-08-10: 16 such hits in 7 files in all three canary
consumers, which still carry the pack's own PR template.

## Deliverable

The three canary consumers converted to thin mode in the registry's
`sequential` cohort order (rwbp-coordinator, loadsmith, hoa-manager),
each by one consumer PR plus the pack-side `mode` flip, and one executed
revert-and-restore proof.

## Requirements

1. Per consumer, in order: record the operator's answer to the
   global-Codex question below **in this file**, run the resweep against
   that consumer's exact HEAD **and clean worktree**, act on a `clear`
   verdict only,
   run `--thin`, open the consumer PR, land it green, then land the pack
   PR carrying that consumer's `mode: thin` row in
   `docs/fleet/consumers.json`. **The registry row is written by `--thin`,
   not by hand afterwards**: one invocation writes both roots, which is
   why it refuses unless both are writable (child 1's `design.md`). The
   two edits then travel in two pull requests and land in that order. The
   window between them — tree thin, registry row still `fat` — is the
   pin-vs-mode skew the parent design accepts and `sd-status fleet`
   reports.
   The literal sequence, per consumer, with `<consumer>` its registry
   name and `<path>` its checkout — R14 found this file describing the
   steps without naming a single command, which is not an executable
   plan:

   ```bash
   # 0. the consumer must already hold the current payload (R19-C2):
   #    every one of the eight receipts is missing at least one shipped
   #    target today, and conversion computes its residual from the
   #    receipt while --check computes it from the source, so a stale
   #    consumer converts cleanly and fails --check immediately.
   .venv/bin/python install.py <path> --check --json   # state must be current
   # 1. exact head, clean tree, verdict written to a file
   git -C <path> status --porcelain          # must be empty
   bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
     scripts/sd-ai-command-pack-thin-resweep.py --repo <path> \
     --consumer <consumer> --out /tmp/<consumer>-verdict.json --json
   # 2. convert, both roots, gated on that exact verdict file
   .venv/bin/python install.py <path> --thin \
     --resweep-verdict /tmp/<consumer>-verdict.json
   # 2b. regenerate the KB ignore block from the machine-installed script
   ~/.agents/bin/sd-ai-command-pack-update-spec-kb.py --if-present
   # 2c. confirm nothing survives in this consumer's own PR template
   bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
     scripts/sd-ai-command-pack-thin-resweep.py --repo <path> \
     --consumer <consumer> --json
   # 3. consumer PR from <path>, then the pack PR carrying the mode row
   ```

   **Steps 2b and 2c are not optional and not covered by the conversion.**
   Both are invisible in a conversion diff that otherwise looks finished,
   which is why they are written here rather than left to memory. Each has
   a distinct reason, measured 2026-08-11 against
   `docs/fleet/surface-partition.json` and `installer/conversion.py`:

   - **2b, the KB refresh.** `.gitignore` has **no partition row**, so
     `classify_target` sends it to `block_strip` rather than `keep`
     (`installer/conversion.py:178`). Child 2b's install-time rewrite runs
     only over `plan.keep`, so it never reaches this file. An existing
     consumer's `.gitignore` therefore keeps the banner written by whatever
     KB-script version it last ran — and every consumer's names
     `scripts/sd-ai-command-pack-update-spec-kb.py`, a path the conversion
     deletes. Nothing in the conversion clears it; only re-running the
     script does, because only the script rewrites its own block. Skipping
     this leaves one `packDefect` per consumer and the resweep will say so.
   - **2c, the consumer's own PR template.**
     `.github/PULL_REQUEST_TEMPLATE.md` *is* `repo-native`, so conversion
     does repoint it — but only the citation forms `THIN_PROFILE` matches.
     Three consumers (`mezmo_benchmark`, `sd-github-review`,
     `anomaly-metric-creator`) have taken this file over and own their own
     wording, which is why their baseline is 15 hits in 7 files against the
     other five consumers' 17 in 8. Consumer-authored phrasing outside the
     profile's patterns survives the rewrite. The resweep is the check, not
     a reading of the diff; repoint whatever it still reports, in this same
     consumer PR.

   The verdict is a file rather than a fresh in-process check because the
   two must be the same measurement: `--thin` verifies the verdict's
   recorded bindings still describe the tree in front of it and refuses
   otherwise. If the consumer's HEAD or worktree moved between the two
   commands, re-run step 1. An abandoned conversion leaves both roots
   uncommitted: `git -C <path> checkout -- .` and
   `git checkout -- docs/fleet/consumers.json` restore them, and the next
   attempt starts again at step 1.

2. A `blocked` verdict stops that consumer's conversion and is reported
   with its reasons. It is not worked around. **It stops the whole
   canary cohort**, matching the existing rollout contract: the wave
   planner halts starts and holds merges on any unsettled terminal
   canary (`scripts/sd-ai-command-pack-fleet-wave-plan.py:200`) and
   `.trellis/spec/backend/manifest-and-filesystem.md:1778` permits
   progression only through successful canaries absent an explicit
   parked-canary override. Continuing past a blocked canary would need
   that override, invoked deliberately — not assumed.
3. **Every canary's Codex users are served by the machine install before
   conversion.** *Rewritten 2026-08-12 (pack 0.71.2). The requirement
   it replaced demanded a per-consumer declare-or-remove choice; that
   choice no longer exists, and the paragraphs below record why, because
   the reasoning is what changed and not merely the numbers.*

   Marker detection is unchanged. Measured 2026-08-10 and true of all
   three canaries: each has a **populated** `.codex/` directory, and each
   registry row declares only `claude`, `gemini`, `github`, `opencode`.
   R14 corrected the rule a third time: directory *existence* is neither
   necessary nor sufficient. An empty `.codex/` is not evidence of
   anything; a directory holding files is, as is a `$CODEX_HOME`
   reference, a pi adapter file, or a `codex exec`-family CLI invocation
   in command position anywhere in the tree. R13 had already removed an
   exemption for Trellis-authored paths. Files the pack itself installed
   are excluded by proven ownership, not by receipt membership.
   `rwbp-coordinator`, `loadsmith`, and `hoa-manager` also reference
   `$CODEX_HOME` in surviving files, and the first two invoke the `codex`
   CLI in their own surviving guidance.

   **Those markers are advisories now, not blockers.** The blocker's
   stated reason was that `retainVendoredFor` intersects the consumer's
   *declared* platforms, so conversion deletes `.agents/**` out from
   under a Codex user with nothing to replace it — Codex being unable to
   consume the machine-installed plugin. The second half is true and
   irrelevant: the `.agents` families belong to the machine *installer*,
   not to the Claude plugin. An executed probe
   (`.trellis/tasks/archive/2026-08/08-09-codex-home-skills-family/research/codex-skills-resolution-probe.md`)
   shows Codex merges project-root `.agents/skills` with
   `$HOME/.agents/skills`, which the machine installer writes. Codex left
   `retainVendoredFor` in 0.71.2, so declaring it retains nothing and the
   demand was for a declaration that changes no plan.

   **The residual figures are the same on every branch.** Declaring
   `codex` no longer moves the plan: it stays 166 delete / 13 retire / 27
   keep for all three canaries, **179 removals**, and the "no vendored
   payload beyond `repo-native` + `consumer-config`" criterion describes
   every canary without exception. The superseded text put the declared
   branch at 91 delete / 102 keep and 104 removals, a 75-target
   difference that no longer exists. Acceptance still compares the
   executed tree against **that consumer's own receipt**, which is now
   the only branch there is.

   **What the operator question is now for.** A consumer whose Codex use
   is entirely global — `~/.codex/`, a CLI flag, a CI environment
   variable — still leaves no repository-visible marker, and the resweep
   still cannot close that. What changed is what the answer decides.
   Conversion no longer removes a surface Codex needs; it **transfers**
   that surface from the vendored copy to `$HOME/.agents/skills`. So the
   question is no longer "will this break a Codex user" but "has the
   machine install actually run for whoever works here". The parent
   contract already requires machine provisioning before conversion; for
   a Codex user that precondition is load-bearing rather than a
   formality, because the vendored copy it replaces is the one Codex is
   reading today.

   **This is an acceptance gate, not advice (R17).** Requirement 1's
   sequence advanced on a `clear` resweep alone, so a careful implementer
   could execute the whole plan without the answer ever existing. The
   gate: for each canary, a dated line in this file naming the consumer,
   who was asked, and one of `runs codex`, `does not run codex`, or
   `unanswered`. `runs codex` no longer selects a branch — it requires
   confirmed machine provisioning for that consumer's Codex users before
   conversion, recorded on the same line. `unanswered` blocks that
   consumer, because an unverified machine install plus a live Codex user
   is the one configuration that loses a working surface.
4. One consumer-authored blocker is already measured and belongs to this
   task rather than to child 2b: `rwbp-coordinator/.prism/rules.json:55`
   is a live Prism **required** rule naming three removed paths. Its text
   is not in the pack's `templates/.prism/rules.json`, so it is
   rwbp-coordinator's own drift, and the partition keeps `.prism/` as
   `shared / consumer-config` — conversion leaves the broken rule
   behind unless the consumer PR fixes it. Repoint it in the same PR that
   converts rwbp-coordinator, before the resweep can return `clear`.
   `.prism/rules.json` is agent-executed, not inert data: round 10
   reclassified it from `advisories` to `blockers` for exactly that
   reason.
5. Each conversion deletes the set enumerated **from that consumer's
   own installed-targets receipt** and classified through the partition
   (parent contract C-B) — measured today at **179 removed targets per
   consumer under the recorded platform choice each canary has now**,
   being 166 machine files plus 13 retired files. That number no longer
   has a second branch: 0.71.2 removed `codex` from `retainVendoredFor`,
   so declaring it retains nothing and 179 holds either way. The
   superseded text put the declaration branch at 91 deleted plus 13
   retired — 104 removals, from 75 further retained machine targets (49
   `.agents`, 25 `scripts`, one document) — which does not reproduce.
   A canary's removal set is still recomputed from its own receipt under
   its own recorded platforms rather than assumed. The four
   special cases are not part of that number and must not be added to it:
   three generated bookkeeping files are **kept and rewritten**, and
   `.gitignore` **survives** with one exact marker block removed. Saying
   "plus the four special cases" described 183 deletions and overstated
   destructive scope by four files. It **keeps** the `repo-native` and
   `consumer-config` slices. The counts are recomputed per consumer, not
   assumed from this line.
6. The revert proof executes `install.py TARGET --revert-thin` on one
   converted canary, confirms CI stays green in the reverted state,
   then re-converts. Reading the revert code is not the proof.
7. `sd-status fleet` is the acceptance instrument, not a summary
   written by hand.
8. **Machine provisioning precedes conversion** (parent contract C-C2).
   Conversion removes a repository's agent surfaces on the assumption
   the machine supplies them; for anyone without the plugin installed
   and the machine installer run, it is indistinguishable from
   deletion. Before the first canary mutation, confirm through
   `sd-status`'s machine scope that the plugin and machine receipt are
   present, and state the prerequisite to whoever works in those
   repositories.

## Acceptance criteria

- [ ] Explicit user authorization for this cohort recorded in this file
      with its date before any consumer mutation.
- [ ] **Added 2026-08-15, rewritten the same day after review round 2.** A fat
      consumer's resweep reports `packDefects: 0`, measured against the three
      canaries untouched at 0.71.6. The count today is 15 per consumer, and
      **14 of those 15 are repointed by the conversion itself** — the pack's
      fat wording is correct and is not edited. The 15 block only because the
      scanner judges pre-conversion bytes while `--thin` requires the verdict
      the conversion is authorized by. See design D2b. The fifteenth is a real
      defect in the skills-glob rewrite (design D2c).
      This is the criterion that says conversion is possible **at all**: as
      measured, no consumer in the fleet can reach a `clear` verdict.
- [ ] **Added 2026-08-15.** Each canary's own citations are rewritten to a
      surviving path or an unambiguous command, evidenced by that consumer's
      resweep reporting `blockers: 0` on a clean tree. Measured starting
      points: 49 / 50 / 34.
- [ ] All three canaries satisfy `installMode == "thin"`, `pin.state == "present"`, and
      `pin.version == machineScope.packVersion` in
      `sd-status fleet --json`; plus `machineScope.state == "installed"`
      and `machineScope.comparison == "current"`. "No skew row" is not
      used: fleet mode exits zero on skew and its follow-up rows are
      untyped prose, so it cannot fail when it should.
- [ ] Each canary's CI is green post-conversion with zero pack CI steps,
      verified by grepping that consumer's `.github/workflows/` at its
      post-merge HEAD.
- [ ] No vendored payload remains in any canary beyond what that
      consumer's **recorded platform choice** retains — the `repo-native` +
      `consumer-config` slices, plus the whole shared machine slice for a
      consumer that declares a platform still carried in
      `retainVendoredFor` (today only `pi`; no canary declares it) —
      verified per consumer by comparing its post-conversion tree against
      **its own pre-conversion installed-targets receipt** and the plan
      derived under that choice. A comparison against the current
      partition alone would pass while orphan files from an older pin
      survive.
- [ ] Each canary's Codex advisory is recorded rather than cleared: since
      0.71.2 the marker forces no per-consumer choice, because declaring
      `codex` retains nothing. Evidence is the post-conversion resweep
      reporting the marker under `advisories` with an empty `blockers`
      bucket for that consumer, plus the operator answer requirement 3
      requires — confirmed machine provisioning for any canary that runs
      Codex. A canary that still shows a marker under `blockers` is a
      partition or scanner defect, not a declaration decision.
- [ ] `rwbp-coordinator/.prism/rules.json` names no removed path at the
      converted HEAD, verified by the resweep returning `clear` for that
      consumer rather than by reading the file — the rule text moved once
      already and a hand check would re-measure the old bytes.
- [ ] Machine scope verified present (plugin + machine receipt) before
      the first canary mutation, with the `sd-status` output recorded.
- [ ] Requirement 1 steps 2b and 2c executed per canary, evidenced by a
      post-conversion resweep reporting zero `packDefects` for that
      consumer. An aggregate "conversion looked clean" does not close this:
      the KB block and a consumer-owned PR template are precisely the two
      surfaces a conversion leaves untouched while appearing complete.
- [ ] The revert proof was executed on a named canary at a named
      commit, CI stayed green, and the only residue was the
      `enabledPlugins` disable marker. Re-conversion ran a **fresh
      exact-head resweep** against the reverted tree first: the revert
      changes the tree, so the verdict that authorized the first
      conversion does not authorize the second.
- [ ] `make release-prep` passes on this repo after the registry flips
      — not `make check` alone. Each `mode` flip changes the
      fleet-manifest digest pinned into
      `docs/fleet/candidate-validation.json`
      (`scripts/sd_ai_command_pack_fleet_lib.py:766`), so `make check`
      cannot pass until release-prep refreshes the ledger.
