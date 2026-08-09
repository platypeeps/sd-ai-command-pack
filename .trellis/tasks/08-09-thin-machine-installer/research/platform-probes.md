# Executed platform probes (implement.md step 1 verification gate)

- **Date**: 2026-08-09
- **Requirement**: `prd.md` requirement 1 / `design.md` "Verification gate".
  `provisional` flips are step-1 outputs, not design decisions.
- **Rule applied**: one probe per SURFACE. No surface flips on another
  surface's evidence. A probe that cannot run headlessly, or that fails,
  keeps its surface `provisional: true` and excludes it from the payload
  build.

## Method

Every probe ran with a scrubbed environment (`env -i`), a scratch `HOME`, a
scratch `XDG_CONFIG_HOME`, and an **empty** working directory, so the only
possible resolution source for the probe artifact is the user (machine)
scope. The real home directory was never read or written by these runs.

```
HOME=<scratch>/mprobe/home
XDG_CONFIG_HOME=<scratch>/mprobe/xdg
cwd=<scratch>/mprobe/work        # empty: no project-scope adapter files
```

`<scratch>` is the session scratchpad
(`/private/tmp/claude-501/.../26fc345a-1f0c-4cc3-ada8-46763f160642/scratchpad`).
`timeout(1)` does not exist on this machine, so each CLI ran under a small
Python wrapper (`run.py`) that applies a hard timeout and closes stdin;
nothing timed out.

Each probe has a **negative control**: the same command with the probe
artifact removed. A probe "passes" only when the positive run resolves the
artifact and the negative run does not — existence of a file is not
evidence, provenance is.

Installed CLIs: `gemini` 0.46.0, `opencode` 1.18.15 (both under
`/opt/homebrew/bin`).

---

## Probe 1 — Gemini user-scope command: PASS

Gates the `gemini` rows (`~/.gemini/commands/sd/<name>.toml`).

Artifact written to `<scratch>/mprobe/home/.gemini/commands/sd/probe.toml`:

```toml
description = "sd machine-scope user-file resolution probe"

prompt = """
SD machine-scope probe.

!{echo sd-machine-probe-user-scope}
"""
```

The `!{...}` shell-injection trigger is deliberate. In non-interactive mode
`handleSlashCommand` builds a `FileCommandLoader`, resolves the command, and
runs its `ShellProcessor` **before** any model call, so the probe proves
file resolution + parse + execution without needing credentials or network.
`GEMINI_API_KEY` is set to an obviously invalid value only to get past the
auth precheck (`validateNonInteractiveAuth` runs before command loading and
exits 41 otherwise).

Command:

```
cd <scratch>/mprobe/work && env -i PATH="$PATH" \
  HOME=<scratch>/mprobe/home XDG_CONFIG_HOME=<scratch>/mprobe/xdg \
  TERM=dumb GEMINI_API_KEY=sd-probe-invalid-key \
  gemini --skip-trust -p "/sd:probe"
```

Decisive output (positive run):

```
An unexpected critical error occurred:Error: sd:probe cannot be run. Blocked command: "echo sd-machine-probe-user-scope". Reason: Blocked by policy.
    at ShellProcessor.processString (.../chunk-XWSJWBAL.js:53748:15)
    at async Object.action (.../chunk-XWSJWBAL.js:54131:32)
    at async handleSlashCommand (.../gemini-YXO2QQ66.js:10013:22)
```

The command name `sd:probe` and the literal shell body from the probe file
both appear, inside `handleSlashCommand` — the user-scope TOML was found,
parsed, name-mapped to `/sd:probe`, and executed. (The policy engine then
blocked the `echo`, which is fine: the block happens *after* resolution and
is itself the proof.)

Negative control (same command, probe file moved away):

```
    at async Turn.run (.../chunk-RCJSF5RP.js:328879:24) {
  status: 400
}
```

Unresolved, so the raw text `/sd:probe` was sent to the model and failed on
the invalid API key. Different failure, same environment: resolution is what
changed.

**Verdict: `gemini` machine disposition verified. `provisional -> false`.**

---

## Probe 2 — OpenCode global command: PASS

Gates the `opencode` rows (`$XDG_CONFIG_HOME/opencode/commands/sd-<name>.md`).

Artifact written to `<scratch>/mprobe/xdg/opencode/commands/sd-probe.md`
(plural `commands/`, matching the shape the pack already ships):

```markdown
---
description: sd machine-scope user-file resolution probe
---

SD machine-scope probe marker sd-machine-probe-user-scope.
```

Command:

```
cd <scratch>/mprobe/work && env -i PATH="$PATH" \
  HOME=<scratch>/mprobe/home XDG_CONFIG_HOME=<scratch>/mprobe/xdg \
  TERM=dumb opencode debug config
```

Decisive output (positive run, `command` key of the resolved config):

```json
{
  "sd-probe": {
    "description": "sd machine-scope user-file resolution probe",
    "template": "SD machine-scope probe marker sd-machine-probe-user-scope."
  }
}
```

`opencode debug config` prints the **resolved, merged** configuration, so
the entry is proof the loader ingested the file, not proof the file exists.
The body became `template`, which is what the command executor runs.

Negative control (probe file moved away):

```json
  "command": {},
```

**Verdict: `opencode` machine disposition verified (executed, upgrading the
prior doc-only evidence). `provisional -> false`. The XDG root, not a
hardcoded `~/.config`, is what resolved.**

---

## Probe 3 — shared `.agents` skills autoload: PASS

Gates the `shared` rows (`~/.agents/skills/<name>/SKILL.md`). This is the
first EXECUTED evidence for this surface; `platform-verification.md` had
only the OpenCode binary's embedded scope table.

Artifact written to
`<scratch>/mprobe/home/.agents/skills/sd-probe/SKILL.md`:

```markdown
---
name: sd-probe
description: Use when verifying that user-scope .agents skills autoload; marker sd-machine-probe-user-scope.
---

# SD probe

Machine-scope autoload probe body.
```

Command:

```
cd <scratch>/mprobe/work && env -i PATH="$PATH" \
  HOME=<scratch>/mprobe/home XDG_CONFIG_HOME=<scratch>/mprobe/xdg \
  TERM=dumb opencode debug skill
```

Decisive output (positive run, `name | location` per entry):

```
customize-opencode | <built-in>
sd-probe | /private/tmp/.../scratchpad/mprobe/home/.agents/skills/sd-probe/SKILL.md
```

The `location` field is the CLI's own report of where it loaded the skill
from — provenance stated by the tool, not inferred. It is the scratch
`HOME`'s `.agents/skills`, with no project-scope or global-config copy in
play.

Negative control (run before the probe skill was created) listed only the
built-in:

```
customize-opencode | <built-in>
```

Corroborating detail from the same run: OpenCode's built-in
`customize-opencode` skill body documents the external-skill scan
(`~/.claude/skills/<name>/SKILL.md`, `~/.agents/skills/<name>/SKILL.md`) and
the opt-out env vars `OPENCODE_DISABLE_EXTERNAL_SKILLS=1` /
`OPENCODE_DISABLE_CLAUDE_CODE_SKILLS=1`. Worth noting for the installer: a
user who sets either variable disables this surface.

**Verdict: `shared` machine disposition verified for its OpenCode consumer.
`provisional -> false`.**

---

## Codex — no probe run, re-dispositioned on existing executed evidence

`codex` ships zero `files[]` rows; the surface it consumes is `shared`'s
`.agents/skills/**`, and `platform-verification.md` established from the
0.147.0 binary that `.agents` resolves against the **project** root and that
`~/.agents/skills` is never referenced (its user root is
`$CODEX_HOME/skills`). No user-scope probe is constructible for a target
family the pack does not ship, so `codex` is re-dispositioned
`(REPO_NATIVE, False)` rather than force-fitted, and `shared` carries
`retainVendoredFor: ["codex", "pi"]` so migration tooling keeps the vendored
`.agents/**` copy for any consumer that serves those platforms.

`pi` was not probed and stays `repo-native`; it is on the retention list for
the same reason.

## Scope outcome

No surface was shrunk. All three probes passed, so `gemini`, `opencode`, and
`shared` all flip to non-provisional and the payload build covers the full
intended slice.
