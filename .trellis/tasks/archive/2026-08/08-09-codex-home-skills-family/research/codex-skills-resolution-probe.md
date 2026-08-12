# Executed probe: Codex user-scope skill resolution

Date: 2026-08-12. `codex-cli 0.147.0` (`/opt/homebrew/bin/codex`).
Instrument: `codex debug prompt-input` — renders the model-visible prompt input
list as JSON, so a resolved skill appears as a `<skills_instructions>` row with
its absolute source path. Absence from that list is absence from the model's
view, which is what "does not resolve" has to mean.

`SP` below is this session's scratchpad root. Transcripts print `$HOME` where
the run printed the operator's expanded home directory; nothing else is edited.

## Probe 1 — `$CODEX_HOME/skills`, with negative control

```bash
rm -rf $SP/codex-probe && mkdir -p $SP/codex-probe/{neg,pos/skills/sd-probe-marker}
cat > $SP/codex-probe/pos/skills/sd-probe-marker/SKILL.md <<'EOF'
---
name: sd-probe-marker
description: ZZQQ-UNIQUE-PROBE-TOKEN probe skill for machine-scope resolution test.
---
Probe body.
EOF
CODEX_HOME=$SP/codex-probe/neg codex debug prompt-input 2>&1 | grep -c "sd-probe-marker\|ZZQQ-UNIQUE-PROBE-TOKEN"
CODEX_HOME=$SP/codex-probe/pos codex debug prompt-input 2>&1 | grep -c "sd-probe-marker\|ZZQQ-UNIQUE-PROBE-TOKEN"
```

```
negative control (no skills dir): 0
positive (skill present):         1
```

Decisive line from the positive run:

```
- sd-probe-marker: ZZQQ-UNIQUE-PROBE-TOKEN probe skill for machine-scope resolution test. (file: $SP/codex-probe/pos/skills/sd-probe-marker/SKILL.md)
```

**PASS.** Codex resolves a user-scope skill from `$CODEX_HOME/skills`.

## Probe 2 — the finding that matters: `$HOME/.agents/skills`

Probe 1's negative control was not silent. With a scratch `CODEX_HOME` holding
no skills at all, Codex still listed 38 skills, every one of them rooted at
`$HOME/.agents/skills`:

```bash
CODEX_HOME=$SP/codex-probe/neg codex debug prompt-input 2>&1 \
  | grep -o '(file: [^)]*/SKILL\.md)' | sed 's#(file: ##; s#/[^/]*/SKILL.md)##' | sort | uniq -c
```

```
   5 $SP/codex-probe/neg/skills/.system
  38 $HOME/.agents/skills
```

The 38 include the 19 `sd-*` skills the machine installer placed there. CWD was
`/tmp`, which has no `.agents` — so this is not project-root resolution.

### Confirming it follows `HOME` rather than a local artifact

`~/.agents`, `~/.agents/skills`, and `~/.agents/bin` are all real directories,
not symlinks. Redirecting `HOME` as well as `CODEX_HOME`:

```bash
mkdir -p $SP/codex-probe/home2/.agents/skills/zz-home-marker
cat > $SP/codex-probe/home2/.agents/skills/zz-home-marker/SKILL.md <<'EOF'
---
name: zz-home-marker
description: HOMEPROBE-TOKEN confirms .agents/skills resolves against HOME.
---
Body.
EOF
HOME=$SP/codex-probe/home2 CODEX_HOME=$SP/codex-probe/neg codex debug prompt-input 2>&1 \
  | grep -o "zz-home-marker\|HOMEPROBE-TOKEN\|$HOME/\.agents" | sort | uniq -c
```

```
   1 HOMEPROBE-TOKEN
   2 zz-home-marker
```

`$HOME/.agents` does not appear. Resolution follows `HOME`, is
compiled-in, and survives a scratch `CODEX_HOME` with no config file.

## Probe 3 — project-root `.agents/skills` resolves too, and merges

With `HOME` and `CODEX_HOME` both pointed at scratch directories and the CWD
holding a project-root marker skill at `$SP/codex-probe/proj/.agents/skills/`
(named `zz-proj-marker`, and outside this repository):

```bash
cd $SP/codex-probe/proj
HOME=$SP/codex-probe/home2 CODEX_HOME=$SP/codex-probe/neg codex debug prompt-input 2>&1 \
  | grep -o 'zz-proj-marker\|PROJPROBE-TOKEN\|zz-home-marker' | sort | uniq -c
```

```
   1 PROJPROBE-TOKEN
   2 zz-home-marker
   2 zz-proj-marker
```

Both the project-root marker and the HOME-scoped marker resolve in the same run.
Codex merges the two roots rather than preferring one.

This is the operationally important one. It means the vendored `.agents/skills`
in a consumer repository **is doing real work for Codex today**, and conversion
does not make that work unnecessary — it *transfers* it to the machine copy. The
machine-install precondition in the canary task is therefore the actual handoff
point, not a formality: remove the vendored copy on a machine without the pack
installed and a Codex user loses the skills, silently.

## What the machine install already puts there

`installer/machinepayload.py:51-53,119-121` ships three `.agents` families;
`~/.local/state/sd-ai-command-pack/machine/machine-receipt.json` (schemaVersion
1, 115 entries) records:

```
{'agents-bin': 26, 'agents-docs': 2, 'agents-skills': 49,
 'gemini-commands': 19, 'opencode-commands': 19}
```

`49 + 26 + 2 = 77` — exactly the row count `retainVendoredFor: ["codex"]`
retains per declaring consumer.

The installed skill bodies are path-rewritten to absolute machine paths, so the
`agents-bin` half resolves too. `~/.agents/skills/sd-status/SKILL.md:47`:

```
   bash ~/.agents/bin/sd-ai-command-pack-toolchain.sh run-python -- \
     ~/.agents/bin/sd-ai-command-pack-status.py [fleet|REPO_PATH] \
```

## Falsified claims

Two recorded statements are contradicted by Probe 2:

- `CHANGELOG.md:349` — "`codex` is re-dispositioned `repo-native`, because it
  resolves `.agents` against the project root and never reads
  `~/.agents/skills`."
- `scripts/sd-ai-command-pack-thin-resweep.py:663-665` — "`.agents/skills/` is
  how Codex reads a skill, because Codex cannot consume the machine-installed
  plugin at all."

Codex does read `$HOME/.agents/skills`. The plugin-consumption clause is
separately true and separately irrelevant: the machine installer's `.agents`
families are not the Claude plugin, and Codex reads them.

## Scope limits

- Covers `codex` only. `pi`, the other `retainVendoredFor` entry, was not
  probed and no claim is made about it.
- Establishes discovery (the skill reaches the model-visible prompt), not
  end-to-end execution of a pack skill under Codex.
- One machine, one Codex version (`0.147.0`).
