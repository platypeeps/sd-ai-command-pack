# Convert the post-canary cohort to thin mode

Child 4 of `08-09-thin-migration`.

**BLOCKED — requires explicit user authorization** for this cohort, and
requires child 3 shipped. This task mutates
`platypeeps/rwbp-website`, `platypeeps/mezmo_benchmark`,
`platypeeps/se-ai-command-pack`, and `platypeeps/sd-github-review`.
Canary authorization does not carry over.

## Deliverable

The four post-canary consumers converted, respecting the registry's
`bounded-parallel` strategy at `maxConcurrency: 2`.

## Requirements

1. Same per-consumer sequence as child 3: exact-HEAD resweep, convert
   only on `clear`, consumer PR green, then the pack-side `mode` flip.
2. At most two consumers in flight at a time, per the registry
   `rolloutPolicy`. The registry is the authority on concurrency, not a
   number chosen here.
3. `se-ai-command-pack` is a special shape: it vendors pack code in
   order to re-ship it. Only its **agent-side** surfaces convert; its
   derivation pipeline is out of scope and continues to consume pack
   releases. Its `candidateChecks` entry carries into the rescoped
   candidate loop rather than being dropped. Converting its derivation
   inputs by mistake is the specific failure this requirement exists to
   prevent.
4. A `blocked` resweep verdict stops that consumer and is reported; the
   remaining consumers continue unless the blocker is fleet-wide.
5. Machine provisioning precedes conversion (parent contract C-C2),
   re-verified for this cohort rather than assumed from child 3.

## Acceptance criteria

- [ ] Explicit user authorization for this cohort recorded in this file
      with its date before any consumer mutation.
- [ ] All four satisfy `installMode == "thin"`, `pin.state == "present"`, and
      `pin.version == machineScope.packVersion` in
      `sd-status fleet --json`; plus `machineScope.state == "installed"`
      and `machineScope.comparison == "current"`. "No skew row" is not
      used: fleet mode exits zero on skew and its follow-up rows are
      untyped prose, so it cannot fail when it should.
- [ ] Each consumer's CI is green post-conversion with zero pack CI
      steps, verified per consumer by grepping its workflows at its
      post-merge HEAD.
- [ ] Each consumer's post-conversion tree matches its own
      pre-conversion installed-targets receipt minus the enumerated
      delete set; a partition-only comparison does not satisfy this.
- [ ] `se-ai-command-pack`'s derivation pipeline is unchanged, shown by
      a diff of its derivation inputs across the conversion commit
      being empty.
- [ ] `make release-prep` passes on this repo after the registry flips
      — every `mode` flip moves the fleet-manifest digest pinned into
      the candidate ledger, so `make check` alone cannot pass.
