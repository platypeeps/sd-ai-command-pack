# `run --` cannot execute the payload helpers the pack ships without the executable bit

## Goal

Make the pack's one documented way to reach a helper work in the pack's own
checkout, where it is the only way its maintainers ever run it.

## Problem

`08-17-plugin-path-version-split` replaced three helper-resolution forms with
one: locate the toolchain through the bootstrap, then reach every helper through
it. `run` ends in

```text
exec "$RESOLVED_PACK_SCRIPT" "$@"
```

which requires the resolved file to carry the executable bit. The pack tracks 30
of the 36 entries under `scripts/` as mode `100644` — every `.mjs`, 24 of the
`.py` helpers, and five `.sh` including `housekeeping.sh`. Six are `100755`,
`toolchain.sh` among them, so the tree is already mixed rather than uniformly
non-executable.

`install.py` sets the bit when it stages a helper, so `~/.agents/bin` holds
`-rwxr-xr-x` copies. The rule therefore works from the machine install and from
any consumer checkout, and fails in exactly one place: the pack's own
repository, where the bootstrap's second candidate —
`scripts/sd-ai-command-pack-toolchain.sh` —
answers first and resolves helpers next to itself.

Hit while running `08-17-plugin-path-version-split`'s own pre-archive gate on
2026-08-18, with the absolute checkout prefix elided:

```text
scripts/sd-ai-command-pack-toolchain.sh: line 508:
<checkout>/scripts/sd-ai-command-pack-review-preflight.mjs: Permission denied
```

`run-python` is unaffected: it execs the interpreter with the script as an
argument, so the bit is never consulted. Only `run` is broken, and only for a
helper the checkout tracks non-executable.

## Requirements

1. `bash "$SD_PACK_TOOLCHAIN" run -- <helper>` runs the helper from the pack's
   own checkout, for every helper the pack ships, or reports why it cannot in a
   message that names the file and the missing property.
2. The fix is one change in one place. Eleven authored sites use this form
   today; a per-site workaround re-creates the drift the source task removed.
3. Behaviour from `~/.agents/bin` and from a consumer checkout is unchanged.
   Those paths work now and must keep working byte for byte.
4. A test fails if a shipped helper becomes unreachable through `run --` again,
   whichever fix is chosen. The defect survived a full `make check`, eleven
   review rounds, and a green CI run, because nothing executes the documented
   form against the checkout copy.

## Acceptance criteria

- [ ] `run --` reaches every shipped helper from a clean checkout of this
      repository, enumerated from `git ls-files scripts/` rather than from a
      list in a test.
- [ ] The same enumeration passes from `~/.agents/bin` after `make sync`.
- [ ] A consumer checkout is verified read-only and unchanged, per the fleet
      per-lane cleanliness rule.
- [ ] `make check` passes. The fleet candidate ledger is refreshed to all-pass
      only if the chosen fix actually moves the payload digest; a mode-only fix
      that leaves it unchanged must be shown to leave it unchanged.
- [ ] The eleven authored `run --` sites are unchanged, or the task records why
      the chosen fix required touching them.

## Candidate fixes

Their costs are **not** equal, contrary to the disposition recorded when this
was deferred from `#503`. That note assumed any `templates/scripts/**` edit
moves the payload digest. `installer/machinepayload.py:90` derives the
executable bit from the destination family rather than from the file's mode —
explicitly so "the payload digest [stays] identical across checkouts that lost
their mode bits" — and `payload_digest` hashes targets, derived bits, and
contents. A mode-only change therefore does not move the digest and does not
stale the fleet ledger. Confirm that before relying on it.

**Track the helpers `100755`.** Asserts what is already true — these files have
shebangs and are executed as programs — and needs no toolchain change at all.
Six helpers under `scripts/` and four under `templates/scripts/` already are,
so this makes a mixed tree consistent rather than introducing a new state. It
is content-free, so it does not move the digest. Verify first that no gate,
installer path, or payload comparison reads the modes it changes.

**Dispatch by extension inside `run`.** When the resolved operand is a pack
helper and is not executable, exec `node` / the selected Python / `bash` by
extension instead of the file itself, making `run` behave the way `run-python`
already does. This one *is* a content change to
`templates/scripts/sd-ai-command-pack-toolchain.sh`,
so it moves the payload digest and does stale the ledger. It also adds logic to
the single point every helper invocation passes through, and needs a clear
failure for an extension it does not know.

The modes fix is the cheaper and more honest one on this evidence; the
dispatch fix is the one to take if the mode bits turn out to be load-bearing
somewhere, or if helpers without a usable shebang exist.

Pick one on evidence in `design.md`; do not implement both.

## Out of scope

- The bootstrap's `[ -f ]`-versus-`[ -r ]` predicate, deferred from `#503` for
  the same payload-digest reason. Related, and a candidate to fold in only if
  this task's own edit already re-touches all 84 bootstrap sites — which
  neither candidate fix above does.
- Changing which candidate the bootstrap prefers. The checkout copy answering
  first inside the pack's own repository is correct: it is the version under
  test.
- `run-python`, which is not affected.

## Evidence

- `git ls-files -s scripts/` — 30 × `100644`, 6 × `100755`.
- `ls -l ~/.agents/bin/sd-ai-command-pack-review-preflight.mjs` — `-rwxr-xr-x`,
  byte-identical to the checkout copy (`0df7cd11…`).
- `scripts/sd-ai-command-pack-toolchain.sh`, the `run` case: `exec
  "$RUN_COMMAND" "$@"`.
- Authored sites: six `run -- …\.mjs`, five `run -- …housekeeping.sh` across
  `templates/.agents/skills`, `templates/docs`, and `.github/command-sources`.
- The failing transcript above, and the recorded disposition in the archived
  `08-17-plugin-path-version-split` PRD's Out of scope.
