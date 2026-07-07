# Expose a machine-readable "active platforms" state instead of marker-file inference

## Summary

Trellis installs per-platform adapter surfaces (Claude, Cursor, Gemini,
Copilot, OpenCode, Codex, Qoder, Trae, and more), but exposes no query
or state file that says which platforms are active in a repo. Tooling
that needs this — in our case an installer pack that only installs
adapters for platforms Trellis has activated — must infer it by probing
for Trellis-owned marker files (examples: `.claude/hooks/session-start.py`,
`.opencode/lib/trellis-context.js`, per-platform generated files).

This inference has two failure modes we have now hit in practice:

1. **Silent drift**: the marker tables must be hand-maintained per
   platform in every downstream tool. As Trellis grew from ~6 to 16+
   platforms, our copies drifted — several tools recognized only the
   original six, silently misclassifying files on the other ten.
2. **Silent breakage on rename**: if a Trellis release renames or
   relocates a marker file, detection quietly returns "not active" and
   downstream installs silently skip that platform. No error surfaces.

## Proposed upstream change

Any one of these would eliminate the inference:

1. A machine-readable state file maintained by `trellis init` /
   `trellis update`, e.g. a JSON document under the repo's Trellis
   directory listing active platform ids and their adapter roots; or
2. A CLI query, e.g. `trellis platforms --json`, returning the same; or
3. At minimum, a documented stability contract naming one canonical
   marker path per platform that downstream tooling may rely on across
   releases.

Option 1 or 2 preferred: they also give downstream tools a forward-
compatible way to handle platforms added after the tool shipped.

## Environment

Trellis CLI vendored scripts at `.trellis/.version` 0.6.5, repos with
mixed platform sets (6-16 active platforms).
