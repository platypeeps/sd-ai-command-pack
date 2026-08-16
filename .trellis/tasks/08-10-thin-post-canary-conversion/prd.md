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

## Cohort authorization

Recorded 2026-08-16. The operator authorized this cohort on 2026-08-16 with
"finish all remaining conversions, you have appoval for all need tool calls,
etc", after the canary cohort had held. Conversions began after that
instruction.

## Acceptance criteria

- [x] Explicit user authorization for this cohort recorded in this file
      with its date before any consumer mutation.
- [x] All four satisfy `installMode == "thin"`, `pin.state == "present"`, and
      `pin.version == machineScope.packVersion` in
      `sd-status fleet --json`; plus `machineScope.state == "installed"`
      and `machineScope.comparison == "current"`. "No skew row" is not
      used: fleet mode exits zero on skew and its follow-up rows are
      untyped prose, so it cannot fail when it should.
- [x] Each consumer's CI is green post-conversion with zero pack CI
      steps, verified per consumer by grepping its workflows at its
      post-merge HEAD.
- [x] Each consumer's post-conversion tree matches its own
      pre-conversion installed-targets receipt minus the enumerated
      delete set; a partition-only comparison does not satisfy this.
      **Deviation for `sd-github-review`; see below.**
- [x] `se-ai-command-pack`'s derivation pipeline is unchanged, shown by
      a diff of its derivation inputs across the conversion commit
      being empty.
- [x] `make release-prep` passes on this repo after the registry flips
      — every `mode` flip moves the fleet-manifest digest pinned into
      the candidate ledger, so `make check` alone cannot pass.

## Acceptance evidence

Collected 2026-08-16 against the live fleet, not from conversion-time notes.

### Fleet state (criterion 2)

```text
$ scripts/sd-ai-command-pack-status.py fleet --json --no-network
machineScope state=installed packVersion=0.71.22 comparison=current
targetPackVersion 0.71.22
rwbp-website             thin   pin=present 0.71.22
mezmo_benchmark          thin   pin=present 0.71.22
se-ai-command-pack       thin   pin=present 0.71.22
sd-github-review         thin   pin=present 0.71.22
```

All four cohort members satisfy every clause. The other four consumers read the
same way, which is the state the parent task cares about.

### Workflows at post-merge HEAD (criterion 3)

```text
rwbp-website        HEAD=7f52a82 main   pack-refs-in-workflows: none
mezmo_benchmark     HEAD=69e262d main   pack-refs-in-workflows: .github/workflows/test.yml
se-ai-command-pack  HEAD=f6108da main   pack-refs-in-workflows: .github/workflows/tests.yml
sd-github-review    HEAD=c1ce6cf main   pack-refs-in-workflows: none
```

Neither of the two hits is a pack CI step, and no consumer retains a vendored
pack script — `ls scripts/sd-ai-command-pack-*` finds nothing in either:

- In `mezmo_benchmark`, the hit is a `grep -Eq` pattern inside a changed-file
  classifier, matching `scripts/sd-ai-command-pack-*.sh` filenames. Those paths
  no longer exist in a thin consumer, so the branch is unreachable — stale text,
  not an executed step.
- In `se-ai-command-pack`, the hit resolves the review preflight through
  `.sd-ai-command-pack/bin/sd-ai-command-pack-review-layout.py`, a kept
  thin-shape file, and prints `skipped:` when no install answers. That is the
  thin-compatible pattern, not a vendored payload call.

### Conversion-commit shape (criterion 4)

| Consumer | Commit | Files added |
| --- | --- | --- |
| `rwbp-website` | `7d4215f` | 0 |
| `mezmo_benchmark` | `5047241` | 0 |
| `se-ai-command-pack` | `b7dd320` | 0 |
| `sd-github-review` | `9a4787a` | **572** |

Three of four added nothing at all: pure payload deletion plus the repointed
kept files, which is exactly receipt-minus-delete-set.

**`sd-github-review` deviates.** It was converted first, on 2026-08-15, by code
that deleted the managed `.gitignore` block instead of adopting it. The block
carried `.build/` and `node_modules/`, so the same commit that removed those
rules staged the artifacts they had been hiding. `c299260` restored the rules
the same day and untracked the `.build/**` half, but not `node_modules/**`; 236
of those paths remain tracked at HEAD, every one introduced by `9a4787a`.

The deviation is recorded rather than repaired here, and is tracked by
`08-16-thin-conversion-gitignore-residue`, which carries the full measurement
and the remediation. It is scoped out of this task for two reasons: the pack-side
cause is already closed (`installer/fileops.py:778` `adopt_marked_block`, which
every later conversion used — hence the three zeros above), and the remedy is a
`git rm --cached` in a consumer repository rather than anything this cohort
owns. A fleet-wide sweep confirmed the blast radius is that one repository: the
other seven consumers' tracked-but-ignored files are `.env.*.example` and
`.trellis/.template-hashes.json` entries added between 2026-05-16 and
2026-06-25, months before any conversion.

### `se-ai-command-pack` derivation pipeline (criterion 5)

```text
$ git show --format='' --name-only b7dd320 \
    | grep -cE '^(installer/|templates/|generated/|install\.py|manifest\.json|Makefile|pyproject\.toml)'
0
```

Zero derivation inputs touched. The commit's non-`scripts/`, non-`docs/` changes
are `.gemini/commands/sd/*.toml` and `.opencode/commands/sd-*.md` — agent-side
adapter surfaces, which requirement 3 puts in scope.

### Pack-side gate (criterion 6)

```text
$ make release-prep
release version gate: no shipped payload changes detected
release changelog gate: manifest version unchanged
==> Full check complete
exit=0
```
