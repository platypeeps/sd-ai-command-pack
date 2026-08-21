# Qualify the `sd-audit-repo` charter fallback path

## Goal

`.github/command-sources/sd-audit-repo.md:12` tells the agent the charter
directory is resolvable "either inside the installed skill payload or at
`.agents/skills/sd-audit-repo/charters/` relative to the repository root". The
second half is false in a thin install. Make it true in both install shapes.

## Measured facts

| where | repo-root `.agents/skills/sd-audit-repo/charters/` | payload `~/.agents/skills/sd-audit-repo/charters/` |
| --- | --- | --- |
| sd-ai-command-pack (vendored dogfood) | 15 charters | 15 charters |
| se-ai-command-pack | 0 | 15 |
| sd-github-review | 0 | 15 |
| people-profiles | 0 | 15 |
| hoa-manager | 0 | 15 |
| anomaly-metric-creator | 0 | 15 |
| loadsmith | 0 | 15 |

All six consumers are `mode=thin`. None carries a repo-relative charter
directory, so the second disjunct never resolves there.

The thin conversion does not rewrite the path. Checked in-process:

```
rewrite_text(line, profile=THIN_PROFILE, key='.claude/commands/sd/audit-repo.md')
```

returns the line unchanged, including "relative to the repository root".
Directory-shaped `.agents/skills/...` tokens are not in the rewrite map — only
file-shaped skill references are, and even `…/SKILL.md` came back unrewritten
in the same probe.

## The decision

**Keep the arm, qualify it.** It is not dead: in the vendored pack checkout it
is the arm that works, because the Claude adapter copy of the skill
(`.claude/skills/sd-audit-repo/`) contains only `SKILL.md` — the charters live
under `.agents/`, exactly where this disjunct points. Deleting it would break
charter resolution in the one install shape where the payload arm is thinnest.

What is wrong is the unqualified root. This is the same defect family as
0.71.42: a sentence that names a repository-relative location for a path the
thin shape resolves under `$HOME`. The 0.71.42 precedent applies — drop the
false qualifier rather than add a conversion-time substitution, which would be
a byte-matched second copy of the same prose.

## Requirements

- The sentence must be true in both install shapes without a rewrite rule.
- Name `.agents/skills/sd-audit-repo/charters/` as living under the same root
  as the installed `.agents` payload, not under the repository root.
- Say explicitly that a thin install has no repo-relative copy, so the agent
  does not probe for one and report a false blocker.
- Ship it: source edit in `.github/command-sources/sd-audit-repo.md`, then
  `make sync && make generate`, version bump, `CHANGELOG.md`.

## Acceptance Criteria

- [ ] No shipped surface claims the charter directory is at a
      repository-relative path unconditionally. Scope the sweep to command
      surfaces — `CHANGELOG.md` quotes the old phrase as history and this PRD
      quotes it to define the check, so a whole-repo grep matches itself and
      can never pass:

      ```bash
      grep -rn 'charters/` relative to the repository root' \
        --include=*.md --include=*.toml . \
        | grep -v node_modules | grep -v CHANGELOG | grep -v '\.trellis/'
      ```

      Expect no output.
- [ ] All shipped copies carry the new wording (source, `plugins/sd/commands/`,
      the Gemini TOML adapter, the OpenCode adapter, and the four
      `templates/` twins).
- [ ] `make check` passes and the version ships with a `CHANGELOG.md` entry.

## Out Of Scope

- Teaching the thin conversion to rewrite directory-shaped `.agents/` tokens.
  That is a broader change to the rewrite map with its own blast radius; this
  task deliberately fixes the prose instead, per the 0.71.42 precedent.
- Refreshing consumers onto the shipped version.
