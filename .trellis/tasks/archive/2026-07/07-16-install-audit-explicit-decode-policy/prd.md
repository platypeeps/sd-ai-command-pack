# Make install-audit decode policy explicit

## Goal

Pin the shipped install audit upstream-manifest read to UTF-8 strict decoding, add regression coverage, and release the fix before resuming fleet refresh.

## Requirements

- Add an explicit UTF-8 decode error policy to the shipped install audit's
  optional upstream-manifest read without changing its advisory-only behavior.
- Keep the template source and root installed mirror byte-identical.
- Cover malformed UTF-8 input through the existing upstream-version advisory
  test surface.
- Publish the shipped payload fix as version `0.15.5` before resuming the fleet
  refresh.

## Acceptance Criteria

- [x] The upstream-manifest read declares `encoding="utf-8"` and
  `errors="strict"` in both shipped copies.
- [x] Malformed UTF-8 produces the existing non-fatal advisory result and no
  traceback.
- [x] Pack drift, parity, focused tests, and the full local check pass.
- [x] Version `0.15.5` is merged and tagged at the release commit.

## Notes

- This is a semantics-preserving policy hardening discovered by the Mezmo
  consumer's committed-diff preflight.
