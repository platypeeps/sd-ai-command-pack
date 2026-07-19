# Retired Review-Body Guidance Removal Design

## Scope Boundary

`manifest.json` is the authoritative inventory of current consumer-shipped
surfaces. The retirement regression will inspect each unique manifest source
whose kind is `skill`, `command`, `prompt`, or `doc`. This covers shared skills,
their references, platform adapters, and the installed guide without scanning
runtime scripts or repository history.

Historical `CHANGELOG.md`, archived Trellis tasks, and audit evidence are not
manifest guidance sources and remain unchanged. Existing template/mirror parity
tests continue to prove that the canonical template and dogfood-installed skill
are byte-identical.

## Change Shape

1. Remove the expired compatibility bullet from the canonical
   `sd-full-check` skill and synchronize the installed mirror through the pack
   installer.
2. Replace the narrow two-document assertion with a manifest-derived scan of
   all current shipped guidance sources.
3. Keep runtime tests that inject `REVIEW_PREFLIGHT_PR_BODY`; they prove the
   retired variable is ignored and are not user guidance.
4. Ship the documentation correction as a patch release with matching
   changelog and fleet-candidate evidence.

## Risks And Controls

- **False positives from historical records:** avoided by scanning only
  manifest guidance kinds.
- **Missing a newly added adapter or reference:** avoided by deriving sources
  from the manifest rather than maintaining a path allowlist.
- **Template/mirror drift:** covered by existing pack drift and full-check
  gates after the canonical template is installed into this checkout.
