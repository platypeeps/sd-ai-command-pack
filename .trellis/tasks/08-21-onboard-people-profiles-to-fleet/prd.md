# Onboard people-profiles to the sd-ai-command-pack fleet

## Goal

Make `platypeeps/people-profiles` a first-class fleet consumer: current pack
version, thin install shape, registered in the fleet manifest with a cohort,
and covered by the same review-invocation policy as every other consumer.

## Context

The request was "install the pack in people-profiles and make it part of the
fleet." The pack is already installed there. What is missing is currency,
shape, and registration.

Measured on `175a8c2`:

| | people-profiles | a registered consumer (hoa-manager) | pack source |
| --- | --- | --- | --- |
| version | 0.55.0 | 0.71.38 | 0.71.40 |
| `mode` | absent | `thin` | n/a |
| hashed files in provenance | 166 | 24 | n/a |
| installed targets | 174 | n/a | n/a |

Two gaps follow. The install is roughly sixteen minor versions behind, and it
is a fat/vendored install: no `mode` pin, and the machine-scope payload is
committed into the repository. Every one of the eight registered consumers is
`"mode": "thin"`. Registering a fat consumer would put a shape into the roster
that the refresh lanes are not built to drive.

### Why the conversion is cheap here, contrary to first appearances

A raw search finds 352 references to `scripts/sd-ai-command-pack-*` across 64
files, which reads like a large rewrite. It is not. Classifying each file
against the install receipt:

- **61 files are pack-owned.** They are replaced wholesale by the refresh, and
  the current payload already adopts the resolver contract.
- **3 files are repo-authored**, one reference each, all prose rather than
  executable guards: `.trellis/spec/backend/quality-guidelines.md`,
  `.trellis/spec/frontend/hook-guidelines.md` [absent: lives in people-profiles; this repository does not carry it], and
  `.trellis/tasks/archive/2026-07/07-25-repository-setup/research/review-risk-disposition.md` [absent: lives in people-profiles; this repository does not carry it].

The repository has no executable guard coupled to the pack at all:
`.github/workflows/ci.yml` [absent: lives in people-profiles; this repository does not carry it] contains no reference to the pack, `~/.agents/bin`,
or `install.py`, and the only path assertion in `tests/test_installer.py` [absent: lives in people-profiles; this repository does not carry it] names
one of the repository's own skills. So step 3 of the documented conversion
order — rewriting guards onto the kept resolver path — reduces to correcting
three documentation citations.

### The Copilot ruleset consequence

people-profiles was deliberately excluded from the fleet-wide removal of the
`copilot_code_review` ruleset rule, on the stated grounds that it is not a pack
consumer and its ruleset is therefore its only Copilot path. Onboarding
retracts that premise. Once `sd-review-pr` owns review invocation here, the
ruleset becomes the same duplicate request it is everywhere else — and worse
than most, because its second ruleset carries `review_on_push=true` and
`review_draft_pull_requests=true`, so it reviews on every push and on drafts,
which is exactly what the fleet integration-only profile suppresses.

## Requirements

- **Follow the documented conversion order.** `docs/FLEET_ROLLOUT.md` fixes
  five steps — ship, refresh, rewrite, resweep, convert — and states why each
  precedes the next. Refresh before rewrite, because a rewrite that lands first
  names a resolver path the consumer does not yet carry. Do not reorder them.
- **The resweep verdict is the gate, not a formality.** `install.py --thin`
  requires `--resweep-verdict` pointing at a `clear` document. A `blocked`
  verdict means conversion stops and the blockers get resolved first; one
  blocker blocks as hard as ninety.
- **The resweep requires a clean worktree.** The repository carries five
  untracked `scripts/*.bak` files, every one named after a pack script.
  `install.py --backup` is documented as saving "a `.bak` copy next to each
  overwritten or deleted file", so these are almost certainly the output of an
  earlier `--force --backup` refresh rather than hand-made edits. They are still
  untracked and still not this task's to delete silently: surface them and get a
  decision. The same mechanism is a live hazard for the refresh itself — it must
  not pass `--backup`, or it re-dirties the tree with up to 86 new `.bak` files
  immediately before the step that demands a clean one.
- **Establish drift before forcing over it.** `--force` overwrites files that
  differ from the pack templates. Whether people-profiles actually carries such
  drift is unmeasured; run `--dry-run` first and reach for `--force` only for
  what a plain refresh leaves behind.
- **Register with a cohort, not just a roster row.** `docs/fleet/consumers.json`
  is schemaVersion 5 and carries a `rolloutPolicy` with `canary`,
  `post-canary`, and `final` cohorts. A consumer absent from every cohort is
  registered but unscheduled.
- **Regenerate the candidate ledger.** `docs/fleet/candidate-validation.json`
  is digest-bound and enforced by `test_surface_closure`; the pre-push hook
  blocks a stale ledger locally. A roster change moves the fleet manifest
  digest.
- **Align the ruleset once, and only once the premise holds.** Strip
  `copilot_code_review` from both people-profiles rulesets, and delete the
  duplicate, at the point the repository is actually a consumer — not before.
- **Do not weaken any gate to make this pass.** If the resweep blocks, or the
  refresh reds a check, the answer is to fix the cause.

## Acceptance Criteria

- [ ] `python3 install.py <pack-checkout> --status --json` run against
      people-profiles reports `installedVersion` 0.71.40 and `state: current`.
      It does **not** report the install mode — measured against hoa-manager, a
      thin consumer, the JSON carries no `mode` key at all — so mode is
      asserted from the receipt below, not from this command.
- [ ] `.sd-ai-command-pack/provenance.json` records `"mode": "thin"`, and the
      committed machine-scope payload under `scripts/` is gone from the
      repository.
- [ ] The resweep verdict for this consumer is `clear`, and the verdict
      document used for the conversion is the one produced against the tree
      that was actually converted.
- [ ] All three repo-authored citations name the kept resolver path as a plain
      path rather than a `scripts/sd-ai-command-pack-*` literal.
- [ ] people-profiles appears in `docs/fleet/consumers.json` with `"mode":
      "thin"`, a `github` slug, a `pathHint`, its platform list, and a
      `rolloutPriority`; and it is named in exactly one `rolloutPolicy` cohort.
- [ ] `docs/fleet/candidate-validation.json` is regenerated and
      `scripts/sd-ai-command-pack-fleet-candidate-check.py --check-ledger`
      exits 0.
- [ ] `make check` passes in the pack repository.
- [ ] The whole-tree review preflight reports zero failures in people-profiles.
- [ ] Neither people-profiles ruleset carries `copilot_code_review`, and the
      `deletion` and `non_fast_forward` rules on its `main` ruleset survive.
- [ ] A live sweep of every repository in the fleet finds `copilot_code_review`
      only where it is intentionally retained, with the retained set stated.

## Out Of Scope

- `answerbook/mezmo_benchmark`, whose ruleset needs an admin this account does
  not have. It stays recorded as outstanding in the audit README.
- Rolling the 0.71.40 refresh out to the other eight consumers. That campaign is
  separately blocked and is not a precondition for onboarding this repository.
