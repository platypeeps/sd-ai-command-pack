# Design: evidence-routed audit charters

## Modes

- `standard`: mandatory core plus fingerprint-selected charters.
- `exhaustive`: every charter, subject only to an explicit unsupported-runtime
  report rather than omission.
- `dimensions=<...>`: adds requested dimensions to the selected mode.

## Applicability Report

A deterministic preflight emits repository fingerprints and a routing table:

- charter ID and version;
- selected mode;
- mandatory/optional classification;
- selected state and reason code;
- supporting fingerprint paths/metadata; and
- unknown/conflicting evidence.

The audit orchestrator consumes this report. It does not invent applicability
from conversation memory.

## Conservative Routing

Unknown or conflicting evidence selects the relevant charter or records an
explicit incomplete-coverage warning. Mandatory security/correctness/test/
release responsibilities do not disappear because a familiar manifest is
absent.

## Calibration

Representative synthetic/real fixtures seed material findings for optional
dimensions. Standard routing is compared with exhaustive results to measure
misses, context/runtime savings, and false-positive charter selection before
the default is changed.

## Interaction

Audit execution does not pause for charter-selection questions when mode and
dimensions are supplied or can be conservatively resolved. Structured input is
reserved for selecting independent follow-up tasks after the report.

## Rollback

Set exhaustive as the fallback if calibration or runtime classification fails.
Rollback removes the optimized default, not charter coverage.
