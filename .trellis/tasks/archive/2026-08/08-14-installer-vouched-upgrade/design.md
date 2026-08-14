# Design

## Where the defect lives

`installer/fileops.py::install_file`, the `destination.exists()` branch:

```python
if destination.exists():
    current = destination.read_bytes()
    if current == new_content:
        return InstallResult(file, InstallStatus.UNCHANGED, ...)
    if file.install == IF_NOT_EXISTS or file.target in FORCE_PRESERVED_TARGETS:
        ...  # PRESERVED / REFRESHED
    if not force:
        return InstallResult(file, InstallStatus.CONFLICT, ...)
    ...      # OVERWRITTEN
```

There is no state between `UNCHANGED` and `CONFLICT`. The function's only
inputs are the file, the destination bytes, and `force`; the consumer's
`provenance.json` is never opened, so "these bytes are the previous release"
is unrepresentable.

## The evidence already on disk

`.sd-ai-command-pack/provenance.json` maps each vouched target to
`sha256:<hex>` of the bytes the last install wrote there. It is written by
`installer/provenance.py::provenance_content` from `VOUCHABLE_STATUSES`
results, and `never_vouched_targets` already excludes force-preserved
targets, managed blocks, and the three receipt files — so a provenance hit
can never name a path this change should not touch.

The digest is of the *installed* bytes (`result.source_digest`, taken from
`new_content` after any thin rewrite), not of the raw template, so the
comparison stays valid in thin checkouts where installed bytes differ from
the pack source.

`installer/removal.py::may_remove_pack_file` already treats exactly this
match as authority to delete a file. This change gives the install path the
same authority to overwrite one.

Drift detection does not depend on the conflict gate either. The install
audit compares every vouched target against its recorded digest and reports
`vouched target content drifted` with state `invalid`
(`installer/inspection.py:241`), independently of whether the install path
would have conflicted. A locally edited file is caught there whatever this
change does.

## Classification

Insert one state ahead of the conflict return, mirroring the machine-scope
engine's `owned-stale`:

| on-disk bytes | provenance entry | status |
|---|---|---|
| == new template | any | `UNCHANGED` (today) |
| != new template | == recorded digest | **`UPDATED`** (new) |
| != new template | present, != recorded | `CONFLICT` (today) |
| != new template | absent / unreadable | `CONFLICT` (today) |

`InstallStatus.UPDATED` already exists, is already in `VOUCHABLE_STATUSES`
and in `inspection._CHANGE_INSTALL_STATUSES`, and `status.py` documents
`REFRESHED` as "Distinct from UPDATED (an `always` file)" — the vocabulary
was written for this case and only generated files ever reached it. No new
enum member, no exit-code change: `UPDATED` is a write, so a run that only
upgrades vouched files exits `0`.

## Threading the provenance map

`install_file` gains a keyword-only
`provenance_files: Mapping[str, str] | None = None`, keyed by POSIX target
path exactly as provenance stores it.

`_install_payload` reads it once per run via
`read_existing_provenance_files(target)` and passes the same mapping to every
`install_file` call. This follows `removal.py`, which already "parses
provenance.json once and threads" the result rather than re-reading per file.

The default is `None`, meaning *no evidence*, which classifies exactly as
today. Two consequences, both wanted:

- Direct `install_file` callers (unit tests) keep their current behaviour
  unless they opt in.
- No hidden filesystem read inside a per-file function, so a malformed or
  symlinked provenance is handled once, at the read, by the existing
  `read_existing_provenance_files` contract (returns `{}` on symlink,
  non-file, unreadable, or malformed input — which lands on `CONFLICT`).

Both the preflight dry-run pass and the apply pass go through
`_install_payload`, so both see the same mapping and cannot disagree. Both
run before the receipts are rewritten, so the mapping describes the previous
release throughout.

`UPDATED` must **not** join the preflight-result reuse set in `install_file`
(`CREATED` / `UNCHANGED` / `PRESERVED`). That reuse is guarded by
`planned_result_matches_destination`, which asks whether the destination
still matches the planned bytes; for `UPDATED` it does not match by
construction, so the apply pass reclassifies from disk. That is the correct
and cheaper outcome, and it keeps the spec's "do not reuse preflight results
for force overwrites, conflicts, generated files" boundary intact.

An interrupted prior run — files written, provenance not yet rewritten —
leaves provenance describing a release older than the bytes on disk. Nothing
matches, so the target conflicts exactly as it does today. The evidence is
absent, and absent evidence fails closed.

## No backup for a vouched upgrade

The forced path calls `backup_existing_file` because it is displacing content
whose origin is unknown. A vouched file's displaced bytes are a published
pack release, reproducible from the pack itself, so writing a `.bak` would
add an untracked file to every consumer on every upgrade. `--backup` keeps
its documented meaning: it preserves what `--force` displaced.

## What deliberately does not change

- `PRESERVED` / `REFRESHED`: the `IF_NOT_EXISTS` and `FORCE_PRESERVED_TARGETS`
  branch returns before the new check, so `.prism/rules.json`,
  `.gito/config.toml`, and `.github/PULL_REQUEST_TEMPLATE.md` are untouched.
- Symlink and non-file destinations: classified before any content read.
- `--force`: still displaces drifted content, still backs it up.
- The machine-scope engine: it already implements this correctly against
  `machine-receipt.json` and shares no code with this path.
- `retire_stale_targets`: reads provenance itself, before the rewrite,
  unchanged.

## Blast radius

`_install_payload` has five call sites in `install.py`: the revert-thin
preflight (1138) and apply (1190), the `--check` / `--status` inspection
dry-run (1351), and the normal install preflight (1590) and apply (1645).
All five gain the mapping from the same helper, so inspection needs no
separate change — `--check` builds its report from these same
`InstallResult`s, and `InstallStatus.UPDATED` is already in
`inspection._CHANGE_INSTALL_STATUSES`, so a vouched-stale target still
counts as a planned change and still reports `refresh-required`. It reports
it as `updated` rather than `conflict`. Revert-thin restores
payload into paths it expects to be absent; a vouched hit there is a
pack-owned file being restored to its current release, which is that flow's
intent — and its explicit refusal to accept `--force` is unaffected, because
a vouched upgrade is not a forced one.

## Spec and documentation

`.trellis/spec/backend/manifest-and-filesystem.md` "Plan-Before-Apply And
Concurrency" describes the repository-install boundary and must name the new
classification alongside the machine-scope `owned-stale` it parallels.
`README.md` and `templates/docs/SD_AI_COMMAND_PACK.md` describe conflicts as
customized files needing `--force`; both need the vouched-upgrade case.
Changing `templates/docs/SD_AI_COMMAND_PACK.md` changes an installed payload
file, so the repo's own copy is refreshed by the installer, not hand-edited.
