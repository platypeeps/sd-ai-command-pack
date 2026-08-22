# Verdict: does the layout resolver accept malformed input today?

Answers the PRD's first requirement. Evidence is from the canonical source at
`scripts/sd-ai-command-pack-review-layout.py`, exercised directly rather than
read alone.

## Method

`_read_machine_receipt` is the only receipt parser. It was imported from the
canonical source and called against seven receipt bodies, each written to a
real file, recording the exception type actually raised:

```
json-array       -> *** AttributeError: 'list' object has no attribute 'get'
json-string      -> *** AttributeError: 'str' object has no attribute 'get'
json-number      -> *** AttributeError: 'int' object has no attribute 'get'
json-null        -> *** AttributeError: 'NoneType' object has no attribute 'get'
object-ok        -> OK ({'path': 'a'},)
files-not-list   -> LayoutError: machine receipt <path> has no files array
entry-not-dict   -> OK ({'path': 'ok'},)
```

## Verdict, one claim at a time

The reviewer asked for two things. They do not share a verdict.

**1. "Validate JSON object" — CONFIRMED, and it is the whole defect.**

`_read_machine_receipt` goes straight from `json.loads` to `document.get("files")`
at `sd-ai-command-pack-review-layout.py:249,256`. Any valid JSON document that is
not an object — array, string, number, boolean, `null` — reaches `.get` on a type
that has no `.get` and raises a bare `AttributeError`. Four of the five shapes are
demonstrated above. This is exactly the class of failure the file's own
`LayoutError` exists to prevent, and the surrounding code already converts `OSError`
and `JSONDecodeError` into it; the type check is simply missing.

**2. "Validate `files` entry shapes" — NOT a crash, and mostly already handled.**

- `files` present but not a list already raises `LayoutError` (`:257-258`). No
  change needed.
- Entries that are not dicts are silently dropped by the `isinstance(entry, dict)`
  filter at `:259`. Nothing downstream can then observe them.
- Missing or mistyped fields cannot raise. The only two reads of an entry
  anywhere in the file are `entry.get("path")` and `entry.get("family")`
  (`:502,504`), both `.get`, so there is no `KeyError` or `TypeError` path. A
  missing `family` already lands on `LayoutError: <name> has unknown destination
  family None` and a dropped or unmatched entry on `LayoutError: <name> is not
  listed in <receipt>`.

So the second half of the finding is over-stated: no `files`-entry shape produces
an incidental exception. What it does produce is a **misdirecting message** — a
malformed entry is reported as "not listed in <receipt>", which sends a reader
looking for a missing install rather than a corrupt receipt.

## What this implies for the change

Narrow. One `isinstance(document, dict)` guard before `:256` closes the only
real crash. Optionally, reject a non-dict `files` entry explicitly instead of
dropping it, so the error names the offending entry — this is the PRD's "message
naming the offending path and field", and it is a diagnosability improvement,
not a correctness fix. That distinction should be stated in the commit rather
than blurred into "hardened validation".

## Shipped copies

Enumerated from the filesystem, not from memory:

```
find . -name "sd-ai-command-pack-review-layout.py" -not -path "./.git/*"
```

Five copies, all currently byte-identical (`sha256` prefix `2576ab2005f232b9`):
`.sd-ai-command-pack/bin/`, `plugins/sd/bin/`,
`plugins/sd/machine-payload/scripts/`, `scripts/`, `templates/scripts/`.
The change must land in all five for the acceptance criterion to hold.
