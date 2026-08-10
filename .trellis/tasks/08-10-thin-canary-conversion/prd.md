# Convert the canary cohort to thin mode and prove revert

Child 3 of `08-09-thin-migration`.

**BLOCKED — requires explicit user authorization.** This task mutates
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

1. Per consumer, in order: run the resweep against that consumer's
   exact HEAD **and clean worktree**, act on a `clear` verdict only,
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
   # 1. exact head, clean tree, verdict written to a file
   git -C <path> status --porcelain          # must be empty
   bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
     scripts/sd-ai-command-pack-thin-resweep.py --repo <path> \
     --consumer <consumer> --out /tmp/<consumer>-verdict.json --json
   # 2. convert, both roots, gated on that exact verdict file
   .venv/bin/python install.py <path> --thin \
     --resweep-verdict /tmp/<consumer>-verdict.json
   # 3. consumer PR from <path>, then the pack PR carrying the mode row
   ```

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
3. **Every canary declares `codex` or stops using it, before conversion.**
   Measured 2026-08-10 and true of all three canaries: each has a
   `.codex/` directory, and each registry row declares only `claude`,
   `gemini`, `github`, `opencode`. The rule is unqualified — the
   directory's existence is the marker. R13 removed an exemption for
   Trellis-authored paths under it, because whoever wrote those files
   runs Codex in that repository and the conversion deletes `.agents/**`
   regardless of which tool authored them.
   That is a blocker, not a warning, and the reason is not bookkeeping:
   `retainVendoredFor` intersects the consumer's **declared** platforms
   (parent `design.md:187`), so conversion deletes `.agents/**` out from
   under a Codex user — and Codex cannot consume the machine-installed
   plugin at all, so nothing replaces it. Per consumer, choose one and
   record which: add `codex` to that consumer's `platforms` (turning
   `retainVendoredFor` retention on, and making this the first real
   exercise of a path the parent design calls untested), or remove the
   Codex usage. `rwbp-coordinator`, `loadsmith`, and `hoa-manager` also
   reference `$CODEX_HOME` in surviving files, and the first two invoke the
   `codex` CLI in their own surviving guidance — two further markers that
   clear the same two ways.

   **Declaring `codex` is not the cheap branch, and the residual figures
   change if it is taken.** `retainVendoredFor` is keyed on the *shared*
   platform's disposition, not on `.agents/**`, so declaring Codex retains
   the whole shared machine slice. Measured against all three canaries,
   identically: the plan moves from 166 delete / 13 retire / 27 keep to
   **91 delete / 13 retire / 102 keep** — 75 additional retained targets,
   being 49 `.agents/**` files, 25 `scripts/**`, and
   `docs/SD_AI_COMMAND_PACK.md`. The removal total for that consumer is
   then 104, not 179, and the "no vendored payload beyond `repo-native` +
   `consumer-config`" criterion below does not describe it. Whichever
   branch a consumer takes, its acceptance compares the executed tree
   against **its own receipt under its recorded platform choice**, and the
   choice is recorded in this file before the conversion runs.

   **What no scan can see.** A consumer whose Codex use is entirely
   global — `~/.codex/`, a CLI flag, a CI environment variable — leaves no
   repository-visible marker. The resweep cannot close that and does not
   claim to. Before converting each canary, ask whoever works in that
   repository whether they run Codex against it, and record the answer
   here alongside the marker evidence. An unanswered question is not a
   `clear` verdict.
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
   consumer**, being 166 machine files plus 13 retired files. The four
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
      consumer that declared `codex` (75 further targets, measured) —
      verified per consumer by comparing its post-conversion tree against
      **its own pre-conversion installed-targets receipt** and the plan
      derived under that choice. A comparison against the current
      partition alone would pass while orphan files from an older pin
      survive.
- [ ] Each canary's undeclared-codex marker is cleared by a recorded
      choice — `codex` added to its `platforms`, or the Codex usage
      removed — and the resweep confirms it rather than a hand check. If
      any canary declares `codex`, `retainVendoredFor` retention runs
      against a real consumer for the first time, so its residual is
      compared against that consumer's own receipt, not assumed.
- [ ] `rwbp-coordinator/.prism/rules.json` names no removed path at the
      converted HEAD, verified by the resweep returning `clear` for that
      consumer rather than by reading the file — the rule text moved once
      already and a hand check would re-measure the old bytes.
- [ ] Machine scope verified present (plugin + machine receipt) before
      the first canary mutation, with the `sd-status` output recorded.
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
