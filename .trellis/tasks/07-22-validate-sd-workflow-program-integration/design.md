# Design: final SD workflow integration gate

## Architecture

The integration task is an evidence-producing gate over already-landed child
contracts. It does not become a second implementation owner.

1. Resolve prerequisite task, PR, commit, version, and disposition evidence.
2. Install or select the exact final command-pack head and compatible external
   router contract.
3. Execute S01-S11 through real generated surfaces and focused deterministic
   fixtures.
4. Run repository-wide and applicable fleet validation on the same head.
5. Publish one closure record consumed by the parent program task.

## Evidence Contract

The task writes a task-local integration record under `research/` with one row
per F01-F17 finding and S01-S11 scenario. Each row records:

- owner task and terminal status;
- PR, commit, pack version, and external router contract identity;
- test or command executed;
- observed result and evidence location;
- accepted follow-up or blocker, when present.

Missing, stale, ambiguous, or incompatible evidence is a failure state rather
than an empty success. The record names the exact repository and head used for
all aggregate commands.

## Scenario Execution

Use deterministic fixtures for unavailable, invalid, paginated, untrusted,
noninteractive, retry, path-containment, and retired-identifier cases. Use an
integration checkout only where behavior depends on generated installation or
cross-repository routing. Provider-backed tests must disclose network or paid
use and reuse exact-scope receipts when eligible.

Scenario failures route to the child that owns the defective contract. The
integration task may add or refine integration fixtures and evidence plumbing,
but it must not implement a child's missing production behavior.

## Parent Handoff

The closure summary reports whether every prerequisite and matrix row passed,
was explicitly dispositioned, or remains blocked. The parent closes only when
all required rows pass and any retained follow-up is consciously accepted.

## Rollback

Program rollback is version-based: reinstall the last known-good command-pack
release and compatible router contract. Do not retain dormant legacy command
surfaces. If the integration harness itself is defective, revert only its
fixtures/evidence changes and rerun against the same recorded identities.
