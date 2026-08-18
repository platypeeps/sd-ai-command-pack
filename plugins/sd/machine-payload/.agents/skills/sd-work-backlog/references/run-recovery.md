# Stopped Or Red Run Recovery

Load this reference only when work-loop status reports `run_stopped` or
`context_red` with this exact path.

Reload the current Trellis task, applicable specs, branch, full HEAD, working
tree, upstream, PR, and every non-null `current` field from status. Do not
repeat a side effect until the ledger and live state agree.

- A checkpoint overlays its owning lifecycle phase. Preserve its human target
  and `checkpoint.resumePhase`.
- Supply every recorded non-null current-state field to `reconcile`. Omit only
  fields that status reports as null.
- When live evidence proves a later lifecycle phase, pass the exact observed
  phase and values with `--verified-live-advance`; repeat exact reconciliation
  without that flag to move amber agreement to green.
- A schema-v1 ledger whose phase is literally `checkpoint` uses a phase-valued
  target as owner. If its target is human text, supply
  `--resume-phase <recorded-lifecycle-phase>` only when independently proven.
- If the ledger claims work live state cannot prove, preserve red health and
  stop. Never reconstruct missing evidence from conversation history.

```bash
SD_PACK_TOOLCHAIN=""
for candidate in "${SD_AI_COMMAND_PACK_TOOLCHAIN:-}" \
  "scripts/sd-ai-command-pack-toolchain.sh" \
  "$HOME/.agents/bin/sd-ai-command-pack-toolchain.sh"; do
  if [ -f "$candidate" ]; then SD_PACK_TOOLCHAIN="$candidate"; break; fi
done
[ -n "$SD_PACK_TOOLCHAIN" ] || { printf '%s\n' "error: sd-ai-command-pack toolchain not found; checked SD_AI_COMMAND_PACK_TOOLCHAIN, scripts/, and \$HOME/.agents/bin. Reinstall the command pack." >&2; exit 1; }

bash "$SD_PACK_TOOLCHAIN" run-python -- \
  sd-ai-command-pack-work-loop.py reconcile --repo . \
  --run-id <run-id> --observed-phase <observed-lifecycle-phase> \
  --task <task> --branch <branch> --head <sha> \
  --base-branch <base-branch> --pr-number <n> --pr-url <url> \
  --last-shipped-sha <sha> --verified-live-advance --json
```

After reconciliation, re-run `status` and follow only its next typed recovery
directive. A stopped run with externally merged/archive evidence may advance to
`terminal_reconciliation`; do not choose that path yourself.

Reconcile first, then reactivate. `start --resume` puts a stopped run back into
`active` without consulting live state, so it is correct only once the ledger
and live evidence already agree — after the reconcile above, or when status
reported no contradiction to begin with. It preserves the run ID, iteration,
counters, and stop reason; the ledger keeps saying why it stopped.

`start --reset` is the opposite intent: discard this run's history and mint a
new one. It archives the outgoing ledger to a `replaced.json` sibling that
nothing reads back automatically, and it refuses `--run-id <the discarded run
ID>` so the replacement can never be mistaken for the run it replaced. Plain
`start` against a stopped run does neither — it refuses and names both flags.
