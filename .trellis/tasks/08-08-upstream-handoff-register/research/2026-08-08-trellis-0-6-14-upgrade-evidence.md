# Evidence: Trellis 0.6.14 upgrade landed in sd-ai-command-pack

Source: task 08-08-trellis-upgrade, branch `chore/trellis-upgrade-0-6-14`.

- Upgrade commit: `d10d4e95` — vendored surface 0.6.7 → 0.6.14 via the
  official `trellis update --force` after a two-part safety gate (0.6.7
  rescan pristine; sandbox-clone apply reproduced byte-for-byte).
  `.trellis/scripts` byte-identical to the 0.6.14 release templates (npm
  package and fork `v0.6.14` tag). `.trellis/.version` = 0.6.14.
- Wrapper adoption commit: `3328a1ec` — status collector now uses
  `task.py current --json` with a <=0.6.7 prose fallback; pack 0.64.29.

`task.py current --json` contract sample captured on this repo (0.6.14):

```json
{"current_task": {"dir": ".trellis/tasks/08-08-trellis-upgrade",
  "id": "trellis-upgrade", "title": "Upgrade vendored Trellis 0.6.7 to 0.6.14",
  "status": "in_progress", "parent": null, "children": [], "branch": null,
  "base_branch": "main"}, "source": "session:...", "stale": false}
```

Uptake consequences for the three 07-09 upstream items originally gated on
">=0.6.8 uptake": the gate is now satisfied in this repository — evaluate
each item against the 0.6.14 vendored surface rather than 0.6.7. Also note
0.6.14 behavior changes relevant to handoff evaluation:

- `add_session.py` omits journal sections with no content (<=0.6.7 always
  scaffolded Testing / Next Steps); the pack record-session wrapper now
  inserts missing sections (commit `d10d4e95`).
- The statusline UTF-8 stdin fix did NOT land here: the statusline hook is
  opt-in, excluded from `trellis update`, and not installed in this repo.
