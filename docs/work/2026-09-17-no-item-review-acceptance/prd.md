---
title: Explicit review acceptance without placeholder work items
created: 2026-09-17
branch: main
---

# PRD — no-item review acceptance

## Problem

Small changes can ship without work items, but review acceptance requires an item-backed receipt.
This leaves evidence-backed rebuttals and accepted risks without an executable clearance path.
Another review can repeat the same accepted objection without resolving that mismatch.

The unmerged research-opening branch demonstrates the gap at `19300794ca3be0e24c2758e8bdb31a5db5d2022e`.
Its third review completed the required depth and passed deterministic checks on 2026-09-17.
The report retained two blockers about an explicitly accepted design risk.
It also found an unfixed diagnostic regression: the parser silently ignores indented declarations.
That diagnosis concerns `fix/research-opening-overrides`, not this planning worktree's baseline `8ba8fa7a`.
The baseline parser accepts indented declarations; the unmerged checker already contains fence and nested-note fixes.

The acceptance entry point requires `--item` and loads that item's receipt.
See `source:bin/sd-ship::parser` and the constructor in `source:bin/sd-ship::Ship`.
Existing acceptance checks already bind findings, evidence, history, source, and tool versions.
See `source:bin/sd_ship_dispositions.py::context` and `source:bin/sd_ship_dispositions.py::validate`.

## Scope

Deliver a no-item review record and explicit acceptance path within the existing ship workflow.
Then fix the diagnostic regression on the existing checker branch.
Keep these deliveries separate; the checker must not change its own acceptance gate.

This item tracks the tooling enhancement. It does not retroactively assign an item to the checker change.
Keep simulator documentation, simulator CI pins, provider configuration, and branch protections unchanged.
Keep whole-opening overrides. Do not change general Markdown parsing or the automatic review limits.
Do not automate no-item pushing, merging, runner assignment, or work-item delivery in this scope.
Do not migrate item-backed work into no-item records. Related item-backed history requires the existing item-backed workflow.

Rules: R13-D1, R13-D2, and R13-D3 apply to authored documentation.

## Requirements

1. Identify no-item records by repository and stable review ID. Branch changes must preserve spent passes without a work-item row.
2. Reuse the current review validation and disposition rules through one shared implementation.
3. Reserve each provider pass before dispatch, using append-only records and the existing repository lock.
4. Preserve raw reports, failed attempts, findings, author exclusions, and spent-pass counts across resumptions.
5. Bind clearance to the exact clean HEAD, full required coverage, passing checks, policy, tools, and complete history.
6. Require one evidenced response for each blocking finding, including repeated findings with separate indices.
7. Accept only supported rebuttals or explicit risk acceptance with a named owner and revisit trigger.
8. Require explicit approval of the validated proposal digest. Implementation approval and merge permission do not approve individual findings.
9. Refuse changed evidence, stale histories, source changes, incomplete coverage, failed checks, and mismatched repositories or branches.
10. Provide a read-only clearance check immediately before each manual publication action.
11. Import historical reports only as untrusted evidence. Imported reports cannot establish tool bindings or authorize publication.
12. Preserve all three spent checker passes during import. A fourth pass requires separate exact-head and history-bound approval.
13. Keep existing item-backed behavior unchanged, including runner, delivery, CI, ownership, and protection checks.
14. Pin manual pushes to the validated commit and merges to the expected remote HEAD.

## Proposed interface

These interfaces are proposals, not existing commands.

- `sd-ship review --no-item --create-record`: allocate a record without provider dispatch.
- `sd-ship review --no-item --review-id ID`: reserve and run the configured exact-head review without pushing.
- `sd-ship review --no-item --review-id ID --import-history FILE`: import evidence without provider dispatch or a new reservation.
- `sd-ship adjudicate --no-item --review-id ID --expected-head SHA`: propose, validate, and explicitly accept dispositions.
- `sd-ship verify-review --no-item --review-id ID --expected-head SHA`: validate clearance without writes or provider calls.

No-item commands also select a stable review record as specified below.
Require exactly one identity mode where applicable: `--item ID` or `--no-item`.
Leave existing lifecycle commands item-backed. Reject runner and delivery flags in the no-item path.
Keep the existing explicit additional-review request and history-digest requirements.
Do not introduce a generic force, bypass, or trusted-report flag.

### Stable record identity

Use an opaque `review_id` scoped to the canonical repository, independent of its branch name.
Store branch aliases, the allocation HEAD, every reserved HEAD, and their tree hashes on that record.
Use `ship-review-no-item:` for review checkpoints and `ship-adjudication-no-item:` for accepted dispositions.
Derive their suffixes from repository identity and `review_id`, with unambiguous field separators.
Never encode absence as item `0`, a negative ID, or a synthetic row.

`sd-ship review --no-item --create-record` allocates a record without provider dispatch or a spent-pass reservation.
It can combine with `--import-history FILE`; ordinary dispatch cannot combine with either flag.
Later no-item commands require `--review-id ID`. Missing identity never allocates a fresh budget implicitly.
Creation requires an explicit assertion that this is new work, not a renamed or rewritten continuation.
Require a clean checkout and a nonempty committed diff against the refreshed default branch before allocation.
Freeze that diff's merge-base and source HEAD in the record.
An unchanged default-branch HEAD is not an allocation target or an ownership anchor.
Create the record after committing the proposed change, not when first creating its branch.

Maintain repository-scoped identity indexes under `ship-review-no-item-index:` using the existing checkpoint primitives.
Use separate bounded checkpoint keys for branch aliases, HEADs, and trees, not one growing repository-wide JSON value.
Update the index and record in one transaction under the repository lock.
Allocation indexes its initial HEAD and tree before the first reservation.
Before creation, reject active branch aliases, recorded HEADs, matching recorded trees, and reserved commits inside the proposed branch diff.
Return the existing review ID or report ambiguity; never choose the record with the smallest spent count.
Before import or reservation, reconcile every supplied HEAD and tree with that index.
Conflicting ownership refuses before any record write or provider dispatch.
Independent changes can share a merge-base. A common base alone does not establish duplicate work.

Before allocation, import, dispatch, and clearance, check retained item-backed receipts for the same canonical repository.
Match their branch, reserved or reviewed HEADs, tree hashes, and reviewed commits within the proposed branch diff.
Do not treat commits already included in the refreshed base as related merely because they are ancestors.
Any matching item-backed receipt refuses no-item operation and names the existing item and receipt.
Never import that receipt as standalone history or use no-item acceptance to clear its findings.
Recheck under the shared repository lock before writes or provider dispatch.

The command-pack adapter enumerates existing `ship:` checkpoint keys through the provisioned connection and reads them with `sd_db.ship.read`.
Use the existing `state` checkpoint table, as the provisioned library's `for_item` function does:

```sql
SELECT key FROM state WHERE kind='checkpoint' AND key LIKE 'ship:%' GROUP BY key
```

This adapter deliberately depends on the existing schema; it does not require an enumeration API or schema change.
Record the tested schema version and required table layout in the adapter's compatibility contract.
Validate that contract before enumeration. Reject incompatible layouts, query errors, and malformed records; never treat them as empty history.
Bind the observed schema contract and its reader dependencies alongside no-item tool bindings.
Test the real provisioned library, schema drift, and unreadable records before allowing dispatch or clearance.
Retain each matching receipt's stored pass history without changing its row, protocol, or key.
Missing or unreadable relevant history refuses operation. Do not add a library or schema change.
Standalone reviews have no complete machine registry.
Their import still requires the operator's completeness assertion; automated checks cannot prove that undisclosed standalone reviews never occurred.

`sd-ship review --no-item --review-id ID --rebind-branch OLD` explicitly rebinds the record to the current branch.
This metadata-only operation preserves every pass and alias, invalidates acceptance, and dispatches no provider.
Require `OLD` to match the stored current branch and every reserved HEAD to remain an ancestor of current HEAD.
Reject conflicting record ownership and stale concurrent writes.
Other commands refuse a branch mismatch until rebinding completes.

Records have `active` and `closed` states. Closing records whether work completed or was abandoned, with a reason.
`sd-ship review --no-item --review-id ID --close-record REASON` closes a record without provider dispatch.
`sd-ship review --no-item --review-id ID --reopen-record` resumes the same record and its unchanged spent count.
Both operations require the repository lock and current receipt revision.
Neither transition finalizes an unfinished reservation or establishes coverage. Interrupted reservations remain spent after close and reopen.
Closing releases the active branch alias, but retains every HEAD, tree, reservation, and evidence reference.
Different work can reuse a closed branch name only when the remaining identity checks find no overlap.
The same content must reopen its existing record. Abandonment never creates a fresh review budget.
Rebinding can move a closed record before reopening, subject to the same ownership and ancestry checks.
Closed records cannot dispatch reviews or provide publication clearance.

Rebinding, closing, and reopening increment `identity_revision` and invalidate acceptance in the same transaction.
Fresh requests and acceptance bind the current identity revision.
Earlier native requests retain their recorded revision and branch. Imported requests remain unchanged and untrusted.
Returning to an earlier branch name cannot restore old acceptance.
Conflicting records return their IDs and retained evidence without mutation; reconciliation must preserve every implicated pass.
V1 provides no merge, deletion, expiry, or budget-reset operation for ambiguous records.
Stop and request a separate migration decision if validated identity remains ambiguous.
Bound index values and receipt-enumeration work. Exceeding a documented limit refuses the operation without dropping history.
Existing records remain readable after a capacity refusal.

Recovery owner: Sven. Trigger: a real capacity refusal or ambiguous identity match.
Successor: a separate no-item history-migration plan; no migration implementation is authorized here.
On 2026-09-17, Sven approved refusal-only V1 recovery and deferred migration tooling.

Branch rename or copying the same HEAD cannot create fresh budget.
This scope does not support rewritten continuations; they must retain their original review ID and stop for a migration decision.
The trusted operator must disclose such continuations. Hashes cannot detect every semantically equivalent rewrite.

Keep no-item records outside item watchers and delivery bookkeeping.
Refuse missing or unreadable storage; do not substitute a second store silently.
Reject acceptance receipts from another identity mode, including item-backed receipts with otherwise matching repository and HEAD.

Extract shared review validation and dispatch boundaries before adding the no-item adapter.
Keep provider routing, authorization, spending controls, and raw-report parsing in their existing owners.
Keep disposition validation in `source:bin/sd_ship_dispositions.py::validate`.
Avoid a second implementation of those gates.

Resolve identity before constructing the shared review context.
The item adapter keeps the current constructor's item lookup, branch checks, receipt keys, and result fields.
The no-item adapter resolves canonical Git identity and the explicit review record without calling the item-bound `Ship` constructor.
Pass storage, repository, branch, source HEAD, review key, history adapter, and identity bindings into the shared review logic.
Remove direct item lookups from that shared logic; do not emulate an item with null or sentinel fields.
The result adapter preserves item-backed output and emits `identity_mode` and `review_id` for no-item output.
Keep GitHub-client construction in the item-backed publication path. No-item review and clearance need no publication client.
Test no-item construction with item lookup and publication-client constructors set to fail if called.

Before extracting code, enumerate every repository module that can affect review, identity, history, acceptance, or clearance decisions.
Include each extracted module and both identity adapters in the relevant review or adjudicator tool-binding manifest.
Retain all existing manifest members, including the library-file hash.
The item-backed and no-item paths must use those complete manifests.
Missing manifest files refuse validation; no fallback may omit them.
Tool-binding values must change when gate code changes. Prior acceptance then requires renewed validation and explicit approval.
Preserve item-backed serialization, key derivation, and history-digest algorithms, not obsolete tool-binding values.
Test each manifest member by changing its bytes and requiring both applicable identity modes to refuse stale clearance.

The no-item identity adapter belongs in this repository, not in `sd_db`.
Reuse the provisioned `sd_db.ship.read`, `save`, and `repository_lock` interfaces with the new checkpoint keys.
These interfaces accept generic keys and records; they do not require item identity lookup.
Do not change the library, its schema, or its version pin in this scope.
Fail clearly if those interfaces are missing. Stop and revise this plan if implementation needs a library change.
Retain the existing library-file hash in the adjudicator binding so library changes invalidate prior acceptance.

### Historical evidence

Preserve review evidence outside temporary storage before implementation starts.
Keep raw reports local; do not publish them through the PR.
Verify each retained file against its original bytes and record the archive digest.

An explicit import reads an ordered manifest containing every known report, request record, and failed attempt.
Validate canonical file paths, bounded JSON, hashes, repository claims, source heads, ancestry, and report-to-report references.
Retain original bytes and record the manifest digest before any new dispatch.
Store supplied approval claims as untrusted context, not proof of authorization.
Require an explicit operator assertion that the supplied history is complete; hashes cannot prove omitted records never existed.
Refuse conflicting imports and merges that would replace existing history.
Do not combine import-only mode with provider-dispatch or acceptance flags.

The no-item checkpoint separates imported history from native reservations:

| Field | Contents and authority |
|---|---|
| `historical_passes` | Immutable imported records, with exact source bytes and hashes. They consume budget but never prove coverage. |
| `passes` | Native reservations and results. Only valid native results can establish current coverage and tool bindings. |
| `history_digest` | A versioned digest of canonical repository, stable review ID, ordered imported records, and ordered native records. |

Each imported record retains its ordinal, source HEAD, original report, request evidence, and available prior-input references.
Store original bytes as bounded base64 values with their SHA256 values; parsed projections never replace those bytes.
Missing reports remain explicit and still consume their recorded reservation.
Treat imported request records as untrusted historical claims, not native additional-review authorizations.
Never manufacture their missing approval fields or revalidate them against reshaped native history.

Spent passes equal `len(historical_passes) + len(passes)`.
Importing the checker evidence sets this count to three, while native coverage remains zero.
The next dispatch therefore needs a new request bound to its exact HEAD and preceding combined `history_digest`.
It appends native reservation four before any provider call.
Interrupted native reservations remain in `passes` and never refund budget.
For any nonempty import, the first native pass requires an explicit request, exact HEAD, and preceding combined history digest.
This rule also applies to one or two imported passes, before ordinary native-only thresholds would require renewal.
Every native pass after import uses full-branch review with complete aggregate history; never use imported evidence for `--verify-report`.
Validate these requests at their actual global ordinals, including ordinal two after one imported pass.
Native-only no-item histories keep the existing initial-review and fix-verification limits.
Keep the existing item-backed receipt format and digest algorithm unchanged.
Mutable branch, lifecycle state, and identity revision stay outside this history digest.
Branch values already stored inside historical evidence remain immutable provenance.
Rebinding must leave every historical prefix digest and request binding valid without rewriting any historical request.

### Shared history integration

Change the shared orchestration to consume a mode-specific history adapter, not direct native-list lengths.
The item-backed adapter returns its existing counts, digests, and binding shape without changes.
The no-item adapter exposes combined spent counts, global ordinals, prefix digests, aggregate input, and validated native results.
Imported records never become native results or native approval requests.

| Existing gate | Required no-item behavior |
|---|---|
| `SharedReview.review` in `source:bin/sd_ship_review.py::SharedReview` | Use combined spent count before dispatch. Imported history cannot take the initial-review or fix-only shortcut. |
| `SharedReview.additional_request` in `source:bin/sd_ship_review.py::SharedReview` | Require explicit continuation after any import. Otherwise apply existing thresholds. Bind requests to combined history and exact HEAD. |
| `source:bin/sd_ship_history.py::validate_additional_requests` | Validate native requests at their global ordinals against their combined prefixes. Never authenticate imported requests. |
| `SharedReview.review_inputs` in `source:bin/sd_ship_review.py::SharedReview` | Validate the first native result after import as a full-branch continuation with complete historical input. |
| `source:bin/sd_ship_dispositions.py::context` | Add no-item identity, schema version, and recomputed combined history digest to acceptance bindings. |
| `source:bin/sd_ship_dispositions.py::key` | Obtain the acceptance key from the explicit identity adapter. Preserve the exact item-backed derivation. |
| `source:bin/sd_ship_dispositions.py::accepted` and `source:bin/sd_ship_dispositions.py::adjudicate` | Read and write only the selected adapter's acceptance key. Reject cross-mode receipts through shared binding validation. |

No-item acceptance keys use `ship-adjudication-no-item:` with the canonical repository and stable review ID suffix.
Do not derive them by stripping `ship:` from a no-item review key.
Keep key selection separate from disposition validation; do not duplicate the adjudicator.
Fixtures must assert the exact read and write keys, not merely different prefixes.

Compute each combined digest from stored records; refuse a cached digest that disagrees with its contents.
For the checker, three imports and no native results require explicit approval before native reservation four.
Use the complete aggregate input's digest for `resume_report_digest`, not the differently shaped checkpoint history digest.
Require the report's source base to equal its independently recorded full-branch `authorship_base`.
Carry imported author exclusions into routing, without treating imported coverage as current coverage.
Every later native result retains the same complete-history validation requirement.

Keep disposition validation shared, but supply explicit mode-specific bindings to it.
No-item bindings include `identity_mode`, `review_id`, current branch, `identity_revision`, schema version, and recomputed combined `history_digest`.
Adding, removing, reordering, or changing any imported record invalidates prior acceptance before publication.
The item-backed binding shape and history-digest algorithm remain byte-for-byte compatible.
Gate changes invalidate tool-binding values in both modes, as specified above.

The checker report used enriched prior evidence, including author responses.
Preserve that historical input and digest without reconstructing or rewriting either.
Build a new aggregate input for the next review, retaining every historical finding and its original provenance.
Save that new input's exact bytes and digest before dispatch, separately from the historical input.
Missing historical tool bindings remain missing. Never backfill them from current files.
A new full-branch review must establish current bindings before clearance can become possible.

### Durable disposition evidence

Before proposing acceptance, materialize all referenced evidence under the common Git directory's `sd-review-evidence/<review_id>/` directory.
Use content-addressed regular files with one hard link. Verify canonical paths and bytes after copying.
Do not overwrite an existing evidence file with different bytes or bind acceptance to temporary paths.
The archive preserves recovery inputs; extracted canonical files provide the evidence that disposition validation reopens.

Before each publication action, verify the archive digest and every bound evidence file through the shared validation path.
Missing or changed evidence refuses clearance, even when a previous validation passed.
Restore missing files from the verified archive before retrying validation.
Relocation changes the proposal digest and requires renewed explicit acceptance.
Document that Git does not publish these records.
Clone replacement requires a separately retained evidence backup and validated restoration.
Before implementation, request an operator-approved durable backup directory outside the checkout, common Git directory, and temporary storage.
Copy and verify the required archive there; record its canonical path and digest in local evidence.
The existing `.git/sd-review-evidence/` archives are local recovery copies, not this independent backup.
Test restoration using only the independent copy in an isolated destination, with the primary evidence path unavailable.
Do not create an external backup location without the operator's approval.
Losing both storage and backup blocks clearance. Never reconstruct missing evidence from an earlier success claim.

### Checker follow-up

This follow-up targets the unmerged checker branch and does not block delivery of the tooling enhancement.
It does not add a work-item association to the checker PR.

After each template update, manually review all content before the first H2 heading.
A whole-opening override suppresses current and future opening checks.

A standalone indented declaration-shaped bullet must emit `declaration must start at the left margin`.
It must leave the target's drift findings active.
Treat a declaration-shaped bullet at an indented block's start as standalone.
Continuation lines inside a valid left-margin declaration remain its reason text.
Ordinary indented explanation bullets remain prose, including blank-separated notes beneath a valid declaration.
A nested declaration-shaped example must never grant an override.
Tests must distinguish standalone declarations from continuation text, including spaces, tabs, and blank separators.

## Delivery sequence

1. Obtain the approved independent backup directory. Copy, verify, and restore-test the evidence archive before implementation.
2. Add isolated failing tests for no-item records, acceptance, history import, and boundary refusals.
3. Extract shared gates with complete tool-binding manifests. Verify item-backed behavior and expected stale-binding refusals before adding the adapter.
4. Implement no-item review, acceptance, and read-only clearance checks. Update the ship workflow documentation.
5. Review and ship the tooling enhancement through the existing item-backed workflow.
6. Require a raw clean/advisory tooling review. Do not use modified acceptance code to clear its own findings.
7. Fetch the default branch and merge it into the checker branch without rewriting existing commits.
8. Reproduce the indented-declaration failure, add regression tests, and apply the diagnostic fix.
9. Import all checker review history as evidence, retaining its three spent passes.
10. Request separate approval for one full-branch review of the final checker HEAD and complete history digest.
11. If only accepted risks remain, present each evidenced disposition and its exact acceptance digest for explicit approval.
12. Revalidate clearance before push and merge. Preserve all existing manual publication checks.

For the checker review, record the merge-base against the refreshed default branch and enumerate its complete diff.
Already-landed tooling changes are outside that diff; see `source:bin/sd-review::resolve_subject`.
Require repository-owned review and acceptance inputs to match the released base before using no-item acceptance.
Stop if the checker diff changes those inputs or review finds a new tooling defect.
Use a separate tooling delivery.

If the tooling review remains blocked, stop; do not use the new path to approve itself.
If imported history is incomplete, retain the evidence and refuse clearance.
If a concurrent process changes the receipt, reject the write and require reconciliation.
Manual clearance does not make remote publication atomic. Exact-commit push and merge checks remain separate requirements.

## Acceptance criteria

The named no-item test module below is proposed.

- [x] `python -m unittest discover -s tests -p 'test_sd_ship_no_item.py'` passes with zero failures.
- [x] That suite proves accepted exact-head clearance makes zero provider calls and creates no work-item rows.
- [x] No-item construction never calls item lookup or publication-client constructors; item-backed construction and output remain compatible.
- [x] That suite proves missing depth, failed checks, stale source, changed evidence, and stale tool bindings each refuse clearance.
- [x] That suite proves duplicate blockers require separate responses and invalid dispositions cannot clear a blocker.
- [x] That suite proves imports preserve failed attempts and all three checker passes without granting clearance.
- [x] Three imported passes and zero native passes refuse unapproved dispatch; approved dispatch creates reservation four before its provider call.
- [x] That case rejects stale combined-prefix approval, incomplete aggregate input, missing author exclusions, and incorrect full-branch coverage.
- [x] One-, two-, and three-import cases each require explicit native continuation and validate their global request ordinals.
- [x] Each case dispatches full-branch review with complete history and never selects imported fix-only coverage.
- [x] A native-only control retains the existing initial-review and fix-verification behavior.
- [x] Accepted clearance rejects each add, remove, reorder, and content mutation of imported history.
- [x] Branch rename, same-HEAD branch copy, and descendant continuation preserve the record and budget; conflicting records refuse dispatch.
- [x] Creation and rebinding are atomic, provider-free, and refuse concurrent index changes without orphaning reservations.
- [x] Related item-backed receipts refuse no-item allocation, import, dispatch, and clearance without changing either mode's history.
- [x] Real-library enumeration needs no known item IDs; schema drift, query errors, and malformed records refuse before dispatch or clearance.
- [x] Rebinding preserves all prior prefix digests and request bindings while invalidating acceptance, including a branch-name round trip.
- [x] Empty or uncommitted branches refuse allocation; distinct committed changes with a shared base receive independent records.
- [x] Close and reopen preserve every pass, invalidate acceptance, and refuse concurrent writes. Interrupted reservations remain spent.
- [x] Closed branch aliases permit unrelated committed work, but identical content retains its original review budget.
- [x] Ambiguity and capacity limits produce actionable refusals without deleting evidence; existing records remain readable.
- [x] Item-backed golden fixtures retain receipt, request, and acceptance-binding shapes, key derivation, and history digests.
- [x] Changed gate code changes tool-binding values; prior acceptance refuses until renewed validation and explicit approval.
- [x] Each extracted gate or adapter appears in a binding manifest; mutating its bytes refuses stale clearance in each applicable mode.
- [x] No-item acceptance uses the exact `ship-adjudication-no-item:` key; item-backed acceptance keeps its original key derivation.
- [x] Both acceptance readers reject a receipt from the other mode, including a forged copy under the expected key.
- [x] That suite proves missing bindings, conflicting histories, invalid ancestry, and stale approval digests cannot authorize publication.
- [x] That suite proves concurrent record changes refuse acceptance and repeated validation appends no acceptance receipt.
- [x] That suite proves item-backed and no-item receipts cannot authorize each other's publication.
- [x] That suite reads the persisted reservation from the provider stub before allowing dispatch.
- [x] Exit, timeout, and interruption tests resume with the spent pass retained and reject unapproved extra dispatches.
- [x] The real provisioned `sd_db` passes no-item storage tests against an isolated database; missing interfaces produce a clear refusal.
- [x] A real shared GitHub guard rejects a moved remote HEAD before merge dispatch, with zero merge API calls.
- [x] The documented manual merge request includes the expected HEAD; its fixture rejects a mismatched server-side SHA.
- [x] `python -m unittest discover -s tests -p 'test_sd_ship*.py'` passes with zero failures.
- [x] `python -m unittest discover -s tests -p 'test_code_health.py'` passes without raising any baseline.
- [x] `make check` exits 0 for each implementation delivery; `sd-docs-lint` reports `clean` for its PR description.
- [x] A fixture-based manual-workflow test rejects changed HEAD or evidence between acceptance and publication preflight.
- [x] The tooling delivery clears its existing review gate without invoking its new no-item acceptance path.
- [x] The retained archive restores every required review artifact with matching bytes and digests before import.
- [x] The independent backup lies outside the checkout, common Git directory, and temporary storage, with verified canonical path and digest.
- [x] Restoration succeeds from that copy alone when the primary evidence path is unavailable in the isolated fixture.
- [x] Acceptance uses durable canonical evidence after temporary sources disappear; publication preflight rejects missing or changed durable evidence.
- [x] Archive restoration preserves exact bytes; relocated evidence requires a new explicitly approved proposal digest.

Checker follow-up verification remains separate from this item's delivery criteria:

- Record a failing diagnostic regression, then pass `python -m unittest discover -s tests -p 'test_sd_research_kit.py'`.
- Cover indented declarations, nested notes, nested examples, valid declarations, and retained unrelated drift.

Fixtures prove implementation behavior, not live provider coverage or human authorization.
The checker branch remains blocked until its own fresh review and any explicit disposition acceptance complete.

## Review

Planning status remains on the database row.
On 2026-09-17, Claude completed pass five: coverage `1/1`, five blockers, overall exit `1`.
`make check` passed with exit `0` in 169.509 seconds.
The reviewed input hash is `c64663f125ee9be298abe98c309f3102daf4abfdf0dd9e935d393e91d0aa75c0`.

Responses in this revision:

1. Receipt enumeration: addressed by explicit query ownership, schema compatibility checks, and a real-library enumeration fixture.
2. Short imported histories: addressed by explicit continuation, full-branch coverage, and request validation at every imported-history ordinal.
3. Independent backup: complete. Sven approved the destination; the isolated restoration passed with primary evidence access denied.
4. Recovery limits: parked. Sven accepted refusal-only V1 scope; migration remains deferred until a concrete case requires it.
5. No-item construction: addressed by explicit identity resolution, shared-context inputs, and constructor isolation tests.

Host review confirms the revised integration requirements. They remain unimplemented and lack fresh independent verification.
The full response record is `/private/tmp/sd-no-item-plan.DKvPEt/planning-verification-5-dispositions.md`.
Earlier responses and raw reports remain in local evidence; this section records the current planning state only.
Five Claude planning passes have completed. The planning cap is spent; no additional pass starts automatically.
On 2026-09-17, Sven approved the limited V1 scope and post-cap amendments after disclosure of the independent-verification gap.
The approved plan hash is `3297d69e71b9ef77fc71e11d3876756ae39964018450054d9b5e3af904fa7736`.
The decision record is `/private/tmp/sd-no-item-plan.DKvPEt/planning-post-cap-approval.json`.
This approval settles planning judgment, not the raw provider verdict or implementation verification.
The backup prerequisite is complete. On 2026-09-17, Sven approved implementation and local validation.
The implementation approval binds PRD hash `472a6cd78bd7ff3e41009926dbd2abb571bf1713f988eb1c06f7b0bfcac4a4db`.
The database row is `in_progress`; decision `2765` and transition `2766` record this approval.
No additional provider review, push, merge, or runner assignment change is authorized.
The checker branch remains unchanged; its diagnostic fix and fourth code review require separate approvals.
The changed artifact is not a sensitive path; no sensitive-path concern ledger or cross-artifact sweep applies.

### Backup verification

On 2026-09-17, seven archives copied to `/Users/sven/Backups/sd-review-evidence` without overwriting files.
All archive hashes matched the recorded source hashes.
The isolated restoration matched all 86 members: 43 artifacts and 43 macOS metadata entries.
The restoration sandbox denied primary evidence reads with `Operation not permitted`.
The hash manifest and restoration receipt remain in the backup directory.
This backup protects against checkout replacement, not device loss.
No implementation or provider review ran during backup verification.

## References

- [Ship workflow](../../../skills/sd-ship/SKILL.md), especially evidence-backed disposition acceptance.
- [Review workflow](../../../skills/sd-review/SKILL.md), especially coverage and provider boundaries.
- [Review limits](../../../.claude/rules/sd-planning-adversarial-review.md).
- Local evidence: `/private/tmp/sd-opening-ship.ly3b5l/additional-review-dispositions.md`.
- Local raw reports: `review-approved.json`, `review-verification.json`, and `review-additional.json` in that evidence directory.
- Local review request: `additional-review-request.json` and its exact `additional-review-history.json` input.
- Retained archive: `/Users/sven/repos/platypeeps/sd-ai-command-pack/.git/sd-review-evidence/no-item-1006-inputs.tar.gz`.
- Retained input archive SHA256: `0d1cce9dd0b809d0942ce6731bd267338608448d06b9c7c6d1298bd5c3ec5be9`.
- Current verification archive: `/Users/sven/repos/platypeeps/sd-ai-command-pack/.git/sd-review-evidence/no-item-1006-verification-5.tar.gz`.
- Planning decision archive: `/Users/sven/repos/platypeeps/sd-ai-command-pack/.git/sd-review-evidence/no-item-1006-post-cap-approval.tar.gz`.
- Independent backup manifest: `/Users/sven/Backups/sd-review-evidence/no-item-1006-backup-manifest.json`.
- Backup manifest SHA256: `80076f886d4b5b44ae2bb2480d59796f440522b31c8808d6acf300d5e623d1c0`.
- Restoration receipt: `/Users/sven/Backups/sd-review-evidence/no-item-1006-backup-restoration.json`.
- Restoration receipt SHA256: `1e5e591335bceb3b17862388824bed7f4fb018d5d9982046eb1db4ce1f526caf`.
- On 2026-09-17, all 11 archived artifacts matched their original bytes. Git does not publish this local archive.

## Log

- 2026-09-17: Sven approved V1 scope, post-cap amendments, and the backup destination. Restoration passed.
- 2026-09-17: Sven approved implementation and local validation. The row moved to `in_progress`; provider review and publication remain unapproved.
- 2026-09-17: Sven retained whole-opening overrides and required manual review after each template update. Decision `2767` records the policy.
- 2026-09-19: All 44 acceptance criteria are ticked. The last three, 348, 352
  and 358, closed as coverage gaps rather than missing behaviour: every guard
  each names already existed, and #1071 (`e7a8f40f`) added the cases that hold
  them, eight of them mutation-verified one guard at a time. #1067
  (`0300b858`) closed 377 and 378 the same way. The delivery sequence's twelve
  steps are spent and the checker review landed, so the work is delivered.
  This commit carries the `Delivers: sd:1006` trailer that
  `source:bin/sd_work.py::_delivery_reason` requires, because
  `source:.venv/lib/python3.13/site-packages/sd_db/workflow.py` refuses a work
  item's move to `done` on any other evidence. The row moves once this lands
  and `sd work deliver` verifies the trailer against the default branch;
  archiving the directory follows the row, not the other way round, because
  `bin/sd-docs-lint` rule 2 reads the row and not this file.
