# Implementation plan: adaptive audit routing

## 1. Inventory Charters And Fingerprints

- Classify mandatory and optional dimensions with explicit rationale.
- Map repository fingerprints to every optional charter.

## 2. Implement Applicability Preflight

- Add deterministic fingerprint collection and a versioned routing report.
- Handle absent, unknown, and conflicting evidence conservatively.

## 3. Add Modes And Reporting

- Add standard, exhaustive, and additive dimension controls.
- Report all run/omitted/failed charters and coverage limitations.
- Apply structured multi-selection only to post-audit task proposals.

## 4. Calibrate

- Build representative fixtures with seeded findings.
- Compare standard versus exhaustive recall, runtime/context cost, and charter
  noise before selecting a default.

## 5. Validate

- Run charter-routing, report, unknown-stack, seeded-finding, generated parity,
  and existing audit tests, followed by `make sync` and `make check`.

## Stop Points

- Stop before changing the default if calibration shows material misses.
- Fall back to exhaustive when applicability cannot be established safely.
