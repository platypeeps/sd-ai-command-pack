# Bound the size of JSON files status reads from consumer checkouts

Filed 2026-08-10 from `08-09-thin-fleet-status-pins` (PR #416). The review
preflight raised the `path-filesystem` boundary-risk category there; the
oversized-file and TOCTOU rows of that matrix were **dispositioned, not
fixed**, because they are properties of a shared pre-existing reader rather
than of that change.

## Problem

`read_json_object` (`templates/scripts/sd-ai-command-pack-status.py:165`) does
`path.read_text(...)` with no size bound and hands the result to
`json.loads`. Every fleet run calls it once per consumer for
`.sd-ai-command-pack/provenance.json`, then again for
`.sd-ai-command-pack/manifest.json` on the fallback path, and schema 5 added a
third call for a thin consumer's pin.

The paths are contained — the pin reader resolves with `resolve(strict=True)`
and `relative_to(<consumer root>)` before reading — so this is not a traversal
issue. It is a resource issue: a multi-gigabyte or deliberately pathological
file inside a consumer checkout makes a read-only status run allocate it
entirely. Fleet mode reads up to 8 checkouts concurrently.

Related: the path is re-read after it is resolved, so a replacement between the
two operations is possible. Decide whether that is worth closing (open once and
`fstat` the handle) or accepting with a stated reason.

## Requirements

1. `read_json_object` refuses a file above a documented byte bound and reports
   the refusal as unreadable with a reason — never as absent, and never as an
   empty-healthy result.
2. The bound is applied in the one shared reader, so provenance, installed
   manifest, and pin reads all inherit it rather than each re-implementing it.
3. Decide the TOCTOU question explicitly: either read through a single opened
   handle, or record why the re-read is acceptable here.

## Acceptance criteria

- [ ] An oversized file at any of the three read sites reports `unreadable`
      with a reason and does not allocate the whole file.
- [ ] The bound lives in the shared reader; no call site duplicates it.
- [ ] The TOCTOU disposition is written down in the backend spec next to the
      containment contract, whichever way it is decided.
- [ ] Existing status behavior for normal-sized files is unchanged.
