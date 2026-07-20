# Harden PR URL validation

## Goal

Reject malformed pull-request URLs without exceptions in the work-loop ledger and status snapshot boundaries.

## Requirements

- Treat pull-request URLs as bounded, parsed input at both the work-loop ledger
  and status-snapshot validation boundaries.
- Return the existing invalid-record result for malformed URL syntax, invalid
  ports, credentials, query strings, fragments, missing hosts, or empty paths;
  never leak a `urllib.parse` exception.
- Keep `templates/scripts/**` authoritative and synchronize the root dogfood
  mirrors through the canonical pack sync command.
- Add focused regressions for invalid-port and malformed-IPv6 inputs in both
  validator paths.
- Ship the compatible fix as a patch release with matching changelog and fleet
  candidate evidence.

## Acceptance Criteria

- [x] Work-loop validation rejects malformed PR URLs without raising.
- [x] Status snapshot normalization converts malformed terminal PR evidence to
      the existing bounded `invalid` result without raising.
- [x] Template/root parity, focused tests, and the full maintainer gate pass.
- [x] The patch release has current all-pass fleet candidate evidence and can
      be consumed by AMC's normal command-pack refresh after upstream merge.

## Notes

- Lightweight follow-up discovered by AMC PR #268 review. The maintainer
  explicitly authorized this upstream PR on 2026-07-20.
