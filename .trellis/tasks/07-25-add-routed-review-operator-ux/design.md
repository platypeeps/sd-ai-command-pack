# Routed Review Operator UX Design

## Ownership Boundary

```text
operator / composing skill
          |
          v
sd-review config ...   sd-review budget ...   finding ...   data ...
          |                    |                  |           |
          +--------------------+-- pack controller -----------+
                       |
                       v
       setup descriptor + versioned router contracts
                       |
          +------------+-------------+
          v                          v
sd-github-review compiler       private control plane
and recovery workflows          catalog and ledger state
```

The pack owns capability discovery, argument validation, operator-facing
formatting, explicit-action confirmation, and safe workflow invocation. It
does not read provider credentials or private ledger storage and does not
reimplement the router's schemas, compiler, selection, recovery, adjudication,
or retention rules.

## Public Surface

| Family | Operations | Default effect |
| --- | --- | --- |
| `sd-review config` | `init`, `validate`, `render`, `explain`, `diff`, `migrate` | Read-only except explicit `init` and `migrate` writes |
| `sd-review budget` | `status`, `pending`, `explain`, `retry` | Read-only except explicit `retry` workflow invocation |
| `sd-review finding` | `list`, `status`, `adjudicate` | Read-only except explicit trusted adjudication |
| `sd-review data` | `status`, `purge` | Read-only except explicitly confirmed private-data purge |

This cleanly extends `sd-review`; it is not a compatibility alias. Generated
platform adapters map natural language or slash-command arguments to the same
controller contract.

## Capability And Failure Model

Before an operation, the pack reads the router's canonical setup descriptor and
resolves the required contract major and capability without side effects.

- `ready`: invoke the declared contract.
- `absent`: show installation/setup guidance; infer no alternate backend.
- `incompatible` or `malformed`: fail closed with expected and observed
  contract identities.
- `unavailable`: report that state could not be established; make no mutation.
- `unsupported_in_standalone`: explain that the installed router is healthy but
  the requested managed capability is intentionally unavailable; never render
  a zero balance, empty queue, or completed operation.

Responses preserve the router-declared `standalone` or `managed` mode. The pack
never infers mode from endpoint health and never offers standalone as an
automatic recovery from a managed-service outage.

Responses preserve the router's separate review, assurance, and merge-gate
outcomes. The pack renders `sd-review / assurance` as truth and
`sd-review / gate` as branch-protection policy; it never relabels a passing
deferred gate as review success. Setup output diagnoses required-Check drift
but repository-rule mutation requires a separate explicit authorization.

Responses are validated before display or use. Unknown schema majors,
identity/digest mismatches, hostile paths or URLs, and over-broad payloads fail
closed.

## Delivery Decomposition

| Child task | Responsibility |
| --- | --- |
| `07-25-add-sd-review-configuration-operations` | Explicit scaffolding, validation, render, explanation, semantic diff, and one-time migration |
| `07-25-add-sd-review-budget-operations` | Bounded budget/deferred status, selection explanation, and explicit trusted recovery |
| `07-25-add-sd-review-finding-adjudication-operations` | Finding list/status plus explicit maintainer-attested adjudication through the trusted workflow |
| `07-25-add-sd-review-data-operations` | Retention/coverage status plus explicitly confirmed private-data purge over router-owned contracts |

The children may implement independently after the common capability envelope
is stable. Shared discovery and response validation belong in the pack-owned
review controller, not copied between skills or adapters.

## Packaging And Release

Authoritative changes start in `templates/**` and command-source inputs. Root
script twins and platform adapters are generated or synchronized through the
normal pack workflow. Shipped payload changes update `manifest.json`, the
installed guide, changelog/version, release ledger, install lifecycle tests,
and fleet validation in one release-consistent change.

Rollback pins the prior pack release. No dormant top-level command or local
router implementation is retained as a fallback.
